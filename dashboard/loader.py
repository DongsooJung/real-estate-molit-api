"""대시보드용 CSV 로더.

molit_api.export_chunked_csv()가 만든 정규화 CSV들을 한 폴더에서 읽어
파생 컬럼(deal_date, price_per_sqm 등)을 붙인 단일 DataFrame으로 반환한다.

hedonic 패키지(__init__ → geopandas/spreg)에 의존하지 않도록 순수 pandas로
작성해, 무거운 공간계량 스택 없이도 대시보드를 띄울 수 있게 한다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Union

import pandas as pd

_INT_COLS = ("deal_amount", "deal_year", "deal_month", "deal_day", "build_year", "floor")


def load_transactions(data_dir: Union[str, Path], pattern: str = "*.csv") -> pd.DataFrame:
    """data_dir 내 pattern과 일치하는 모든 CSV를 읽어 병합 후 파생 컬럼 추가.

    Args:
        data_dir: CSV가 들어 있는 폴더
        pattern: glob 패턴 (기본 '*.csv')

    Returns:
        병합·가공된 DataFrame. 파일이 없으면 빈 DataFrame.
    """
    paths = sorted(Path(data_dir).glob(pattern))
    if not paths:
        return pd.DataFrame()
    frames = [pd.read_csv(p) for p in paths]
    df = pd.concat(frames, ignore_index=True)
    return add_derived(df)


def add_derived(df: pd.DataFrame) -> pd.DataFrame:
    """deal_date(거래일), price_per_sqm(㎡당 만원), floor_category 파생."""
    if df.empty:
        return df

    df = df.copy()
    for col in _INT_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    if "area" in df.columns:
        df["area"] = pd.to_numeric(df["area"], errors="coerce")

    # 거래일: 연/월/일 → datetime (결측·이상치는 NaT)
    if {"deal_year", "deal_month", "deal_day"} <= set(df.columns):
        ymd = (
            df["deal_year"].astype("string")
            + "-"
            + df["deal_month"].astype("string").str.zfill(2)
            + "-"
            + df["deal_day"].astype("string").str.zfill(2)
        )
        df["deal_date"] = pd.to_datetime(ymd, format="%Y-%m-%d", errors="coerce")

    # ㎡당 가격(만원): deal_amount(만원) / area(㎡)
    if {"deal_amount", "area"} <= set(df.columns):
        df["price_per_sqm"] = df["deal_amount"] / df["area"]

    # 층수 범주
    if "floor" in df.columns:
        df["floor_category"] = pd.cut(
            df["floor"].astype("float"),
            bins=[0, 5, 15, float("inf")],
            labels=["저층(1-5)", "중층(6-15)", "고층(16+)"],
        )

    return df
