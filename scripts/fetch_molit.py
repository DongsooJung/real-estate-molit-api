"""MOLIT 실거래가 수집 → 50행 단위 CSV 저장 퀵스타트.

실행 방법 (둘 중 하나):
    1) VS Code: 이 파일을 열고 F5 ("Python: 현재 파일" 구성) — PYTHONPATH=src 자동 설정
    2) 터미널:  python -m scripts.fetch_molit   (repo 루트에서, src가 경로에 있어야 함)

사전 준비:
    - .env.example을 .env로 복사하고 MOLIT_API_KEY(공공데이터포털 '디코딩' 키) 입력
    - pip install -r requirements.txt
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# src 레이아웃을 import 경로에 추가(터미널 직접 실행 시).
SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from hedonic.molit_api import MolitClient  # noqa: E402


def main() -> None:
    region = os.getenv("TARGET_REGION_CODE", "11680")   # 기본: 강남구
    year_month = os.getenv("TARGET_YEAR_MONTH", "202601")
    out_dir = Path(os.getenv("DATA_DIR", "./data")) / "raw"

    client = MolitClient()  # MOLIT_API_KEY 없으면 ValueError로 안내
    paths = client.fetch_and_export(region, year_month, out_dir, chunk_size=50)

    if not paths:
        print(f"[{region}/{year_month}] 조회 결과가 없습니다.")
        return
    print(f"[{region}/{year_month}] {len(paths)}개 CSV 저장 완료 → {out_dir}")
    for p in paths:
        print(f"  - {p.name}")


if __name__ == "__main__":
    main()
