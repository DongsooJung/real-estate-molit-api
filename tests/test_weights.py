"""
공간가중행렬 테스트

build_weights / summarize_weights 구현 검증.
공간계량 스택(geopandas/shapely/libpysal)이 없으면 모듈 전체를 skip한다.
"""
import sys
from pathlib import Path

import pytest
import numpy as np

# 공간계량 스택이 없으면 이 모듈 전체를 skip한다.
gpd = pytest.importorskip("geopandas")
Point = pytest.importorskip("shapely.geometry").Point
pytest.importorskip("libpysal")

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from hedonic.weights import build_weights, summarize_weights


@pytest.fixture
def sample_gdf():
    """10x10 그리드의 100개 점으로 이루어진 테스트 GDF (단위 간격)."""
    points = [Point(x, y) for x in range(10) for y in range(10)]
    return gpd.GeoDataFrame(
        {"id": range(100)},
        geometry=points,
        crs="EPSG:5186",
    )


class TestBuildWeights:
    def test_knn_returns_expected_k_neighbors(self, sample_gdf):
        """KNN(k=8) 이면 각 점은 정확히 8개 이웃을 가져야 함."""
        w = build_weights(sample_gdf, method="knn", k=8, row_standardize=False)
        assert all(len(w.neighbors[i]) == 8 for i in w.id_order)

    def test_row_standardization(self, sample_gdf):
        """row_standardize=True면 각 행의 가중치 합은 1.0"""
        w = build_weights(sample_gdf, method="knn", k=8, row_standardize=True)
        for i in w.id_order:
            assert sum(w.weights[i]) == pytest.approx(1.0)

    def test_distance_band_threshold(self, sample_gdf):
        """threshold=1.5면 격자 상 4방향 + 대각 이웃 포함 (내부점 8이웃)."""
        w = build_weights(
            sample_gdf, method="distance", threshold_meter=1.5,
            row_standardize=False,
        )
        # 내부점(5,5) → id = x*10 + y = 55. 직교 4 + 대각 4 = 8 이웃
        interior_id = 55
        assert len(w.neighbors[interior_id]) == 8

    def test_distance_band_corner_fewer(self, sample_gdf):
        """모서리점(0,0)은 직교 2 + 대각 1 = 3 이웃."""
        w = build_weights(
            sample_gdf, method="distance", threshold_meter=1.5,
            row_standardize=False,
        )
        corner_id = 0  # (0,0)
        assert len(w.neighbors[corner_id]) == 3

    def test_invalid_method_raises(self, sample_gdf):
        """미지원 method는 ValueError."""
        with pytest.raises(ValueError):
            build_weights(sample_gdf, method="invalid_xyz")

    def test_geographic_crs_raises(self):
        """경위도(EPSG:4326) 좌표계는 ValueError."""
        gdf = gpd.GeoDataFrame(
            {"id": [0, 1]},
            geometry=[Point(127.0, 37.5), Point(127.1, 37.6)],
            crs="EPSG:4326",
        )
        with pytest.raises(ValueError):
            build_weights(gdf, method="knn", k=1)


class TestSummarizeWeights:
    def test_summary_contains_required_keys(self, sample_gdf):
        w = build_weights(sample_gdf, method="knn", k=8)
        summary = summarize_weights(w)
        assert set(summary.keys()) >= {"n", "mean_neighbors", "pct_islands", "sparsity"}

    def test_summary_values(self, sample_gdf):
        w = build_weights(sample_gdf, method="knn", k=8, row_standardize=False)
        summary = summarize_weights(w)
        assert summary["n"] == 100
        assert summary["mean_neighbors"] == pytest.approx(8.0)
        assert summary["pct_islands"] == 0.0
        assert 0.0 <= summary["sparsity"] <= 1.0

    def test_distance_band_all_islands(self, sample_gdf):
        # 매우 작은 threshold → 모든 점이 고립(섬)
        w = build_weights(
            sample_gdf, method="distance", threshold_meter=0.5,
            row_standardize=False,
        )
        summary = summarize_weights(w)
        assert summary["pct_islands"] == pytest.approx(1.0)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
