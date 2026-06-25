# Real Estate Hedonic Price Model · 부동산 헤도닉 가격모형 (한국)

> 공간 자기상관을 보정한 한국 아파트 실거래 헤도닉 가격모형
> Hedonic pricing models for Korean apartment transactions with spatial autocorrelation correction

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![PySAL](https://img.shields.io/badge/PySAL-spreg-orange?style=flat-square)](https://pysal.org)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

## 개요 · Overview

국내 부동산 분석은 공간 독립성 가정을 위배하는 단순 OLS 헤도닉 모형을 흔히 사용합니다. 강남권 아파트는 강한 공간 군집을 보이므로, 이를 무시하면 구조·근린·입지 속성의 잠재가격(implicit price) 추정이 편향됩니다. 본 저장소는 MOLIT 실거래가 수집부터 공간 헤도닉 추정·잠재가격 산출까지의 파이프라인을 제공합니다.

Korean real estate analysis commonly uses naive OLS hedonic models that violate spatial independence assumptions. Gangnam apartments exhibit strong spatial clustering — ignoring it biases implicit price estimates for structural, neighborhood, and locational attributes. This repository covers the full pipeline from MOLIT transaction collection to spatial hedonic estimation and implicit price reporting.

## 문제와 접근 · Problem & Approach

1. **고전 헤도닉 / Classical Hedonic** (Rosen, 1974) — OLS 기준선
2. **공간 헤도닉 / Spatial Hedonic** — SAR/SEM 보정 (PySAL/spreg, `models.py`)
3. **잠재가격·MWTP / Implicit Prices** — 한계지불의사액 산출
4. **MOLIT API 연동 / Data Pipeline** — 실시간 실거래 수집 (`molit_api.py`)

## 데이터 파이프라인 · Data Pipeline

```
MOLIT 실거래가 API → 정제 → 지오코딩(Kakao) → 공간조인(행정동)
→ 피처 엔지니어링 → 모형 추정 → 잠재가격 리포트
```

## 주요 변수 · Key Variables

| 구분 Category | 변수 Variables |
|---------------|----------------|
| **구조 Structural** | 전용면적, 층, 연식, 세대수, 주차비율 |
| **근린 Neighborhood** | 학군, 공원 근접성, 상업 밀도 |
| **교통 Transportation** | 지하철 거리, 버스정류장 수, 도로 접근성 |
| **환경 Environmental** | 소음, 조망, 경사, 침수위험구역 |

## 기술 스택 · Tech Stack

- **Core:** Python 3.11+, PySAL (spreg), GeoPandas, statsmodels
- **데이터 수집:** MOLIT 실거래가 API, Kakao/V-World 지오코딩
- **Visualization:** Plotly, Matplotlib, Dash 대시보드

## 프로젝트 구조 · Repository Structure

```
real-estate-hedonic/
├── src/hedonic/
│   ├── molit_api.py            # MOLIT 실거래가 API 래퍼
│   ├── geocoding.py            # Kakao/V-World 지오코딩
│   ├── preprocessing.py        # 정제·공간조인·피처 생성
│   ├── weights.py              # 공간 가중행렬
│   ├── models.py               # OLS, SAR, SEM 헤도닉
│   ├── diagnostics.py          # 공간 진단·검정
│   └── visualization.py        # 가격지도·결과 시각화
├── dashboard/
│   ├── app.py                  # 인터랙티브 대시보드
│   └── loader.py
├── scripts/
│   ├── fetch_molit.py          # 실거래 수집
│   ├── fetch_bulk.py           # 대량 수집
│   ├── build_seoul_geo.py      # 서울 경계 GeoJSON 구축
│   └── make_sample.py          # 샘플 데이터 생성
├── notebooks/
│   └── 01_end_to_end_pipeline.ipynb
├── data/{raw, sample}/
├── docs/ARCHITECTURE.md
├── tests/
├── pyproject.toml · requirements.txt
└── LICENSE
```

## 빠른 시작 · Quick Start

```bash
git clone https://github.com/DongsooJung/real-estate-hedonic.git
cd real-estate-hedonic
pip install -r requirements.txt

# MOLIT API 키 설정 (.env.example 참고)
export MOLIT_API_KEY="your_key_here"

jupyter notebook notebooks/01_end_to_end_pipeline.ipynb
```

## 참고문헌 · References

- Rosen, S. (1974). Hedonic Prices and Implicit Markets. *JPE*.
- Can, A. (1992). Specification and Estimation of Hedonic Housing Price Models. *Regional Science and Urban Economics*.
- 국토교통부. 실거래가 공개시스템 API 문서.

## 라이선스 · License

MIT License

## 저자 · Author

**정동수 (Dongsoo Jung)** — 서울대학교 박사과정 · 스마트도시공학
연구 분야: 공간계량 × 부동산 × 도시정책
