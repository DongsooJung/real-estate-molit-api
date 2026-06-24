"""MOLIT 실거래가 API 클라이언트 테스트.

외부 API를 실제로 호출하지 않고 `requests.get`을 모킹하여
XML 파싱·컬럼 정규화·페이지 순회·에러 처리를 검증한다.
"""
import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

# molit_api만 단독 로드한다. `from hedonic import molit_api`는 패키지 __init__이
# models(geopandas/libpysal/spreg)를 끌어와 데이터 수집 계층 테스트에 불필요한
# 전체 공간계량 스택을 요구하므로, 모듈 파일을 직접 import한다.
_MOLIT_PATH = Path(__file__).resolve().parent.parent / "src" / "hedonic" / "molit_api.py"
_spec = importlib.util.spec_from_file_location("molit_api", _MOLIT_PATH)
molit_api = importlib.util.module_from_spec(_spec)
sys.modules["molit_api"] = molit_api  # @dataclass가 cls.__module__를 조회하므로 선등록
_spec.loader.exec_module(molit_api)

MolitClient = molit_api.MolitClient
MolitQueryParams = molit_api.MolitQueryParams
COLUMN_MAP = molit_api.COLUMN_MAP
export_chunked_csv = molit_api.export_chunked_csv


# ----------------------------------------------------------------------
# XML 픽스처 빌더
# ----------------------------------------------------------------------
def _item_xml(
    deal_amount=" 82,500",
    build_year="2008",
    year="2026",
    month="1",
    day="15",
    legal_dong=" 개포동",
    apt="래미안개포",
    area="84.97",
    jibun="12",
    region="11680",
    floor="10",
    cancel="",
) -> str:
    return f"""
      <item>
        <dealAmount>{deal_amount}</dealAmount>
        <buildYear>{build_year}</buildYear>
        <dealYear>{year}</dealYear>
        <dealMonth>{month}</dealMonth>
        <dealDay>{day}</dealDay>
        <umdNm>{legal_dong}</umdNm>
        <aptNm>{apt}</aptNm>
        <excluUseAr>{area}</excluUseAr>
        <jibun>{jibun}</jibun>
        <sggCd>{region}</sggCd>
        <floor>{floor}</floor>
        <cdealType>{cancel}</cdealType>
      </item>"""


def _response_xml(items: str, result_code: str = "00", total: int = 1) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<response>
  <header><resultCode>{result_code}</resultCode><resultMsg>MSG</resultMsg></header>
  <body>
    <items>{items}</items>
    <numOfRows>1000</numOfRows>
    <pageNo>1</pageNo>
    <totalCount>{total}</totalCount>
  </body>
