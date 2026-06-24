"""대시보드 CSV 로더 테스트 (순수 pandas, 오프라인)."""
import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

_LOADER_PATH = Path(__file__).resolve().parent.parent / "dashboard" / "loader.py"
_spec = importlib.util.spec_from_file_location("dashboard_loader", _LOADER_PATH)
loader = importlib.util.module_from_spec(_spec)
sys.modules["dashboard_loader"] = loader
_spec.loader.exec_module(loader)

load_transactions = loader.load_transactions
add_derived = loader.add_derived


def _sample_df():
    return pd.DataFrame(
        {
            "deal_amount": [82500, 120000],
            "deal_year": [2026, 2026],
            "deal_month": [1, 1],
            "deal_day": [15, 3],
            "area": [84.97, 114.5],
            "floor": [10, 2],
            "legal_dong": ["개포동", "역삼동"],
            "region_code": ["11680", "11680"],
        }
    )


class TestAddDerived:
    def test_deal_date_built(self):
        out = add_derived(_sample_df())
        assert out["deal_date"].dt.day.tolist() == [15, 3]
        assert str(out["deal_date"].dtype).startswith("datetime64")

    def test_price_per_sqm(self):
        out = add_derived(_sample_df())
        assert round(out["price_per_sqm"].iloc[0], 1) == round(82500 / 84.97, 1)

    def test_floor_category(self):
        out = add_derived(_sample_df())
        assert list(out["floor_category"]) == ["중층(6-15)", "저층(1-5)"]

    def test_empty_df(self):
        assert add_derived(pd.DataFrame()).empty

    def test_bad_date_becomes_nat(self):
        df = _sample_df()
        df.loc[0, "deal_day"] = 99  # 잘못된 일자
        out = add_derived(df)
        assert pd.isna(out["deal_date"].iloc[0])


class TestLoadTransactions:
    def test_reads_and_concats_csvs(self, tmp_path):
        _sample_df().iloc[:1].to_csv(tmp_path / "a.csv", index=False, encoding="utf-8-sig")
        _sample_df().iloc[1:].to_csv(tmp_path / "b.csv", index=False, encoding="utf-8-sig")
        out = load_transactions(tmp_path)
        assert len(out) == 2
        assert "deal_date" in out.columns

    def test_missing_dir_returns_empty(self, tmp_path):
        assert load_transactions(tmp_path / "nope").empty
