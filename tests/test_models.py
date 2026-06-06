"""Tests for dsno_processor.models."""

from __future__ import annotations

from datetime import datetime

import pytest

from dsno_processor.exceptions import InvalidDateRangeError
from dsno_processor.models import DateRange, DsnoInfo, FreightMode, ProcessingResult


# ── FreightMode ──────────────────────────────────────────────────────


class TestFreightMode:
    """Tests for the FreightMode enum."""

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("AIR", FreightMode.AIR),
            ("air", FreightMode.AIR),
            ("Air", FreightMode.AIR),
            ("SEA", FreightMode.SEA),
            ("sea", FreightMode.SEA),
            ("ROAD", FreightMode.ROAD),
        ],
    )
    def test_from_string_valid(self, raw: str, expected: FreightMode):
        assert FreightMode.from_string(raw) is expected

    def test_from_string_invalid(self):
        with pytest.raises(ValueError, match="Invalid freight mode"):
            FreightMode.from_string("TRAIN")

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("AÉREO", FreightMode.AIR),
            ("MARÍTIMO/RODOVIÁRIO", FreightMode.SEA),
            ("SEA/ROAD", FreightMode.SEA),
        ],
    )
    def test_missing_translations(self, raw: str, expected: FreightMode):
        """_missing_ should resolve translated labels."""
        assert FreightMode(raw.upper()) is expected

    def test_values(self):
        assert FreightMode.AIR.value == "AIR"
        assert FreightMode.SEA.value == "SEA"
        assert FreightMode.ROAD.value == "ROAD"


# ── DateRange ────────────────────────────────────────────────────────


class TestDateRange:
    """Tests for the DateRange dataclass."""

    def test_from_string_valid(self):
        dr = DateRange.from_string("01/01/2026;31/01/2026")
        assert dr.start == datetime(2026, 1, 1)
        assert dr.end == datetime(2026, 1, 31, 23, 59, 59)

    def test_from_string_same_day(self):
        dr = DateRange.from_string("15/03/2026;15/03/2026")
        assert dr.start == datetime(2026, 3, 15)
        assert dr.end == datetime(2026, 3, 15, 23, 59, 59)

    def test_from_string_with_spaces(self):
        dr = DateRange.from_string(" 01/01/2026 ; 31/01/2026 ")
        assert dr.start == datetime(2026, 1, 1)

    def test_from_string_invalid_format(self):
        with pytest.raises(InvalidDateRangeError):
            DateRange.from_string("2026-01-01;2026-01-31")

    def test_from_string_missing_separator(self):
        with pytest.raises(InvalidDateRangeError):
            DateRange.from_string("01/01/2026")

    def test_from_string_empty(self):
        with pytest.raises(InvalidDateRangeError):
            DateRange.from_string("")

    def test_frozen(self):
        dr = DateRange.from_string("01/01/2026;31/01/2026")
        with pytest.raises(AttributeError):
            dr.start = datetime(2026, 2, 1)  # type: ignore[misc]


# ── DsnoInfo ─────────────────────────────────────────────────────────


class TestDsnoInfo:
    """Tests for the DsnoInfo dataclass."""

    def test_creation(self):
        info = DsnoInfo(invoice="12345", container="CNT-001", booking="BK-001")
        assert info.invoice == "12345"
        assert info.container == "CNT-001"
        assert info.booking == "BK-001"

    def test_frozen(self):
        info = DsnoInfo(invoice="1", container="C", booking="B")
        with pytest.raises(AttributeError):
            info.invoice = "2"  # type: ignore[misc]


# ── ProcessingResult ─────────────────────────────────────────────────


class TestProcessingResult:
    """Tests for the ProcessingResult dataclass."""

    def test_defaults(self):
        r = ProcessingResult()
        assert r.total == 0
        assert r.success == 0
        assert r.errors == []
        assert r.failed == 0

    def test_failed_property(self):
        r = ProcessingResult(total=10, success=7)
        assert r.failed == 3

    def test_errors_independent(self):
        """Each instance should have its own error list."""
        r1 = ProcessingResult()
        r2 = ProcessingResult()
        r1.errors.append("err")
        assert r2.errors == []
