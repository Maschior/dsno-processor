"""Tests for dsno_processor.ebs_upload (non-Selenium helpers).

Only tests the pure-Python helpers: history tracking and
``list_local_files``.  Browser-dependent functions are excluded.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dsno_processor.ebs_upload import (
    already_uploaded,
    list_local_files,
    load_history,
    record_success,
    save_history,
)
from dsno_processor.exceptions import ConfigurationError


# ── History helpers ──────────────────────────────────────────────────


class TestUploadHistoryHelpers:
    """Tests for load/save/record/already helpers (upload variant)."""

    def test_load_empty_history(self, tmp_path: Path):
        history = load_history(str(tmp_path))
        assert history == {}

    def test_save_and_load_round_trip(self, tmp_path: Path):
        data = {"file.txt": {"status": "success", "date": "2026-01-01"}}
        save_history(data, str(tmp_path))
        loaded = load_history(str(tmp_path))
        assert loaded == data

    def test_record_success_marks_file(self, tmp_path: Path):
        history: dict = {}
        record_success(history, "DSNO_001.txt", str(tmp_path))
        assert history["DSNO_001.txt"]["status"] == "success"

    def test_already_uploaded_success(self):
        history = {"f.txt": {"status": "success"}}
        assert already_uploaded(history, "f.txt") is True

    def test_already_uploaded_legacy_sucesso(self):
        history = {"f.txt": {"status": "sucesso"}}
        assert already_uploaded(history, "f.txt") is True

    def test_not_yet_uploaded(self):
        assert already_uploaded({}, "f.txt") is False

    def test_load_corrupted_history(self, tmp_path: Path):
        path = tmp_path / "historico_uploads.json"
        path.write_text("{bad json", encoding="utf-8")
        with pytest.raises(ConfigurationError, match="Malformed"):
            load_history(str(tmp_path))


# ── list_local_files ─────────────────────────────────────────────────


class TestListLocalFiles:
    """Tests for list_local_files."""

    def test_lists_regular_files(self, tmp_path: Path):
        (tmp_path / "DSNO_001.txt").write_text("data", encoding="utf-8")
        (tmp_path / "DSNO_002.txt").write_text("data", encoding="utf-8")
        files = list_local_files(str(tmp_path))
        assert len(files) == 2
        assert "DSNO_001.txt" in files
        assert "DSNO_002.txt" in files

    def test_ignores_history_json(self, tmp_path: Path):
        (tmp_path / "DSNO_001.txt").write_text("data", encoding="utf-8")
        (tmp_path / "historico_uploads.json").write_text("{}", encoding="utf-8")
        (tmp_path / "historico_downloads.json").write_text("{}", encoding="utf-8")
        files = list_local_files(str(tmp_path))
        assert len(files) == 1
        assert "DSNO_001.txt" in files

    def test_ignores_subdirectories(self, tmp_path: Path):
        (tmp_path / "DSNO_001.txt").write_text("data", encoding="utf-8")
        (tmp_path / "subdir").mkdir()
        files = list_local_files(str(tmp_path))
        assert len(files) == 1

    def test_directory_not_found(self):
        with pytest.raises(FileNotFoundError, match="not found"):
            list_local_files("/nonexistent/path/xyz")

    def test_empty_directory_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="No files"):
            list_local_files(str(tmp_path))

    def test_only_history_files_raises(self, tmp_path: Path):
        (tmp_path / "historico_uploads.json").write_text("{}", encoding="utf-8")
        with pytest.raises(FileNotFoundError, match="No files"):
            list_local_files(str(tmp_path))
