"""Data models for the DSNO Processor application."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from .exceptions import InvalidDateRangeError


@dataclass(frozen=True)
class DateRange:
    """Represents a date range for filtering invoices."""

    start: datetime
    end: datetime

    @classmethod
    def from_string(cls, raw: str) -> DateRange:
        """Parse a date range string in the format 'DD/MM/YYYY;DD/MM/YYYY'.

        The end date is inclusive (extended to 23:59:59).
        """
        try:
            start_str, end_str = raw.split(";")
            start = pd.to_datetime(start_str.strip(), format="%d/%m/%Y")
            end = (
                pd.to_datetime(end_str.strip(), format="%d/%m/%Y")
                + pd.Timedelta(days=1)
                - pd.Timedelta(seconds=1)
            )
        except (ValueError, AttributeError) as exc:
            raise InvalidDateRangeError(
                "The date range must be in the format 'DD/MM/YYYY;DD/MM/YYYY'."
            ) from exc

        return cls(start=start.to_pydatetime(), end=end.to_pydatetime())


@dataclass(frozen=True)
class DsnoInfo:
    """Shipping information extracted from the customer sheet."""

    invoice: str
    container: str
    booking: str


@dataclass
class ProcessingResult:
    """Aggregate result of a batch DSNO processing run."""

    total: int = 0
    success: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def failed(self) -> int:
        return self.total - self.success
