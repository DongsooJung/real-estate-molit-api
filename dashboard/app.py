"""MOLIT 실거래가 시각화 대시보드 (Streamlit).

실행:
    streamlit run dashboard/app.py
    # 또는 CSV 폴더 지정:
    streamlit run dashboard/app.py -- --data-dir data/raw

기능:
    - 사이드바 필터: 지역코드 / 법정동 / 거래일 범위 / 거래유형 / 면적
    - 일별: 거래건수·평균 거래금액 추이
    - 데이터 구분별: 법정동·단지·거래유형·층수범주 집계 (지표 선택)
    - 면적-가격 산점도, 원본 테이블 + CSV 다운로드
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# dashboard/ 를 import 경로에 추가 (loader는 hedonic 패키지에 비의존)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from loader import load_transactions  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _default_data_dir() -> str:
    # CLI 인자(streamlit run app.py -- --data-dir X) 우선, 없으면 data/sample
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=None)
    args, _ = parser.parse_known_args()
    if args.data_dir:
        return args.data_dir
    return str(ROOT / "data" / "sample")


st.set_page_config(page_title="MOLIT 실거래가 대시보드", page_icon="🏢", layout="wide")
st.title("🏢 MOLIT 아파트 실거래가 대시보드")

# ----------------------------------------------------------------------
# 데이터 로드
# ----------------------------------------------------------------------
data_dir = st.sidebar.text_input("📁 CSV 폴더", value=_default_data_dir())


@st.cache_data(show_spinner=False)
def _load(path: str) -> pd.DataFrame:
    return load_transactions(path)


df = _load(data_dir)

if df.empty:
    st.warning(
        f"`{data_dir}` 에서 CSV를 찾지 못했습니다.\n\n"
        "- 데모 데이터: `python scripts/make_sample.py` 실행 후 `data/sample` 사용\n"
        "- 실제 데이터: `python scripts/fetch_molit.py` 로 `data/raw` 생성"
    )
    st.stop()

# ----------------------------------------------------------------------
# 사이드바 필터
# ----------------------------------------------------------------------
st.sidebar.header("필터")
f = df.copy()

if "region_code" in f.columns:
    regions = sorted(f["region_code"].dropna().astype(str).unique())
    sel = st.sidebar.multiselect("지역코드", regions, default=regions)
    f = f[f["region_code"].astype(str).isin(sel)]

if "legal_dong" in f.columns:
    dongs = sorted(f["legal_dong"].dropna().unique())
    sel = st.sidebar.multiselect("법정동", dongs, default=dongs)
    f = f[f["legal_dong"].isin(sel)]

if "deal_type" in f.columns and f["deal_type"].notna().any():
    types = sorted(f["deal_type"].dropna().unique())
    if types:
        sel = st.sidebar.multiselect("거래유형", types, default=types)
        f = f[f["deal_type"].isin(sel)]

if "deal_date" in f.columns and f["deal_date"].notna().any():
    dmin, dmax = f["deal_date"].min().date(), f["deal_date"].max().date()
    rng = st.sidebar.date_input("거래일 범위", value=(dmin, dmax), min_value=dmin, max_value=dmax)
    if isinstance(rng, tuple) and len(rng) == 2:
        lo, hi = pd.Timestamp(rng[0]), pd.Timestamp(rng[1])
        f = f[(f["deal_date"] >= lo) & (f["deal_date"] <= hi)]

if "area" in f.columns and f["area"].notna().any():
    amin, amax = float(f["area"].min()), float(f["area"].max())
    if amin < amax:
        lo, hi = st.sidebar.slider("전용면적(㎡)", amin, amax, (amin, amax))
        f = f[(f["area"] >= lo) & (f["area"] <= hi)]

if f.empty:
    st.info("필터 조건에 맞는 데이터가 없습니다.")
    st.stop()

# ----------------------------------------------------------------------
# KPI
# ----------------------------------------------------------------------
c1, c2, c3, c4 = st.columns(4)
c1.metric("거래 건수", f"{len(f):,}")
if "deal_amount" in f.columns:
    c2.metric("평균 거래금액", f"{f['deal_amount'].mean()/10000:,.1f} 억")
if "price_per_sqm" in f.columns:
    c3.metric("평균 ㎡당", f"{f['price_per_sqm'].mean():,.0f} 만원")
if "apt_name" in f.columns:
    c4.metric("단지 수", f"{f['apt_name'].nunique():,}")

st.divider()

# ----------------------------------------------------------------------
# 일별 추이
# ----------------------------------------------------------------------
st.subheader("📅 일별 추이")
if "deal_date" in f.columns and f["deal_date"].notna().any():
    daily = (
        f.dropna(subset=["deal_date"])
        .groupby("deal_date")
        .agg(거래건수=("deal_amount", "size"), 평균금액=("deal_amount", "mean"))
        .reset_index()
    )
    daily["평균금액(억)"] = daily["평균금액"] / 10000
    g1, g2 = st.columns(2)
    g1.plotly_chart(
        px.bar(daily, x="deal_date", y="거래건수", title="일별 거래건수"),
        use_container_width=True,
    )
    g2.plotly_chart(
        px.line(daily, x="deal_date", y="평균금액(억)", markers=True, title="일별 평균 거래금액"),
        use_container_width=True,
    )
else:
    st.caption("거래일(deal_date) 정보가 없어 일별 추이를 표시할 수 없습니다.")

st.divider()

# ----------------------------------------------------------------------
# 데이터 구분별 집계
# ----------------------------------------------------------------------
st.subheader("🗂 데이터 구분별 집계")
dim_candidates = [c for c in ["legal_dong", "apt_name", "deal_type", "floor_category"] if c in f.columns]
metric_map = {
    "거래 건수": ("size", None),
    "평균 거래금액(억)": ("mean", "deal_amount"),
    "총 거래금액(억)": ("sum", "deal_amount"),
    "평균 ㎡당(만원)": ("mean", "price_per_sqm"),
}
col_a, col_b, col_c = st.columns([1, 1, 1])
dim = col_a.selectbox("구분 기준", dim_candidates)
metric = col_b.selectbox("지표", list(metric_map.keys()))
topn = col_c.slider("상위 N", 5, 30, 15)

agg, target = metric_map[metric]
if agg == "size":
    grouped = f.groupby(dim, observed=True).size().rename("값").reset_index()
else:
    grouped = f.groupby(dim, observed=True)[target].agg(agg).rename("값").reset_index()
    if "억" in metric:
        grouped["값"] = grouped["값"] / 10000

grouped = grouped.sort_values("값", ascending=False).head(topn)
st.plotly_chart(
    px.bar(grouped, x="값", y=dim, orientation="h", title=f"{dim}별 {metric}").update_yaxes(
        categoryorder="total ascending"
    ),
    use_container_width=True,
)

st.divider()

# ----------------------------------------------------------------------
# 면적-가격 산점도
# ----------------------------------------------------------------------
if {"area", "deal_amount"} <= set(f.columns):
    st.subheader("📈 면적 대비 거래금액")
    color_dim = st.selectbox("색상 구분", ["(없음)"] + dim_candidates, index=0)
    scatter = f.dropna(subset=["area", "deal_amount"]).copy()
    scatter["거래금액(억)"] = scatter["deal_amount"] / 10000
    fig = px.scatter(
        scatter,
        x="area",
        y="거래금액(억)",
        color=None if color_dim == "(없음)" else color_dim,
        hover_data=[c for c in ["apt_name", "deal_date", "floor"] if c in scatter.columns],
        labels={"area": "전용면적(㎡)"},
    )
    st.plotly_chart(fig, use_container_width=True)

# ----------------------------------------------------------------------
# 원본 테이블 + 다운로드
# ----------------------------------------------------------------------
st.subheader("📋 데이터")
st.dataframe(f, use_container_width=True, height=320)
st.download_button(
    "필터된 데이터 CSV 다운로드",
    data=f.to_csv(index=False).encode("utf-8-sig"),
    file_name="molit_filtered.csv",
    mime="text/csv",
)
