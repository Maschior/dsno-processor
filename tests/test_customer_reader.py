"""Tests for dsno_processor.customer_reader.

Like ``control_reader``, this module calls ``load_config()`` at import-time.
We monkeypatch the module-level column constants directly.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from dsno_processor.exceptions import ColumnMissingError, SheetNotFoundError
from dsno_processor.models import DsnoInfo


# ── Helpers ──────────────────────────────────────────────────────────


def _patch_customer_constants():
    """Context-manager that patches module-level column names."""
    import dsno_processor.customer_reader as cust

    return patch.multiple(
        cust,
        _INVOICE_COL="INVOICE",
        _CONTAINER_COL="CONTAINER",
        _BOOKING_COL="BOOKING/HAWB",
        _REQUIRED_COLUMNS={"INVOICE", "BOOKING/HAWB"},
    )


# ── read_customer_sheet ──────────────────────────────────────────────


class TestReadCustomerSheet:
    """Tests for read_customer_sheet."""

    def test_reads_excel_and_normalizes_columns(self, tmp_path: Path):
        df = pd.DataFrame({"  Invoice  ": [1], " Booking ": ["bk"]})
        path = tmp_path / "cust.xlsx"
        df.to_excel(path, index=False)

        from dsno_processor.customer_reader import read_customer_sheet

        with patch("dsno_processor.customer_reader.cfg") as mock_cfg:
            mock_cfg.customer_sheet_properties.sheet_name = ""
            result = read_customer_sheet(path)

        assert "INVOICE" in result.columns
        assert "BOOKING" in result.columns

    def test_file_not_found(self, tmp_path: Path):
        from dsno_processor.customer_reader import read_customer_sheet

        with pytest.raises(SheetNotFoundError, match="not found"):
            read_customer_sheet(tmp_path / "missing.xlsx")

    def test_sheet_name_not_found(self, tmp_path: Path):
        df = pd.DataFrame({"A": [1]})
        path = tmp_path / "cust.xlsx"
        df.to_excel(path, index=False, sheet_name="Sheet1")

        from dsno_processor.customer_reader import read_customer_sheet

        with patch("dsno_processor.customer_reader.cfg") as mock_cfg:
            mock_cfg.customer_sheet_properties.sheet_name = "NonExistentSheet"
            with pytest.raises(SheetNotFoundError, match="not found"):
                read_customer_sheet(path)


# ── get_dsno_info ────────────────────────────────────────────────────


class TestGetDsnoInfo:
    """Tests for get_dsno_info."""

    def test_returns_dsno_info(self, customer_sheet_df: pd.DataFrame):
        with _patch_customer_constants():
            from dsno_processor.customer_reader import get_dsno_info

            info = get_dsno_info(100001, customer_sheet_df)
            assert info is not None
            assert isinstance(info, DsnoInfo)
            assert info.invoice == "100001"
            assert info.booking == "BK-001"
            assert info.container == "CNT-001"

    def test_returns_none_when_not_found(self, customer_sheet_df: pd.DataFrame):
        with _patch_customer_constants():
            from dsno_processor.customer_reader import get_dsno_info

            result = get_dsno_info(999999, customer_sheet_df)
            assert result is None

    def test_missing_columns_raises(self):
        df = pd.DataFrame({"OTHER_COL": [1, 2]})
        with _patch_customer_constants():
            from dsno_processor.customer_reader import get_dsno_info

            with pytest.raises(ColumnMissingError, match="Missing columns"):
                get_dsno_info(1, df)

    def test_container_optional(self):
        """If CONTAINER column is missing, container should be empty string."""
        df = pd.DataFrame(
            {
                "INVOICE": [100001],
                "BOOKING/HAWB": ["BK-001"],
            }
        )
        with _patch_customer_constants():
            from dsno_processor.customer_reader import get_dsno_info

            info = get_dsno_info(100001, df)
            assert info is not None
            assert info.container == ""

    def test_returns_first_match_on_duplicates(self):
        df = pd.DataFrame(
            {
                "INVOICE": [100001, 100001],
                "BOOKING/HAWB": ["BK-FIRST", "BK-SECOND"],
                "CONTAINER": ["CNT-1", "CNT-2"],
            }
        )
        with _patch_customer_constants():
            from dsno_processor.customer_reader import get_dsno_info

            info = get_dsno_info(100001, df)
            assert info is not None
            assert info.booking == "BK-FIRST"
