"""
공간가중행렬 테스트 스켈레톤

TODO 항목을 구현하면서 순차적으로 테스트 통과시킬 수 있도록 설계.
"""
import pytest
import numpy as np

# 공간계량 스택(geopandas/shapely)이 없으면 이 모듈 전체를 skip한다.
gpd = pytest.importorskip("geopandas")
Point = pytest.importorskip("shapely.geometry").Point

# from hedonic.weights import build_weights, summarize_weights


@pytest.fixture
def sample_gdf():
    """10x10 그리드의 100개 점으로 이루어진 테스트 GDF."""
    points = [Point(x, y) for x in range(10) for y in range(10)]
    return gpd.GeoDataFrame(
        {"id": range(100)},
        geometry=points,
        crs="EPSG:5186",
    )


class TestBuildWeights:
    def test_knn_returns_expected_k_neighbors(self, sample_gdf):
        """KNN(k=8) 이면 각 점은 정확히 8개 이웃을 가져야 함."""
        pytest.skip("build_weights 미구현")
        # w = build_weights(sample_gdf, method="knn", k=8)
        # assert all(len(w.neighbors[i]) == 8 for i in w.id_order)

    def test_row_standardization(self, sample_gdf):
        """row_standardize=True면 각 행의 가중치 합은 1.0"""
        pytest.skip("build_weights 미구현")

    def test_distance_band_threshold(self, sample_gdf):
        """threshold=1.5면 격자 상 4방향 + 대각 이웃 포함."""
        pytest.skip("build_weights 미구현")

    def test_invalid_method_raises(self, sample_gdf):
        """미지원 method는 ValueError."""
        pytest.skip("build_weights 미구현")


class TestSummarizeWeights:
    def test_summary_contains_required_keys(self):
        pytest.skip("summarize_weights 미구현")
        # assert set(summarize_weights(w).keys()) >= {"n", "mean_neighbors", "pct_islands", "sparsity"}