</response>"""


class _FakeResponse:
    def __init__(self, text: str, status: int = 200):
        self.text = text
        self.content = text.encode("utf-8")
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"status {self.status_code}")


@pytest.fixture
def client():
    return MolitClient(api_key="TESTKEY")


def _patch_get(monkeypatch, responses):
    """requests.get을 순차 응답 리스트로 대체. 호출 인자도 기록."""
    calls = []
    seq = iter(responses)

    def fake_get(url, params=None, timeout=None):
        calls.append({"url": url, "params": params, "timeout": timeout})
        return next(seq)

    monkeypatch.setattr(molit_api.requests, "get", fake_get)
    return calls


# ----------------------------------------------------------------------
# _normalize_columns
# ----------------------------------------------------------------------
class TestNormalizeColumns:
    def test_renames_to_snake_case(self, client):
        raw = pd.DataFrame([{"dealAmount": "82,500", "aptNm": "래미안", "excluUseAr": "84.97"}])
        out = client._normalize_columns(raw)
        assert "deal_amount" in out.columns
        assert "apt_name" in out.columns
        assert "dealAmount" not in out.columns

    def test_deal_amount_comma_and_space_to_int(self, client):
        raw = pd.DataFrame([{"dealAmount": " 82,500"}, {"dealAmount": "1,234,567"}])
        out = client._normalize_columns(raw)
        assert out["deal_amount"].tolist() == [82500, 1234567]
        assert str(out["deal_amount"].dtype) == "Int64"

    def test_numeric_types(self, client):
        raw = pd.DataFrame([{"excluUseAr": "84.97", "floor": "10", "buildYear": "2008"}])
        out = client._normalize_columns(raw)
        assert out["area"].dtype == float
        assert str(out["floor"].dtype) == "Int64"
        assert out["floor"].iloc[0] == 10

    def test_text_whitespace_stripped(self, client):
        raw = pd.DataFrame([{"umdNm": " 개포동 ", "aptNm": " 래미안"}])
        out = client._normalize_columns(raw)
        assert out["legal_dong"].iloc[0] == "개포동"
        assert out["apt_name"].iloc[0] == "래미안"

    def test_empty_df_preserves_schema(self, client):
        out = client._normalize_columns(pd.DataFrame())
        assert list(out.columns) == list(COLUMN_MAP.values())
        assert out.empty


# ----------------------------------------------------------------------
# _call_single_page
# ----------------------------------------------------------------------
class TestCallSinglePage:
    def test_parses_items(self, client, monkeypatch):
        xml = _response_xml(_item_xml() + _item_xml(apt="개포자이"), total=2)
        _patch_get(monkeypatch, [_FakeResponse(xml)])
        df = client._call_single_page(MolitQueryParams("11680", "202601"))
        assert len(df) == 2
        assert "dealAmount" in df.columns  # 정규화 전이라 원본(영문) 태그

    def test_empty_items_returns_empty(self, client, monkeypatch):
        _patch_get(monkeypatch, [_FakeResponse(_response_xml("", total=0))])
        df = client._call_single_page(MolitQueryParams("11680", "202601"))
        assert df.empty

    def test_error_result_code_raises(self, client, monkeypatch):
        xml = _response_xml("", result_code="99")
        _patch_get(monkeypatch, [_FakeResponse(xml)])
        with pytest.raises(RuntimeError, match="99"):
            client._call_single_page(MolitQueryParams("11680", "202601"))

    def test_non_xml_response_raises_runtimeerror(self, client, monkeypatch):
        # 게이트웨이가 평문 'Unauthorized'를 200으로 반환하는 경우
        _patch_get(monkeypatch, [_FakeResponse("Unauthorized")])
        with pytest.raises(RuntimeError, match="파싱 실패"):
            client._call_single_page(MolitQueryParams("11680", "202601"))

    def test_http_error_propagates(self, client, monkeypatch):
        import requests
        _patch_get(monkeypatch, [_FakeResponse("", status=500)])
        with pytest.raises(requests.HTTPError):
            client._call_single_page(MolitQueryParams("11680", "202601"))

    def test_request_params_sent(self, client, monkeypatch):
        calls = _patch_get(monkeypatch, [_FakeResponse(_response_xml(_item_xml()))])
        client._call_single_page(MolitQueryParams("11680", "202601", page_no=3))
        p = calls[0]["params"]
        assert p["LAWD_CD"] == "11680"
        assert p["DEAL_YMD"] == "202601"
        assert p["pageNo"] == 3
        assert p["serviceKey"] == "TESTKEY"


# ----------------------------------------------------------------------
# fetch_transactions
# ----------------------------------------------------------------------
class TestFetchTransactions:
    def test_single_page_normalized(self, client, monkeypatch):
        xml = _response_xml(_item_xml() + _item_xml(apt="개포자이"), total=2)
        _patch_get(monkeypatch, [_FakeResponse(xml)])
        df = client.fetch_transactions("11680", "202601")
        assert len(df) == 2
        assert "deal_amount" in df.columns
        assert df["deal_amount"].iloc[0] == 82500

    def test_pagination_stops_on_short_page(self, client, monkeypatch):
        # 1페이지: 1000건(가득), 2페이지: 1건(미만) → 2페이지에서 종료
        full = "".join(_item_xml() for _ in range(1000))
        page1 = _response_xml(full, total=1001)
        page2 = _response_xml(_item_xml(), total=1001)
        _patch_get(monkeypatch, [_FakeResponse(page1), _FakeResponse(page2)])
        df = client.fetch_transactions("11680", "202601", all_pages=True)
        assert len(df) == 1001

    def test_all_pages_false_fetches_one_page(self, client, monkeypatch):
        full = "".join(_item_xml() for _ in range(1000))
        calls = _patch_get(monkeypatch, [_FakeResponse(_response_xml(full))])
        df = client.fetch_transactions("11680", "202601", all_pages=False)
        assert len(df) == 1000
        assert len(calls) == 1  # 추가 페이지 호출 없음

    def test_empty_result_returns_schema(self, client, monkeypatch):
        _patch_get(monkeypatch, [_FakeResponse(_response_xml("", total=0))])
        df = client.fetch_transactions("11680", "202601")
        assert df.empty
        assert list(df.columns) == list(COLUMN_MAP.values())

    @pytest.mark.parametrize("region", ["1168", "11680A", "116800", 11680])
    def test_invalid_region_code(self, client, region):
        with pytest.raises(ValueError):
            client.fetch_transactions(region, "202601")

    @pytest.mark.parametrize("ym", ["20261", "2026013", "2026AB"])
    def test_invalid_year_month(self, client, ym):
        with pytest.raises(ValueError):
            client.fetch_transactions("11680", ym)


# ----------------------------------------------------------------------
# fetch_multi_period
# ----------------------------------------------------------------------
class TestFetchMultiPeriod:
    def test_combines_regions_and_months(self, client, monkeypatch):
        # 2 지역 × 2 월 = 4 조합, 각 1건 → 4행
        responses = [_FakeResponse(_response_xml(_item_xml())) for _ in range(4)]
        _patch_get(monkeypatch, responses)
        df = client.fetch_multi_period(["11680", "11710"], ["202601", "202602"])
        assert len(df) == 4

    def test_skips_failed_combo(self, client, monkeypatch):
        # 첫 조합은 에러코드, 둘째는 정상 → 1행만 살아남음
        responses = [
            _FakeResponse(_response_xml("", result_code="99")),
            _FakeResponse(_response_xml(_item_xml())),
        ]
        _patch_get(monkeypatch, responses)
        df = client.fetch_multi_period(["11680"], ["202601", "202602"])
        assert len(df) == 1


# ----------------------------------------------------------------------
# 생성자
# ----------------------------------------------------------------------
def test_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("MOLIT_API_KEY", raising=False)
    with pytest.raises(ValueError, match="MOLIT_API_KEY"):
        MolitClient(api_key=None)


# ----------------------------------------------------------------------
# export_chunked_csv
# ----------------------------------------------------------------------
class TestExportChunkedCsv:
    def _df(self, n):
        return pd.DataFrame({"deal_amount": range(n), "apt_name": [f"단지{i}" for i in range(n)]})

    def test_splits_into_chunks_of_50(self, tmp_path):
        paths = export_chunked_csv(self._df(120), tmp_path, chunk_size=50)
        assert len(paths) == 3
        lens = [len(pd.read_csv(p)) for p in paths]
        assert lens == [50, 50, 20]

    def test_exact_multiple(self, tmp_path):
        paths = export_chunked_csv(self._df(100), tmp_path, chunk_size=50)
        assert len(paths) == 2
        assert all(len(pd.read_csv(p)) == 50 for p in paths)

    def test_filenames_zero_padded_and_prefixed(self, tmp_path):
        paths = export_chunked_csv(self._df(60), tmp_path, chunk_size=50, prefix="molit_11680_202601")
        names = sorted(p.name for p in paths)
        assert names == ["molit_11680_202601_0001.csv", "molit_11680_202601_0002.csv"]

    def test_empty_df_writes_nothing(self, tmp_path):
        paths = export_chunked_csv(pd.DataFrame(), tmp_path)
        assert paths == []
        assert list(tmp_path.iterdir()) == []

    def test_creates_missing_dir(self, tmp_path):
        target = tmp_path / "nested" / "out"
        export_chunked_csv(self._df(10), target, chunk_size=50)
        assert target.is_dir()

    def test_invalid_chunk_size(self, tmp_path):
        with pytest.raises(ValueError):
            export_chunked_csv(self._df(10), tmp_path, chunk_size=0)

    def test_utf8_sig_bom_and_korean(self, tmp_path):
        paths = export_chunked_csv(self._df(3), tmp_path, chunk_size=50)
        raw = paths[0].read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf")        # UTF-8 BOM
        assert "단지0" in raw.decode("utf-8-sig")     # 한글 보존


# ----------------------------------------------------------------------
# fetch_and_export (end-to-end, mocked HTTP)
# ----------------------------------------------------------------------
class TestFetchAndExport:
    def test_fetch_then_chunk_to_csv(self, client, monkeypatch, tmp_path):
        # 60건 → chunk 50 → 2개 파일
        items = "".join(_item_xml() for _ in range(60))
        _patch_get(monkeypatch, [_FakeResponse(_response_xml(items, total=60))])
        paths = client.fetch_and_export("11680", "202601", tmp_path, chunk_size=50)
        assert len(paths) == 2
        first = pd.read_csv(paths[0])
        assert "deal_amount" in first.columns        # 정규화된 컬럼으로 저장됨
        assert first["deal_amount"].iloc[0] == 82500
        assert paths[0].name == "molit_11680_202601_0001.csv"

    def test_no_data_no_files(self, client, monkeypatch, tmp_path):
        _patch_get(monkeypatch, [_FakeResponse(_response_xml("", total=0))])
        paths = client.fetch_and_export("11680", "202601", tmp_path)
        assert paths == []
