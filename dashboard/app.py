"""MOLIT 실거래가 시각화 대시보드 (Streamlit).

실행:
    streamlit run dashboard/app.py
    # 또는 CSV 폴더 지정:
    streamlit run dashboard/app.py -- --data-dir data/raw

탭 구성:
    📊 개요      — KPI, 데이터 품질 요약
    📅 시계열    — 일/주/월 단위 거래건수·가격 추이 (이동평균)
    🗂 구분별    — 단일 차원 집계 + 2개 차원 교차 히트맵
    📈 분포·관계 — 가격/면적 히스토그램·박스플롯, 면적-가격 산점도
    📋 데이터    — 원본 테이블 + CSV 다운로드
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# dashboard/ 를 import 경로에 추가 (loader는 hedonic 패키지에 비의존)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from loader import load_transactions  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# 가격 단위 설정: 표시명 → (컬럼, 라벨)
PRICE_UNITS = {
    "㎡당(만원)": "price_per_sqm",
    "평당(만원)": "price_per_pyeong",
}
DIM_LABELS = {
    "legal_dong": "법정동",
    "apt_name": "단지",
    "deal_type": "거래유형",
    "floor_category": "층수범주",
}
GEOJSON_PATH = ROOT / "dashboard" / "assets" / "seoul_sig.geojson"
# 서울 25개 자치구 SIG_CD → 이름 (지도 hover·라벨용)
SEOUL_SIG = {
    "11110": "종로구", "11140": "중구", "11170": "용산구", "11200": "성동구",
    "11215": "광진구", "11230": "동대문구", "11260": "중랑구", "11290": "성북구",
    "11305": "강북구", "11320": "도봉구", "11350": "노원구", "11380": "은평구",
    "11410": "서대문구", "11440": "마포구", "11470": "양천구", "11500": "강서구",
    "11530": "구로구", "11545": "금천구", "11560": "영등포구", "11590": "동작구",
    "11620": "관악구", "11650": "서초구", "11680": "강남구", "11710": "송파구",
    "11740": "강동구",
}


def _default_data_dir() -> str:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=None)
    args, _ = parser.parse_known_args()
    return args.data_dir or str(ROOT / "data" / "sample")


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
# 사이드바: 필터 + 옵션
# ----------------------------------------------------------------------
st.sidebar.header("필터")
f = df.copy()

if "is_cancelled" in f.columns and f["is_cancelled"].any():
    if st.sidebar.checkbox("취소(해제)거래 제외", value=False):
        f = f[~f["is_cancelled"]]

if "region_code" in f.columns:
    opts = sorted(f["region_code"].dropna().astype(str).unique())
    sel = st.sidebar.multiselect("지역코드", opts, default=opts)
    f = f[f["region_code"].astype(str).isin(sel)]

if "legal_dong" in f.columns:
    opts = sorted(f["legal_dong"].dropna().unique())
    sel = st.sidebar.multiselect("법정동", opts, default=opts)
    f = f[f["legal_dong"].isin(sel)]

if "deal_type" in f.columns and f["deal_type"].notna().any():
    opts = sorted(f["deal_type"].dropna().unique())
    if opts:
        sel = st.sidebar.multiselect("거래유형", opts, default=opts)
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

st.sidebar.divider()
price_unit_label = st.sidebar.radio(
    "가격 단위", list(PRICE_UNITS), index=0, help="㎡당/평당 단가 기준"
)
price_col = PRICE_UNITS[price_unit_label]

if f.empty:
    st.info("필터 조건에 맞는 데이터가 없습니다.")
    st.stop()

# 사용 가능한 구분 차원
dims = [c for c in DIM_LABELS if c in f.columns and f[c].notna().any()]


def _dim_label(col: str) -> str:
    return DIM_LABELS.get(col, col)


# ----------------------------------------------------------------------
# 탭
# ----------------------------------------------------------------------
tab_overview, tab_time, tab_map, tab_dim, tab_dist, tab_data = st.tabs(
    ["📊 개요", "📅 시계열", "🗺 지도", "🗂 구분별", "📈 분포·관계", "📋 데이터"]
)


@st.cache_data(show_spinner=False)
def _load_geojson(path: str) -> dict | None:
    p = Path(path)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))

# ===== 개요 =====
with tab_overview:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("거래 건수", f"{len(f):,}")
    if "deal_amount" in f.columns:
        c2.metric("평균 거래금액", f"{f['deal_amount'].mean()/10000:,.1f} 억")
    if price_col in f.columns:
        c3.metric(f"평균 {price_unit_label}", f"{f[price_col].mean():,.0f} 만원")
    if "apt_name" in f.columns:
        c4.metric("단지 수", f"{f['apt_name'].nunique():,}")

    st.divider()
    q1, q2 = st.columns(2)
    with q1:
        st.markdown("**데이터 품질**")
        quality = {"행 수": f"{len(f):,}"}
        if "deal_date" in f.columns:
            quality["거래일 결측"] = f"{int(f['deal_date'].isna().sum()):,}"
        if "is_cancelled" in df.columns:
            quality["취소거래(원본)"] = f"{int(df['is_cancelled'].sum()):,}"
        if "deal_date" in f.columns and f["deal_date"].notna().any():
            quality["기간"] = (
                f"{f['deal_date'].min():%Y-%m-%d} ~ {f['deal_date'].max():%Y-%m-%d}"
            )
        st.table(pd.Series(quality, name="값").to_frame())
    with q2:
        if dims:
            st.markdown(f"**{_dim_label(dims[0])}별 거래건수 (상위 10)**")
            top = f[dims[0]].value_counts().head(10).rename("건수").reset_index()
            top.columns = [_dim_label(dims[0]), "건수"]
            st.dataframe(top, use_container_width=True, hide_index=True)

# ===== 시계열 =====
with tab_time:
    if "deal_date" not in f.columns or not f["deal_date"].notna().any():
        st.caption("거래일(deal_date) 정보가 없어 시계열을 표시할 수 없습니다.")
    else:
        c1, c2, c3 = st.columns([1, 1, 1])
        gran = c1.radio("집계 단위", ["일", "주", "월"], horizontal=True)
        ts_metric = c2.selectbox(
            "지표", ["거래건수", "평균 거래금액(억)", f"평균 {price_unit_label}"]
        )
        show_ma = c3.checkbox("이동평균(7)", value=(gran == "일"))

        freq = {"일": "D", "주": "W", "월": "MS"}[gran]
        base = f.dropna(subset=["deal_date"]).set_index("deal_date")
        grouper = pd.Grouper(freq=freq)
        if ts_metric == "거래건수":
            ts = base.groupby(grouper).size().rename("값")
        elif "거래금액" in ts_metric:
            ts = (base.groupby(grouper)["deal_amount"].mean() / 10000).rename("값")
        else:
            ts = base.groupby(grouper)[price_col].mean().rename("값")
        ts = ts.reset_index()

        if ts_metric == "거래건수":
            fig = px.bar(ts, x="deal_date", y="값", title=f"{gran}별 {ts_metric}")
        else:
            fig = px.line(ts, x="deal_date", y="값", markers=True, title=f"{gran}별 {ts_metric}")
        if show_ma and len(ts) >= 3:
            ts["이동평균"] = ts["값"].rolling(7, min_periods=1).mean()
            fig.add_scatter(x=ts["deal_date"], y=ts["이동평균"], mode="lines", name="이동평균(7)")
        fig.update_layout(yaxis_title=ts_metric, xaxis_title="")
        st.plotly_chart(fig, use_container_width=True)

# ===== 지도 =====
with tab_map:
    gj_path = st.text_input(
        "경계 GeoJSON 경로 (properties.sig_cd = region_code)",
        value=str(GEOJSON_PATH),
        key="geojson_path",
    )
    geojson = _load_geojson(gj_path)

    if "region_code" not in f.columns:
        st.caption("region_code 컬럼이 없어 지도를 표시할 수 없습니다.")
    elif geojson is None:
        st.warning(
            f"GeoJSON을 찾지 못했습니다: `{gj_path}`\n\n"
            "`python scripts/build_seoul_geo.py` 로 서울 시군구 경계를 생성하세요."
        )
    else:
        m1, m2 = st.columns([1, 1])
        map_metric = m1.selectbox(
            "지표", ["거래건수", "평균 거래금액(억)", f"평균 {price_unit_label}"], key="map_metric"
        )
        anim = m2.radio("시간 애니메이션", ["없음", "일별", "주별"], horizontal=True, key="map_anim")

        fmap = f.copy()
        fmap["region_code"] = fmap["region_code"].astype(str)

        def _aggregate(frame: pd.DataFrame, by: list[str]) -> pd.DataFrame:
            if map_metric == "거래건수":
                out = frame.groupby(by, observed=True).size().rename("값").reset_index()
            elif "거래금액" in map_metric:
                out = frame.groupby(by, observed=True)["deal_amount"].mean().rename("값").reset_index()
                out["값"] = out["값"] / 10000
            else:
                out = frame.groupby(by, observed=True)[price_col].mean().rename("값").reset_index()
            return out

        anim_frame = None
        if anim != "없음" and "deal_date" in fmap.columns and fmap["deal_date"].notna().any():
            freq = "D" if anim == "일별" else "W"
            fmap = fmap.dropna(subset=["deal_date"])
            fmap["기간"] = (
                fmap["deal_date"].dt.to_period(freq).dt.start_time.dt.strftime("%Y-%m-%d")
            )
            agg = _aggregate(fmap, ["region_code", "기간"])
            anim_frame = "기간"
            order = {"기간": sorted(agg["기간"].unique())}
        else:
            agg = _aggregate(fmap, ["region_code"])
            order = None

        agg["자치구"] = agg["region_code"].map(SEOUL_SIG).fillna(agg["region_code"])
        fig = px.choropleth(
            agg,
            geojson=geojson,
            locations="region_code",
            featureidkey="properties.sig_cd",
            color="값",
            color_continuous_scale="YlOrRd",
            range_color=(agg["값"].min(), agg["값"].max()),
            animation_frame=anim_frame,
            category_orders=order,
            hover_name="자치구",
            labels={"값": map_metric},
        )
        fig.update_geos(fitbounds="locations", visible=False)
        fig.update_layout(margin=dict(l=0, r=0, t=30, b=0), height=560)
        st.plotly_chart(fig, use_container_width=True)
        if anim != "없음" and anim_frame is None:
            st.caption("거래일 정보가 없어 애니메이션 없이 표시했습니다.")

# ===== 구분별 =====
with tab_dim:
    if not dims:
        st.caption("구분 가능한 범주형 컬럼이 없습니다.")
    else:
        metric_map = {
            "거래 건수": ("size", None),
            "평균 거래금액(억)": ("mean", "deal_amount"),
            "총 거래금액(억)": ("sum", "deal_amount"),
            f"평균 {price_unit_label}": ("mean", price_col),
        }
        a, b, c = st.columns([1, 1, 1])
        dim = a.selectbox("구분 기준", dims, format_func=_dim_label)
        metric = b.selectbox("지표", list(metric_map))
        topn = c.slider("상위 N", 5, 30, 15)

        agg, target = metric_map[metric]
        if agg == "size":
            g = f.groupby(dim, observed=True).size().rename("값").reset_index()
        else:
            g = f.groupby(dim, observed=True)[target].agg(agg).rename("값").reset_index()
            if "억" in metric:
                g["값"] = g["값"] / 10000
        g = g.sort_values("값", ascending=False).head(topn)
        fig = px.bar(
            g, x="값", y=dim, orientation="h", title=f"{_dim_label(dim)}별 {metric}"
        )
        fig.update_layout(yaxis_title=_dim_label(dim))
        fig.update_yaxes(categoryorder="total ascending")
        st.plotly_chart(fig, use_container_width=True)

        # 2개 차원 교차 히트맵
        if len(dims) >= 2:
            st.markdown("**교차 분석 (히트맵)**")
            h1, h2, h3 = st.columns([1, 1, 1])
            row_dim = h1.selectbox("행", dims, index=0, format_func=_dim_label, key="hm_row")
            col_dim = h2.selectbox("열", dims, index=1, format_func=_dim_label, key="hm_col")
            hm_metric = h3.selectbox("값", ["거래건수", f"평균 {price_unit_label}"], key="hm_metric")
            if row_dim == col_dim:
                st.caption("행과 열에 서로 다른 차원을 선택하세요.")
            else:
                if hm_metric == "거래건수":
                    pv = f.pivot_table(index=row_dim, columns=col_dim, aggfunc="size", fill_value=0)
                else:
                    pv = f.pivot_table(
                        index=row_dim, columns=col_dim, values=price_col, aggfunc="mean"
                    )
                st.plotly_chart(
                    px.imshow(pv, text_auto=".0f", aspect="auto",
                              labels=dict(color=hm_metric),
                              title=f"{_dim_label(row_dim)} × {_dim_label(col_dim)} — {hm_metric}"),
                    use_container_width=True,
                )

# ===== 분포·관계 =====
with tab_dist:
    if price_col in f.columns:
        d1, d2 = st.columns(2)
        d1.plotly_chart(
            px.histogram(f, x=price_col, nbins=40, title=f"{price_unit_label} 분포",
                         labels={price_col: price_unit_label}),
            use_container_width=True,
        )
        if dims:
            box_dim = d2.selectbox("박스플롯 구분", dims, format_func=_dim_label, key="box_dim")
            d2.plotly_chart(
                px.box(f, x=box_dim, y=price_col, title=f"{_dim_label(box_dim)}별 {price_unit_label}",
                       labels={price_col: price_unit_label, box_dim: _dim_label(box_dim)}),
                use_container_width=True,
            )

    if {"area", "deal_amount"} <= set(f.columns):
        st.markdown("**면적 대비 거래금액**")
        color_dim = st.selectbox("색상 구분", ["(없음)"] + dims, index=0, format_func=lambda c: "(없음)" if c == "(없음)" else _dim_label(c))
        sc = f.dropna(subset=["area", "deal_amount"]).copy()
        sc["거래금액(억)"] = sc["deal_amount"] / 10000
        st.plotly_chart(
            px.scatter(
                sc, x="area", y="거래금액(억)",
                color=None if color_dim == "(없음)" else color_dim,
                trendline="ols" if color_dim == "(없음)" else None,
                hover_data=[c for c in ["apt_name", "deal_date", "floor"] if c in sc.columns],
                labels={"area": "전용면적(㎡)"},
            ),
            use_container_width=True,
        )

# ===== 데이터 =====
with tab_data:
    st.dataframe(f, use_container_width=True, height=420)
    st.download_button(
        "필터된 데이터 CSV 다운로드",
        data=f.to_csv(index=False).encode("utf-8-sig"),
        file_name="molit_filtered.csv",
        mime="text/csv",
    )
