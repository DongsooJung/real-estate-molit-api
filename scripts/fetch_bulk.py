"""MOLIT 실거래가 대량 수집.

여러 지역(구) × 여러 달을 한 번에 조회해 data/raw 에 정규화 CSV로 저장한다.
조합별 실패는 건너뛰고(경고), tqdm으로 진행률을 표시한다.

사용 예:
    # 서울 25개 구, 2024-01 ~ 2026-06 전체
    python scripts/fetch_bulk.py --regions seoul25 --months 202401-202606

    # 강남3구, 특정 달들
    python scripts/fetch_bulk.py --regions 11680,11650,11710 --months 202601,202602,202603

사전 준비:
    - .env 에 MOLIT_API_KEY (공공데이터포털 '디코딩' 키)
    - pip install -r requirements.txt
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from hedonic.molit_api import MolitClient, export_chunked_csv  # noqa: E402

# 서울 25개 자치구 SIG_CD
SEOUL25 = [
    "11110", "11140", "11170", "11200", "11215", "11230", "11260", "11290",
    "11305", "11320", "11350", "11380", "11410", "11440", "11470", "11500",
    "11530", "11545", "11560", "11590", "11620", "11650", "11680", "11710",
    "11740",
]


def expand_months(spec: str) -> list[str]:
    """'202401-202606' 범위 또는 '202401,202402' 목록 → YYYYMM 리스트."""
    spec = spec.strip()
    if "-" in spec:
        lo, hi = spec.split("-", 1)
        y, m = int(lo[:4]), int(lo[4:])
        y2, m2 = int(hi[:4]), int(hi[4:])
        out = []
        while (y, m) <= (y2, m2):
            out.append(f"{y:04d}{m:02d}")
            m += 1
            if m > 12:
                y, m = y + 1, 1
        return out
    return [s.strip() for s in spec.split(",") if s.strip()]


def expand_regions(spec: str) -> list[str]:
    if spec.strip().lower() == "seoul25":
        return list(SEOUL25)
    return [s.strip() for s in spec.split(",") if s.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="MOLIT 실거래가 대량 수집")
    parser.add_argument("--regions", default="11680", help="'seoul25' 또는 쉼표구분 SIG_CD")
    parser.add_argument("--months", default="202601", help="'YYYYMM-YYYYMM' 또는 쉼표구분")
    parser.add_argument("--out", default=str(ROOT / "data" / "raw"))
    parser.add_argument("--chunk-size", type=int, default=1000)
    parser.add_argument("--prefix", default="molit")
    args = parser.parse_args()

    regions = expand_regions(args.regions)
    months = expand_months(args.months)
    print(f"수집 대상: {len(regions)}개 구 × {len(months)}개월 = {len(regions)*len(months)} 조합")

    client = MolitClient()  # MOLIT_API_KEY 없으면 ValueError로 안내
    df = client.fetch_multi_period(regions, months)
    if df.empty:
        print("수집된 데이터가 없습니다. (키/지역/월 확인)")
        return

    paths = export_chunked_csv(df, args.out, chunk_size=args.chunk_size, prefix=args.prefix)
    print(f"총 {len(df):,}행 → {len(paths)}개 CSV 저장: {args.out}")


if __name__ == "__main__":
    main()
