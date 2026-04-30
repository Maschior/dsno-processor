"""Tests for dsno_processor.editor."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from dsno_processor.editor import (
    edit_field,
    edit_navstar_dsno,
    get_size,
    move_to_processed,
    normalize_file,
)
from dsno_processor.exceptions import DsnoFileError
from dsno_processor.models import DsnoInfo


# ── Helpers ──────────────────────────────────────────────────────────


def _write_file(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


# ── edit_field ───────────────────────────────────────────────────────


class TestEditField:
    """Tests for the low-level edit_field function."""

    def test_basic_replacement(self, tmp_path: Path):
        fp = _write_file(tmp_path / "f.txt", "AAABBBCCC\n")
        result = edit_field(fp, "AAA", 4, 6, "XXX")
        assert result is True
        assert fp.read_text(encoding="utf-8").startswith("AAAXXXCCC")

    def test_pads_short_content(self, tmp_path: Path):
        fp = _write_file(tmp_path / "f.txt", "AAABBBCCC\n")
        result = edit_field(fp, "AAA", 4, 6, "X")
        text = fp.read_text(encoding="utf-8")
        # "X" should be padded to 3 characters
        assert text.startswith("AAAX  CCC")
        assert result is True

    def test_truncates_long_content(self, tmp_path: Path):
        fp = _write_file(tmp_path / "f.txt", "AAABBBCCC\n")
        result = edit_field(fp, "AAA", 4, 6, "XXXXX")
        text = fp.read_text(encoding="utf-8")
        # "XXXXX" truncated to 3 characters
        assert text.startswith("AAAXXXCCC")
        assert result is True

    def test_no_match_returns_false(self, tmp_path: Path):
        fp = _write_file(tmp_path / "f.txt", "AAABBBCCC\n")
        result = edit_field(fp, "ZZZZZ", 4, 6, "X")
        assert result is False

    def test_file_not_found(self, tmp_path: Path):
        fp = tmp_path / "nonexistent.txt"
        with pytest.raises(DsnoFileError, match="not found"):
            edit_field(fp, "A", 1, 3, "X")

    def test_invalid_column_range(self, tmp_path: Path):
        fp = _write_file(tmp_path / "f.txt", "AAABBB\n")
        with pytest.raises(ValueError, match="Invalid column range"):
            edit_field(fp, "A", 5, 3, "X")

    def test_col_start_zero(self, tmp_path: Path):
        fp = _write_file(tmp_path / "f.txt", "AAABBB\n")
        with pytest.raises(ValueError, match="Invalid column range"):
            edit_field(fp, "A", 0, 3, "X")

    def test_success_message_logged(self, tmp_path: Path, caplog):
        fp = _write_file(tmp_path / "f.txt", "AAABBBCCC\n")
        import logging
        with caplog.at_level(logging.INFO):
            edit_field(fp, "AAA", 4, 6, "XXX", success_message="Edited!")
        assert "Edited!" in caplog.text

    def test_multiple_matching_lines(self, tmp_path: Path):
        content = "AAABBB\nAAABBB\n"
        fp = _write_file(tmp_path / "f.txt", content)
        edit_field(fp, "AAA", 4, 6, "XXX")
        lines = fp.read_text(encoding="utf-8").splitlines()
        assert lines[0].startswith("AAAXXX")
        assert lines[1].startswith("AAAXXX")


# ── normalize_file ───────────────────────────────────────────────────


class TestNormalizeFile:
    """Tests for normalize_file."""

    def test_replaces_accented_characters(self, tmp_path: Path):
        fp = _write_file(tmp_path / "f.txt", "Héllo Wörld Ação\n")
        result = normalize_file(fp)
        assert result is True
        text = fp.read_text(encoding="utf-8")
        assert "Hello World Acao" in text

    def test_ascii_unchanged(self, tmp_path: Path):
        fp = _write_file(tmp_path / "f.txt", "Hello World\n")
        normalize_file(fp)
        assert "Hello World" in fp.read_text(encoding="utf-8")

    def test_file_not_found(self, tmp_path: Path):
        with pytest.raises(DsnoFileError, match="not found"):
            normalize_file(tmp_path / "nope.txt")


# ── move_to_processed ────────────────────────────────────────────────


class TestMoveToProcessed:
    """Tests for move_to_processed."""

    def test_moves_file(self, tmp_path: Path):
        fp = _write_file(tmp_path / "file.txt", "content")
        dest_dir = tmp_path / "Processed"
        result = move_to_processed(fp, dest_dir)
        assert result is True
        assert not fp.exists()
        assert (dest_dir / "file.txt").exists()

    def test_creates_destination_dir(self, tmp_path: Path):
        fp = _write_file(tmp_path / "file.txt", "content")
        dest_dir = tmp_path / "deep" / "nested" / "Processed"
        move_to_processed(fp, dest_dir)
        assert dest_dir.is_dir()

    def test_file_not_found(self, tmp_path: Path):
        with pytest.raises(DsnoFileError, match="not found"):
            move_to_processed(tmp_path / "nope.txt", tmp_path / "Processed")


# ── get_size ─────────────────────────────────────────────────────────


class TestGetSize:
    """Tests for get_size."""

    def test_returns_correct_size(self, tmp_path: Path):
        fp = _write_file(tmp_path / "f.txt", "hello")
        assert get_size(fp) == 5

    def test_empty_file(self, tmp_path: Path):
        fp = tmp_path / "empty.txt"
        fp.write_bytes(b"")
        assert get_size(fp) == 0

    def test_file_not_found(self, tmp_path: Path):
        with pytest.raises(DsnoFileError, match="not found"):
            get_size(tmp_path / "nope.txt")


# ── edit_navstar_dsno ────────────────────────────────────────────────


class TestEditNavstarDsno:
    """Tests for the composite edit_navstar_dsno function."""

    def test_applies_all_edits(self, dsno_file: Path):
        info = DsnoInfo(invoice="INV-999", container="CNT-TEST", booking="BK-TEST")
        result = edit_navstar_dsno(dsno_file, info)
        assert result is True
        content = dsno_file.read_text(encoding="utf-8")
        assert "BK-TEST" in content
        assert "INV-999" in content
        assert "CNT-TEST" in content
