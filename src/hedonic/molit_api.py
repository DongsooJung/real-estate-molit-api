"""
MOLIT 실거래가 OpenAPI 클라이언트

국토교통부 아파트 매매 실거래가 OpenAPI를 호출하여
정규화된 DataFrame으로 반환한다.

API Docs: https://www.data.go.kr/data/15057511/openapi.do
Endpoint: getRTMSDataSvcAptTrade
"""
from __future__ import annotations

import os
import math
import logging
import itertools
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable, Optional, Union
from dataclasses import dataclass

import pandas as pd
import requests
from tqdm import tqdm
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()


@dataclass
class MolitQueryParams:
    """MOLIT API 요청 파라미터."""
    region_code: str          # 법정동 5자리 (예: '11680' = 강남구)
    year_month: str           # 'YYYYMM' (예: '202601')
    page_no: int = 1
    num_of_rows: int = 1000


class MolitClient:
    """
    국토교통부 아파트 매매 실거래가 API 클라이언트.

    Attributes:
        api_key: 공공데이터포털 인증키 (환경변수 MOLIT_API_KEY 자동 로드)
        base_url: API 베이스 URL
        timeout: 요청 타임아웃 (초)

    Example:
        >>> client = MolitClient()
        >>> df = client.fetch_transactions("11680", "202601")
        >>> df.shape
        (347, 24)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: int = 30,
    ):
        self.api_key = api_key or os.getenv("MOLIT_API_KEY")
        if not self.api_key:
            raise ValueError(
                "MOLIT_API_KEY가 설정되지 않았습니다. "
                ".env 파일 또는 환경변수를 확인하세요."
            )
        self.base_url = base_url or os.getenv(
            "MOLIT_API_BASE",
            "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade",
        )
        self.timeout = timeout
        self.endpoint = f"{self.base_url}/getRTMSDataSvcAptTrade"

    # ------------------------------------------------------------------
    # Public Methods
    # ------------------------------------------------------------------
    def fetch_transactions(
        self,
        region_code: str,
        year_month: str,
        all_pages: bool = True,
    ) -> pd.DataFrame:
        """
        단일 지역·단월 실거래 데이터 조회.

        Args:
            region_code: 법정동 코드 5자리 (예: '11680')
            year_month: 조회 년월 'YYYYMM' (예: '202601')
            all_pages: True면 모든 페이지를 순회하여 병합

        Returns:
            정규화된 실거래 DataFrame. 주요 컬럼:
                - deal_amount (int): 거래금액 (만원)
                - deal_year, deal_month, deal_day (int)
                - area (float): 전용면적 (㎡)
                - apt_name (str): 단지명
                - jibun (str): 지번
                - legal_dong (str): 법정동명
                - floor (int): 층
                - build_year (int): 건축연도

        Raises:
            requests.HTTPError: API 호출 실패 시
            ValueError: region_code·year_month 형식 오류 시
        """
        self._validate_region_code(region_code)
        self._validate_year_month(year_month)

        frames: list[pd.DataFrame] = []
        page = 1
        while True:
            params = MolitQueryParams(
                region_code=region_code,
                year_month=year_month,
                page_no=page,
            )
            page_df = self._call_single_page(params)
            if page_df.empty:
                break
            frames.append(page_df)
            # 마지막 페이지(요청 행수 미만)면 종료. totalCount 없이 페이징 판정.
            if not all_pages or len(page_df) < params.num_of_rows:
                break
            page += 1

        raw = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        logger.info(
            "MOLIT %s/%s: %d건 조회 (페이지 %d)",
            region_code, year_month, len(raw), page,
        )
        return self._normalize_columns(raw)

    def fetch_multi_period(
        self,
        region_codes: Iterable[str],
        year_months: Iterable[str],
    ) -> pd.DataFrame:
        """
        다지역·다월 데이터 병렬 조회 후 pandas.concat으로 병합.

        Returns:
            모든 구·월 조합의 통합 DataFrame.
            tqdm 프로그레스바로 진행 상태 표시.
        """
        combos = list(itertools.product(region_codes, year_months))
        frames: list[pd.DataFrame] = []
        for region_code, year_month in tqdm(combos, desc="MOLIT fetch"):
            try:
                df = self.fetch_transactions(region_code, year_month)
            except (requests.RequestException, RuntimeError) as exc:
                # 한 조합 실패가 전체를 중단시키지 않도록: 경고 후 건너뜀
                logger.warning(
                    "조회 실패 %s/%s: %s", region_code, year_month, exc
                )
                continue
            if not df.empty:
                frames.append(df)

        if not frames:
            return self._normalize_columns(pd.DataFrame())
        return pd.concat(frames, ignore_index=True)

    def fetch_and_export(
        self,
        region_code: str,
        year_month: str,
        out_dir: Union[str, Path],
        chunk_size: int = 50,
        all_pages: bool = True,
    ) -> list[Path]:
        """단일 지역·월 실거래를 조회한 뒤 chunk_size 행 단위 CSV로 저장.

        Args:
            region_code: 법정동 코드 5자리
            year_month: 'YYYYMM'
            out_dir: CSV 저장 디렉터리 (없으면 생성)
            chunk_size: 파일당 행 수 (기본 50)
            all_pages: True면 모든 페이지 조회

        Returns:
            기록된 CSV 파일 경로 리스트 (조회 결과가 없으면 빈 리스트).
        """
        df = self.fetch_transactions(region_code, year_month, all_pages=all_pages)
        prefix = f"molit_{region_code}_{year_month}"
        return export_chunked_csv(df, out_dir, chunk_size=chunk_size, prefix=prefix)

    # ------------------------------------------------------------------
    # Private Helpers
    # ------------------------------------------------------------------
    def _call_single_page(self, params: MolitQueryParams) -> pd.DataFrame:
        """단일 페이지 API 호출. XML 파싱 후 (가공 전) DataFrame 반환.

        반환되는 모든 컬럼은 한글 태그명·문자열 상태이며, 타입 캐스팅과
        컬럼명 변환은 _normalize_columns()가 담당한다. items가 없으면
        빈 DataFrame을 반환한다.
        """
        query = {
            "serviceKey": self.api_key,        # ⚠️ 공공데이터포털 '디코딩' 키 사용
            "LAWD_CD": params.region_code,     # 레거시 RTMSOBJSvc 엔드포인트 파라미터명
            "DEAL_YMD": params.year_month,
            "pageNo": params.page_no,
            "numOfRows": params.num_of_rows,
        }
        resp = requests.get(self.endpoint, params=query, timeout=self.timeout)
        resp.raise_for_status()

        # bytes로 파싱(인코딩 헤더 의존 회피). 게이트웨이가 XML이 아닌 평문/HTML
        # 에러("Unauthorized" 등)를 200으로 줄 수 있어 ParseError를 RuntimeError로 변환.
        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError as exc:
            snippet = resp.text[:200].strip()
            raise RuntimeError(f"MOLIT API 응답 파싱 실패: {snippet!r}") from exc

        # 공공데이터포털 표준 헤더: HTTP 200이라도 에러일 수 있어 resultCode 확인.
        code = root.findtext(".//resultCode")
        if code is not None and code not in ("00", "000"):
            msg = root.findtext(".//resultMsg")
            raise RuntimeError(f"MOLIT API 오류 [{code}]: {msg}")

        rows = [
            {child.tag: (child.text or "").strip() for child in item}
            for item in root.findall(".//item")
        ]
        return pd.DataFrame(rows)

    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """MOLIT 한글 컬럼명을 영문 snake_case로 변환, 타입 캐스팅."""
        if df.empty:
            # 빈 응답에도 다운스트림이 기대하는 스키마를 보장한다.
            return pd.DataFrame(columns=list(COLUMN_MAP.values()))

        df = df.rename(columns=COLUMN_MAP)

        # 거래금액: " 82,500" → 82500 (만원, nullable 정수)
        if "deal_amount" in df.columns:
            df["deal_amount"] = pd.to_numeric(
                df["deal_amount"].str.replace(",", "", regex=False).str.strip(),
                errors="coerce",
            ).astype("Int64")

        # 결측 가능성이 있어 nullable Int64로 캐스팅
        for col in ("deal_year", "deal_month", "deal_day", "build_year", "floor"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

        if "area" in df.columns:
            df["area"] = pd.to_numeric(df["area"], errors="coerce")  # float ㎡

        for col in ("legal_dong", "apt_name", "jibun"):
            if col in df.columns:
                df[col] = df[col].str.strip()

        return df

    @staticmethod
    def _validate_region_code(code: str) -> None:
        """region_code가 5자리 숫자인지 검증."""
        if not (isinstance(code, str) and len(code) == 5 and code.isdigit()):
            raise ValueError(f"region_code는 5자리 숫자 문자열이어야 합니다: {code}")

    @staticmethod
    def _validate_year_month(ym: str) -> None:
        """year_month가 'YYYYMM' 형식인지 검증."""
        if not (isinstance(ym, str) and len(ym) == 6 and ym.isdigit()):
            raise ValueError(f"year_month는 'YYYYMM' 형식이어야 합니다: {ym}")


# ----------------------------------------------------------------------
# MOLIT → 내부 컬럼 매핑 (신 엔드포인트 apis.data.go.kr/1613000 영문 태그)
# ----------------------------------------------------------------------
COLUMN_MAP = {
    "dealAmount": "deal_amount",    # 거래금액(만원, 콤마 포함 문자열)
    "dealingGbn": "deal_type",      # 거래유형(중개거래/직거래)
    "buildYear": "build_year",      # 건축년도
    "dealYear": "deal_year",        # 년
    "dealMonth": "deal_month",      # 월
    "dealDay": "deal_day",          # 일
    "umdNm": "legal_dong",          # 법정동(읍면동명)
    "aptNm": "apt_name",            # 단지명
    "excluUseAr": "area",           # 전용면적(㎡)
    "jibun": "jibun",               # 지번
    "sggCd": "region_code",         # 시군구코드 5자리
    "floor": "floor",               # 층
    "cdealDay": "cancel_date",      # 해제사유발생일
    "cdealType": "cancel_flag",     # 해제여부('O')
    # --- 신 API 추가 필드 ---
    "aptDong": "apt_dong",          # 동
    "buyerGbn": "buyer_type",       # 매수자 구분(개인/법인 등)
    "slerGbn": "seller_type",       # 매도자 구분
    "estateAgentSggNm": "agent_sgg",  # 중개사 소재지(시군구)
    "rgstDate": "register_date",    # 등기일자
    "landLeaseholdGbn": "land_leasehold",  # 토지임대부 여부
    "roadNm": "road_name",          # 도로명
}


# ----------------------------------------------------------------------
# CSV 내보내기
# ----------------------------------------------------------------------
def export_chunked_csv(
    df: pd.DataFrame,
    out_dir: Union[str, Path],
    chunk_size: int = 50,
    prefix: str = "molit",
    encoding: str = "utf-8-sig",
) -> list[Path]:
    """DataFrame을 chunk_size 행 단위로 분할하여 여러 CSV 파일로 저장.

    파일명은 ``{prefix}_{0001}.csv`` 형태로 0-padding된 순번을 가진다.
    한국어 Windows·Excel 호환을 위해 기본 인코딩은 utf-8-sig(BOM 포함)이다.

    Args:
        df: 저장할 DataFrame
        out_dir: 저장 디렉터리 (없으면 생성)
        chunk_size: 파일당 행 수 (기본 50, 양의 정수)
        prefix: 파일명 접두사
        encoding: 파일 인코딩 (기본 'utf-8-sig')

    Returns:
        기록된 CSV 파일 경로 리스트. df가 비어 있으면 빈 리스트.

    Raises:
        ValueError: chunk_size가 1 미만일 때
    """
    if chunk_size < 1:
        raise ValueError(f"chunk_size는 1 이상이어야 합니다: {chunk_size}")

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    if df.empty:
        logger.warning("저장할 데이터가 없습니다 (빈 DataFrame). out_dir=%s", out_path)
        return []

    n_chunks = math.ceil(len(df) / chunk_size)
    width = max(4, len(str(n_chunks)))  # 최소 4자리 0-padding

    paths: list[Path] = []
    for i in range(n_chunks):
        chunk = df.iloc[i * chunk_size : (i + 1) * chunk_size]
        file_path = out_path / f"{prefix}_{i + 1:0{width}d}.csv"
        chunk.to_csv(file_path, index=False, encoding=encoding)
        paths.append(file_path)

    logger.info("%d행 → %d개 CSV 파일 저장 (chunk_size=%d): %s",
                len(df), n_chunks, chunk_size, out_path)
    return paths
