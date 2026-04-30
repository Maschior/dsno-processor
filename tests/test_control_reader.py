"""Tests for dsno_processor.control_reader.

The ``control_reader`` module calls ``load_config()`` at import-time to
set module-level column name constants.  We monkeypatch those constants
directly so the tests don't depend on a real ``config.toml``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from dsno_processor.exceptions import ColumnMissingError, SheetNotFoundError
from dsno_processor.models import DateRange


# ── Helpers ──────────────────────────────────────────────────────────


def _patch_column_constants():
    """Decorator / context-manager that patches module-level column names."""
    import dsno_processor.control_reader as cr

    return patch.multiple(
        cr,
        _DATE_COL="CREATION_DATE",
        _DSNO_COL="ARGUMENT2",
        _INVOICE_COL="INVOICE",
        _STATUS_COL="STATUS",
        _FREIGHT_ORACLE_COL="FREIGHT_ORACLE",
        _FREIGHT_SOFTWAY_COL="FREIGHT_SOFTWAY",
        _REQUIRED_COLUMNS={
            "CREATION_DATE",
            "ARGUMENT2",
            "INVOICE",
            "STATUS",
            "FREIGHT_ORACLE",
            "FREIGHT_SOFTWAY",
        },
    )


# ── read_control_sheet ───────────────────────────────────────────────


class TestReadControlSheet:
    """Tests for read_control_sheet."""

    def test_reads_excel_and_normalizes_columns(self, tmp_path: Path):
        df = pd.DataFrame({"  invoice  ": [1], " dsno ": ["x"]})
        path = tmp_path / "ctrl.xlsx"
        df.to_excel(path, index=False)

        from dsno_processor.control_reader import read_control_sheet

        result = read_control_sheet(path)
        # Columns should be stripped and uppercased
        assert "INVOICE" in result.columns
        assert "DSNO" in result.columns

    def test_file_not_found(self, tmp_path: Path):
        from dsno_processor.control_reader import read_control_sheet

        with pytest.raises(SheetNotFoundError, match="not found"):
            read_control_sheet(tmp_path / "missing.xlsx")


# ── get_status_options ───────────────────────────────────────────────


class TestGetStatusOptions:
    """Tests for get_status_options."""

    def test_returns_sorted_unique(self, control_sheet_df: pd.DataFrame):
        with _patch_column_constants():
            from dsno_processor.control_reader import get_status_options

            opts = get_status_options(control_sheet_df)
            assert opts == ["Open", "Processed"]

    def test_returns_empty_if_less_than_two(self):
        df = pd.DataFrame({"STATUS": ["Open", "Open"]})
        with _patch_column_constants():
            from dsno_processor.control_reader import get_status_options

            assert get_status_options(df) == []

    def test_returns_empty_on_missing_column(self):
        df = pd.DataFrame({"OTHER": [1, 2]})
        with _patch_column_constants():
            from dsno_processor.control_reader import get_status_options

            assert get_status_options(df) == []


# ── get_invoice_dsno_pairs ───────────────────────────────────────────


class TestGetInvoiceDsnoPairs:
    """Tests for get_invoice_dsno_pairs."""

    def test_filters_by_date_range(self, control_sheet_df: pd.DataFrame):
        with _patch_column_constants():
            from dsno_processor.control_reader import get_invoice_dsno_pairs

            dr = DateRange.from_string("14/01/2026;17/01/2026")
            pairs = get_invoice_dsno_pairs(dr, control_sheet_df)
            invoices = [p[0] for p in pairs]
            assert 100001 in invoices
            assert 100002 in invoices
            assert 100003 not in invoices  # Feb 1 is outside range

    def test_filters_by_status(self, control_sheet_df: pd.DataFrame):
        with _patch_column_constants():
            from dsno_processor.control_reader import get_invoice_dsno_pairs

            dr = DateRange.from_string("01/01/2026;28/02/2026")
            pairs = get_invoice_dsno_pairs(
                dr, control_sheet_df, status_filter=["Open"]
            )
            invoices = [p[0] for p in pairs]
            assert 100001 in invoices
            assert 100003 in invoices
            # "Processed" status should be excluded
            assert 100002 not in invoices

    def test_no_filter_returns_all(self, control_sheet_df: pd.DataFrame):
        with _patch_column_constants():
            from dsno_processor.control_reader import get_invoice_dsno_pairs

            dr = DateRange.from_string("01/01/2026;28/02/2026")
            pairs = get_invoice_dsno_pairs(dr, control_sheet_df, status_filter=None)
            assert len(pairs) == 3

    def test_missing_columns_raises(self):
        df = pd.DataFrame({"INVOICE": [1], "ARGUMENT2": ["x"]})
        with _patch_column_constants():
            from dsno_processor.control_reader import get_invoice_dsno_pairs

            dr = DateRange.from_string("01/01/2026;31/12/2026")
            with pytest.raises(ColumnMissingError, match="Missing columns"):
                get_invoice_dsno_pairs(dr, df)

    def test_returns_four_element_tuples(self, control_sheet_df: pd.DataFrame):
        with _patch_column_constants():
            from dsno_processor.control_reader import get_invoice_dsno_pairs

            dr = DateRange.from_string("01/01/2026;28/02/2026")
            pairs = get_invoice_dsno_pairs(dr, control_sheet_df)
            for invoice, dsno, oracle_f, softway_f in pairs:
                assert isinstance(dsno, str)
