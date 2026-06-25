"""
공간가중행렬(Spatial Weights Matrix) 생성

PySAL/libpysal 기반으로 4가지 방식의 W 행렬을 생성한다.
헤도닉 모형의 공간자기상관 보정에 사용된다.
"""
from __future__ import annotations

import logging
from typing import Literal

import numpy as np
import geopandas as gpd
from libpysal.weights import (
    Queen,
    Rook,
    KNN,
    DistanceBand,
    W,
)

logger = logging.getLogger(__name__)

WeightType = Literal["queen", "rook", "knn", "distance"]


def build_weights(
    gdf: gpd.GeoDataFrame,
    method: WeightType = "knn",
    k: int = 8,
    threshold_meter: float = 1000.0,
    row_standardize: bool = True,
) -> W:
    """
    공간가중행렬 W를 method에 따라 생성.

    Args:
        gdf: 공간 단위(Point 또는 Polygon) GeoDataFrame.
             Point의 경우 미터 좌표계(EPSG:5186 등)로 투영되어 있어야 함.
        method:
            - 'queen': Queen 인접성 (polygon 8방향)
            - 'rook': Rook 인접성 (polygon 4방향)
            - 'knn': K-nearest neighbors (point 분석 기본)
            - 'distance': 거리 밴드 (임계거리 내 모두 이웃)
        k: KNN에서 최근접 이웃 수 (기본 8)
        threshold_meter: DistanceBand 임계거리 (기본 1km)
        row_standardize: True면 W_ij = 1/n_i (행 합 = 1)

    Returns:
        libpysal.weights.W 객체

    Raises:
        ValueError: method 미지원 또는 gdf가 미터 좌표계 아닌 경우
    """
    if gdf.crs is not None and gdf.crs.is_geographic:
        raise ValueError(
            "거리 기반 가중치는 미터 투영좌표계가 필요합니다 "
            "(예: EPSG:5186). gdf.to_crs(5186) 후 사용하세요."
        )

    if method == "queen":
        w = Queen.from_dataframe(gdf, use_index=True)
    elif method == "rook":
        w = Rook.from_dataframe(gdf, use_index=True)
    elif method == "knn":
        w = KNN.from_dataframe(gdf, k=k)
    elif method == "distance":
        w = DistanceBand.from_dataframe(
            gdf, threshold=threshold_meter, binary=True, silence_warnings=True
        )
    else:
        raise ValueError(
            f"지원하지 않는 method: {method!r}. "
            "'queen'|'rook'|'knn'|'distance' 중 선택."
        )

    if row_standardize:
        w.transform = "R"

    return w


def summarize_weights(w: W) -> dict:
    """
    W 행렬 기초 통계 반환.

    Returns:
        {
            'n': int,                # 공간 단위 수
            'mean_neighbors': float, # 평균 이웃 수
            'pct_islands': float,    # 고립점 비율
            'sparsity': float,       # 희소도 (0~1)
        }
    """
    n = w.n
    cardinalities = np.array(list(w.cardinalities.values()), dtype=float)
    mean_neighbors = float(cardinalities.mean()) if n else 0.0
    pct_islands = float(len(w.islands) / n) if n else 0.0
    # 희소도 = 1 - (비영요소 수 / n²)
    nonzero = float(cardinalities.sum())
    sparsity = float(1.0 - nonzero / (n * n)) if n else 1.0

    return {
        "n": int(n),
        "mean_neighbors": mean_neighbors,
        "pct_islands": pct_islands,
        "sparsity": sparsity,
    }


def plot_connectivity(
    w: W,
    gdf: gpd.GeoDataFrame,
    ax=None,
    edge_color: str = "#4ecca3",
    edge_alpha: float = 0.3,
) -> None:
    """
    공간가중행렬 연결 구조 시각화 (이웃 간 엣지 plot).

    고립점(islands)은 빨간색, 이웃 엣지는 민트색으로 표시.
    """
    raise NotImplementedError(
        "TODO: gdf.plot() 후 w.neighbors 순회하며 ax.plot() 엣지 그리기"
    )
