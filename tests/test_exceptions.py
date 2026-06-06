"""Tests for dsno_processor.exceptions."""

from __future__ import annotations

import pytest

from dsno_processor.exceptions import (
    CanceledError,
    ColumnMissingError,
    ConfigurationError,
    DsnoFileError,
    DsnoProcessorError,
    InvalidDateRangeError,
    LoginError,
    SheetNotFoundError,
)


_ALL_EXCEPTIONS = [
    ConfigurationError,
    SheetNotFoundError,
    ColumnMissingError,
    DsnoFileError,
    InvalidDateRangeError,
    LoginError,
    CanceledError,
]


class TestExceptionHierarchy:
    """Verify the exception class hierarchy."""

    @pytest.mark.parametrize("exc_cls", _ALL_EXCEPTIONS)
    def test_inherits_from_base(self, exc_cls):
        assert issubclass(exc_cls, DsnoProcessorError)

    @pytest.mark.parametrize("exc_cls", _ALL_EXCEPTIONS)
    def test_inherits_from_exception(self, exc_cls):
        assert issubclass(exc_cls, Exception)

    @pytest.mark.parametrize("exc_cls", _ALL_EXCEPTIONS)
    def test_instantiable_with_message(self, exc_cls):
        exc = exc_cls("test message")
        assert str(exc) == "test message"

    @pytest.mark.parametrize("exc_cls", _ALL_EXCEPTIONS)
    def test_raisable(self, exc_cls):
        with pytest.raises(exc_cls):
            raise exc_cls("boom")

    def test_base_is_exception(self):
        assert issubclass(DsnoProcessorError, Exception)
