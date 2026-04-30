"""Tests for dsno_processor.status_updater."""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

from dsno_processor.status_updater import update_control_sheet_status


# ── Helpers ──────────────────────────────────────────────────────────


def _create_control_excel(
    path: Path,
    rows: list[tuple[str, str | None]],
) -> Path:
    """Create a minimal control sheet Excel file.

    Each row is ``(dsno_filename, current_status)``.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["ARGUMENT2", "STATUS"])
    for dsno, status in rows:
        ws.append([dsno, status])
    wb.save(path)
    return path


def _create_processed_dir(base: Path, filenames: list[str]) -> Path:
    """Create a Processed directory containing the given dummy files."""
    processed = base / "Processed"
    processed.mkdir(parents=True, exist_ok=True)
    for fn in filenames:
        (processed / fn).write_text("dummy", encoding="utf-8")
    return processed


# ── Tests ────────────────────────────────────────────────────────────


class TestUpdateControlSheetStatus:
    """Tests for update_control_sheet_status."""

    def test_updates_matching_rows(self, tmp_path: Path):
        ctrl = _create_control_excel(
            tmp_path / "ctrl.xlsx",
            [
                ("DSNO_001.txt", "Open"),
                ("DSNO_002.txt", "Open"),
                ("DSNO_003.txt", "Open"),
            ],
        )
        processed = _create_processed_dir(tmp_path, ["DSNO_001.txt", "DSNO_003.txt"])

        count = update_control_sheet_status(ctrl, processed)
        assert count == 2

        # Verify in the Excel file
        wb = openpyxl.load_workbook(ctrl)
        ws = wb.active
        statuses = {ws.cell(r, 1).value: ws.cell(r, 2).value for r in range(2, 5)}
        assert statuses["DSNO_001.txt"] == "Processed"
        assert statuses["DSNO_002.txt"] == "Open"
        assert statuses["DSNO_003.txt"] == "Processed"

    def test_already_processed_not_counted(self, tmp_path: Path):
        ctrl = _create_control_excel(
            tmp_path / "ctrl.xlsx",
            [("DSNO_001.txt", "Processed")],
        )
        processed = _create_processed_dir(tmp_path, ["DSNO_001.txt"])
        count = update_control_sheet_status(ctrl, processed)
        assert count == 0

    def test_empty_processed_dir(self, tmp_path: Path):
        ctrl = _create_control_excel(
            tmp_path / "ctrl.xlsx",
            [("DSNO_001.txt", "Open")],
        )
        processed = _create_processed_dir(tmp_path, [])
        count = update_control_sheet_status(ctrl, processed)
        assert count == 0

    def test_control_sheet_not_found(self, tmp_path: Path):
        processed = _create_processed_dir(tmp_path, ["DSNO_001.txt"])
        count = update_control_sheet_status(tmp_path / "nope.xlsx", processed)
        assert count == 0

    def test_processed_dir_not_found(self, tmp_path: Path):
        ctrl = _create_control_excel(
            tmp_path / "ctrl.xlsx",
            [("DSNO_001.txt", "Open")],
        )
        count = update_control_sheet_status(ctrl, tmp_path / "missing")
        assert count == 0

    def test_creates_backup(self, tmp_path: Path):
        ctrl = _create_control_excel(
            tmp_path / "ctrl.xlsx",
            [("DSNO_001.txt", "Open")],
        )
        processed = _create_processed_dir(tmp_path, ["DSNO_001.txt"])
        update_control_sheet_status(ctrl, processed)

        backup_dir = tmp_path / "control_sheet_backups"
        assert backup_dir.exists()
        backups = list(backup_dir.glob("ctrl_*.xlsx"))
        assert len(backups) == 1

    def test_adds_status_column_if_missing(self, tmp_path: Path):
        """If the STATUS column doesn't exist, it should be created."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["ARGUMENT2"])
        ws.append(["DSNO_001.txt"])
        ctrl = tmp_path / "ctrl.xlsx"
        wb.save(ctrl)

        processed = _create_processed_dir(tmp_path, ["DSNO_001.txt"])
        count = update_control_sheet_status(ctrl, processed)
        assert count == 1

        wb2 = openpyxl.load_workbook(ctrl)
        ws2 = wb2.active
        # STATUS column should have been added
        headers = [ws2.cell(1, c).value for c in range(1, ws2.max_column + 1)]
        assert "STATUS" in headers
