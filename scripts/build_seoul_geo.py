"""서울 시군구 경계 GeoJSON 빌드 (대시보드 지도 탭용).

전국 시군구 GeoJSON(통계청 kostat, 약 18MB)을 내려받아
서울 25개 구만 추려 geometry를 단순화하고, MOLIT region_code(SIG_CD)를
properties.sig_cd 로 부여한 경량 GeoJSON을 생성한다.

출력: dashboard/assets/seoul_sig.geojson (리포에 커밋되는 소형 파일)
실행: python scripts/build_seoul_geo.py
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from shapely.geometry import mapping, shape

ROOT = Path(__file__).resolve().parent.parent
SRC_URL = (
    "https://raw.githubusercontent.com/southkorea/southkorea-maps/master/"
    "kostat/2018/json/skorea-municipalities-2018-geo.json"
)
OUT = ROOT / "dashboard" / "assets" / "seoul_sig.geojson"

# 서울 25개 자치구: 행정표준 SIG_CD ↔ 구 이름 (MOLIT region_code 5자리와 동일)
SEOUL_SIG = {
    "11110": "종로구", "11140": "중구", "11170": "용산구", "11200": "성동구",
    "11215": "광진구", "11230": "동대문구", "11260": "중랑구", "11290": "성북구",
    "11305": "강북구", "11320": "도봉구", "11350": "노원구", "11380": "은평구",
    "11410": "서대문구", "11440": "마포구", "11470": "양천구", "11500": "강서구",
    "11530": "구로구", "11545": "금천구", "11560": "영등포구", "11590": "동작구",
    "11620": "관악구", "11650": "서초구", "11680": "강남구", "11710": "송파구",
    "11740": "강동구",
}
NAME_TO_SIG = {v: k for k, v in SEOUL_SIG.items()}
TOLERANCE = 0.0006  # 약 50~60m, 시각화용 단순화


def main() -> None:
    print("다운로드 중...", SRC_URL)
    with urllib.request.urlopen(SRC_URL) as resp:
        data = json.load(resp)

    out_features = []
    for feat in data["features"]:
        props = feat["properties"]
        # 통계청 코드 접두사 '11' = 서울. 타 도시의 동명 구(중구·강서구 등) 오매칭 방지.
        if not str(props.get("code", "")).startswith("11"):
            continue
        name = props.get("name")
        if name not in NAME_TO_SIG:
            continue
        geom = shape(feat["geometry"]).simplify(TOLERANCE, preserve_topology=True)
        out_features.append(
            {
                "type": "Feature",
                "properties": {"sig_cd": NAME_TO_SIG[name], "name": name},
                "geometry": mapping(geom),
            }
        )

    out_features.sort(key=lambda f: f["properties"]["sig_cd"])
    fc = {"type": "FeatureCollection", "features": out_features}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
    print(f"생성: {OUT} ({OUT.stat().st_size:,} bytes, {len(out_features)}개 구)")
    missing = set(SEOUL_SIG) - {f["properties"]["sig_cd"] for f in out_features}
    if missing:
        print("경고: 매칭 안 된 SIG_CD:", missing)


if __name__ == "__main__":
    main()
