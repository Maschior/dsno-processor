"""Tests for dsno_processor.processor."""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dsno_processor.exceptions import CanceledError
from dsno_processor.models import FreightMode, ProcessingResult


# ── _resolve_freight ─────────────────────────────────────────────────


class TestResolveFreight:
    """Tests for the _resolve_freight helper."""

    def _resolve(self, oracle, softway, mode: FreightMode):
        from dsno_processor.processor import _resolve_freight

        return _resolve_freight(oracle, softway, mode)

    # -- AIR mode --

    def test_air_with_softway_available(self):
        value, error = self._resolve("100", "110", FreightMode.AIR)
        assert value == "110"
        assert error is None

    def test_air_without_softway_fallback_to_oracle(self):
        value, error = self._resolve("100", None, FreightMode.AIR)
        assert value == "100"
        assert error is not None  # warning about fallback

    def test_air_without_softway_nan(self):
        value, error = self._resolve("100", "nan", FreightMode.AIR)
        assert value == "100"
        assert error is not None

    # -- SEA mode --

    def test_sea_softway_differs_from_oracle(self):
        value, error = self._resolve("100", "110", FreightMode.SEA)
        assert value == "110"
        assert error is None

    def test_sea_softway_equals_oracle(self):
        value, error = self._resolve("100", "100", FreightMode.SEA)
        assert value == "100"
        assert error is None

    def test_sea_no_softway(self):
        value, error = self._resolve("100", None, FreightMode.SEA)
        assert value == "100"
        assert error is None

    # -- Both empty --

    def test_both_empty(self):
        value, error = self._resolve(None, None, FreightMode.AIR)
        assert value == "AIR"
        assert error is None

    def test_both_nan_strings(self):
        value, error = self._resolve("nan", "nan", FreightMode.SEA)
        assert value == "SEA"
        assert error is None

    # -- ROAD mode (unhandled → fallback) --

    def test_road_with_softway(self):
        value, error = self._resolve("100", "110", FreightMode.ROAD)
        assert value == "110"
        assert error is not None  # warning about unhandled mode

    def test_road_without_softway(self):
        value, error = self._resolve("100", None, FreightMode.ROAD)
        assert value == "100"
        assert error is not None


# ── _process_single_dsno ─────────────────────────────────────────────


class TestProcessSingleDsno:
    """Tests for _process_single_dsno."""

    def _process(self, invoice, dsno_path, customer_sheet_path):
        from dsno_processor.processor import _process_single_dsno

        return _process_single_dsno(invoice, dsno_path, customer_sheet_path)

    @patch("dsno_processor.processor.get_size")
    @patch("dsno_processor.processor.normalize_file")
    @patch("dsno_processor.processor.edit_navstar_dsno")
    @patch("dsno_processor.processor.get_dsno_info")
    @patch("dsno_processor.processor.read_customer_sheet")
    def test_success(
        self,
        mock_read,
        mock_info,
        mock_edit,
        mock_normalize,
        mock_size,
        tmp_path: Path,
    ):
        dsno_path = tmp_path / "DSNO.txt"
        dsno_path.write_text("content", encoding="utf-8")

        mock_read.return_value = MagicMock()
        mock_info.return_value = MagicMock(
            invoice="100", container="CNT", booking="BK"
        )
        mock_size.side_effect = [10, 20]  # original then new (different)

        result = self._process(100, dsno_path, "cust.xlsx")
        assert result is None  # None means success

    @patch("dsno_processor.processor.read_customer_sheet")
    @patch("dsno_processor.processor.get_dsno_info")
    def test_invoice_not_found(self, mock_info, mock_read, tmp_path):
        mock_read.return_value = MagicMock()
        mock_info.return_value = None
        result = self._process(999, tmp_path / "x.txt", "cust.xlsx")
        assert "not found" in result.lower()

    @patch("dsno_processor.processor.read_customer_sheet")
    @patch("dsno_processor.processor.get_dsno_info")
    def test_missing_booking(self, mock_info, mock_read, tmp_path):
        mock_read.return_value = MagicMock()
        mock_info.return_value = MagicMock(
            invoice="100", container="CNT", booking="nan"
        )
        result = self._process(100, tmp_path / "x.txt", "cust.xlsx")
        assert "booking" in result.lower()

    @patch("dsno_processor.processor.get_size")
    @patch("dsno_processor.processor.normalize_file")
    @patch("dsno_processor.processor.edit_navstar_dsno")
    @patch("dsno_processor.processor.get_dsno_info")
    @patch("dsno_processor.processor.read_customer_sheet")
    def test_file_not_found(
        self, mock_read, mock_info, mock_edit, mock_normalize, mock_size
    ):
        mock_read.return_value = MagicMock()
        mock_info.return_value = MagicMock(
            invoice="100", container="CNT", booking="BK"
        )
        result = self._process(100, Path("/nonexistent/DSNO.txt"), "cust.xlsx")
        assert "not found" in result.lower()

    @patch("dsno_processor.processor.get_size")
    @patch("dsno_processor.processor.normalize_file")
    @patch("dsno_processor.processor.edit_navstar_dsno")
    @patch("dsno_processor.processor.get_dsno_info")
    @patch("dsno_processor.processor.read_customer_sheet")
    def test_unchanged_file_size(
        self,
        mock_read,
        mock_info,
        mock_edit,
        mock_normalize,
        mock_size,
        tmp_path: Path,
    ):
        dsno = tmp_path / "DSNO.txt"
        dsno.write_text("content", encoding="utf-8")
        mock_read.return_value = MagicMock()
        mock_info.return_value = MagicMock(
            invoice="100", container="CNT", booking="BK"
        )
        mock_size.side_effect = [10, 10]  # same size

        result = self._process(100, dsno, "cust.xlsx")
        assert "unchanged" in result.lower()


