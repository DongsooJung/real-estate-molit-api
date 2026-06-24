"""데모용 가짜 실거래 CSV 생성.

MOLIT API 키 없이도 대시보드(dashboard/app.py)를 바로 확인할 수 있도록
data/sample/ 폴더에 50행 단위 정규화 CSV를 생성한다.
chunking·인코딩은 실제 파이프라인과 동일하게 molit_api.export_chunked_csv를 재사용한다.
"""
from __future__ import annotations

import importlib.util
import random
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

# molit_api만 단독 로드 (hedonic 패키지 __init__의 무거운 import 회피)
_spec = importlib.util.spec_from_file_location(
    "molit_api", ROOT / "src" / "hedonic" / "molit_api.py"
)
molit_api = importlib.util.module_from_spec(_spec)
sys.modules["molit_api"] = molit_api
_spec.loader.exec_module(molit_api)


def main() -> None:
    random.seed(42)
    apts = {
        "개포동": ["래미안개포", "개포자이", "디에이치아너힐즈"],
        "역삼동": ["역삼래미안", "역삼아이파크"],
        "대치동": ["대치삼성", "대치아이파크", "은마아파트"],
    }
    deal_types = ["중개거래", "직거래"]
    areas = [39.6, 59.92, 84.97, 114.5, 134.8]

    rows = []
    for ym in ["202601", "202602"]:
        year, month = int(ym[:4]), int(ym[4:])
        for _ in range(150):
            dong = random.choice(list(apts))
            apt = random.choice(apts[dong])
            area = round(random.choice(areas) + random.uniform(-2, 2), 2)
            # 강남권 ㎡당 대략 2,000~3,200만원 → deal_amount(만원)
            amount = int(area * random.uniform(2000, 3200))
            cancelled = random.random() < 0.04  # 약 4%는 해제(취소)거래
            day = random.randint(1, 28)
            rows.append(
                {
                    "deal_amount": amount,
                    "deal_type": random.choice(deal_types),
                    "build_year": random.choice([1999, 2004, 2008, 2015, 2021]),
                    "deal_year": year,
                    "deal_month": month,
                    "deal_day": day,
                    "legal_dong": dong,
                    "apt_name": apt,
                    "area": area,
                    "jibun": str(random.randint(1, 900)),
                    "region_code": "11680",
                    "floor": random.randint(1, 30),
                    "cancel_date": f"{ym}{day:02d}" if cancelled else "",
                    "cancel_flag": "O" if cancelled else "",
                }
            )

    df = pd.DataFrame(rows)
    out_dir = ROOT / "data" / "sample"
    paths = molit_api.export_chunked_csv(
        df, out_dir, chunk_size=50, prefix="molit_11680_sample"
    )
    print(f"{len(df)}행 → {len(paths)}개 CSV 생성: {out_dir}")


if __name__ == "__main__":
    main()