# ── process_dsno (public API) ────────────────────────────────────────


class TestProcessDsno:
    """Tests for the public process_dsno function."""

    @patch("dsno_processor.processor.update_control_sheet_status")
    @patch("dsno_processor.processor.move_to_processed")
    @patch("dsno_processor.processor._process_single_dsno")
    @patch("dsno_processor.processor.get_invoice_dsno_pairs")
    @patch("dsno_processor.processor.read_control_sheet")
    @patch("dsno_processor.processor.setup_logger")
    def test_full_success_flow(
        self,
        mock_logger,
        mock_read_ctrl,
        mock_pairs,
        mock_single,
        mock_move,
        mock_update,
        tmp_path: Path,
    ):
        mock_read_ctrl.return_value = MagicMock()
        mock_pairs.return_value = [
            (100001, "DSNO_001.txt", 100, 110),
            (100002, "DSNO_002.txt", 200, 200),
        ]
        mock_single.return_value = None  # success

        from dsno_processor.processor import process_dsno

        result = process_dsno(
            date_range="01/01/2026;31/01/2026",
            customer_sheet="cust.xlsx",
            control_sheet="ctrl.xlsx",
            dsno_dir=str(tmp_path),
            freight_mode="SEA",
            status_filter=[],
        )

        assert isinstance(result, ProcessingResult)
        assert result.total == 2
        assert result.success == 2
        assert result.failed == 0

    @patch("dsno_processor.processor.read_control_sheet")
    @patch("dsno_processor.processor.get_invoice_dsno_pairs")
    @patch("dsno_processor.processor.setup_logger")
    def test_no_pairs_found(
        self, mock_logger, mock_pairs, mock_read_ctrl, tmp_path: Path
    ):
        mock_read_ctrl.return_value = MagicMock()
        mock_pairs.return_value = []

        from dsno_processor.processor import process_dsno

        result = process_dsno(
            date_range="01/01/2026;31/01/2026",
            customer_sheet="cust.xlsx",
            control_sheet="ctrl.xlsx",
            dsno_dir=str(tmp_path),
            status_filter=[],
        )
        assert result.total == 0

    @patch("dsno_processor.processor.read_control_sheet")
    @patch("dsno_processor.processor.setup_logger")
    def test_cancel_before_reading(self, mock_logger, mock_read_ctrl, tmp_path: Path):
        cancel = threading.Event()
        cancel.set()

        from dsno_processor.processor import process_dsno

        with pytest.raises(CanceledError):
            process_dsno(
                date_range="01/01/2026;31/01/2026",
                customer_sheet="cust.xlsx",
                control_sheet="ctrl.xlsx",
                dsno_dir=str(tmp_path),
                cancel_event=cancel,
                status_filter=[],
            )

    @patch("dsno_processor.processor.update_control_sheet_status")
    @patch("dsno_processor.processor.move_to_processed")
    @patch("dsno_processor.processor._process_single_dsno")
    @patch("dsno_processor.processor.get_invoice_dsno_pairs")
    @patch("dsno_processor.processor.read_control_sheet")
    @patch("dsno_processor.processor.setup_logger")
    def test_errors_tracked(
        self,
        mock_logger,
        mock_read_ctrl,
        mock_pairs,
        mock_single,
        mock_move,
        mock_update,
        tmp_path: Path,
    ):
        mock_read_ctrl.return_value = MagicMock()
        mock_pairs.return_value = [
            (100001, "DSNO_001.txt", 100, 110),
        ]
        mock_single.return_value = "Something went wrong"

        from dsno_processor.processor import process_dsno

        result = process_dsno(
            date_range="01/01/2026;31/01/2026",
            customer_sheet="cust.xlsx",
            control_sheet="ctrl.xlsx",
            dsno_dir=str(tmp_path),
            status_filter=[],
        )
        assert result.total == 1
        assert result.success == 0
        assert result.failed == 1
        assert len(result.errors) == 1

    @patch("dsno_processor.processor.setup_logger")
    def test_invalid_status_filter_type(self, mock_logger, tmp_path: Path):
        from dsno_processor.processor import process_dsno

        with pytest.raises(ValueError, match="status_filter must be a list"):
            process_dsno(
                date_range="01/01/2026;31/01/2026",
                customer_sheet="cust.xlsx",
                control_sheet="ctrl.xlsx",
                dsno_dir=str(tmp_path),
                status_filter="Open",  # type: ignore[arg-type]
            )

    @patch("dsno_processor.processor.update_control_sheet_status")
    @patch("dsno_processor.processor.move_to_processed")
    @patch("dsno_processor.processor._process_single_dsno")
    @patch("dsno_processor.processor.get_invoice_dsno_pairs")
    @patch("dsno_processor.processor.read_control_sheet")
    @patch("dsno_processor.processor.setup_logger")
    def test_progress_callback_called(
        self,
        mock_logger,
        mock_read_ctrl,
        mock_pairs,
        mock_single,
        mock_move,
        mock_update,
        tmp_path: Path,
    ):
        mock_read_ctrl.return_value = MagicMock()
        mock_pairs.return_value = [(100001, "DSNO_001.txt", 100, 110)]
        mock_single.return_value = None

        callback = MagicMock()

        from dsno_processor.processor import process_dsno

        process_dsno(
            date_range="01/01/2026;31/01/2026",
            customer_sheet="cust.xlsx",
            control_sheet="ctrl.xlsx",
            dsno_dir=str(tmp_path),
            progress_callback=callback,
            status_filter=[],
        )

        # Callback should have been called with various events
        events = [call[0][0] for call in callback.call_args_list]
        assert "phase" in events
        assert "total" in events
        assert "finished" in events
