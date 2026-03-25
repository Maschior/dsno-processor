"""Read invoice/DSNO pairs from the internal control sheet."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from .exceptions import SheetNotFoundError
from .models import DateRange

log = logging.getLogger(__name__)

# Column names in the control spreadsheet
_DATE_COL = "CREATION_DATE"
_DSNO_COL = "ARGUMENT2"
_INVOICE_COL = "INVOICE"


def get_invoice_dsno_pairs(
    date_range: DateRange,
    control_sheet_path: Path | str,
) -> list[tuple[int, str]]:
    """Return a list of ``(invoice, dsno_filename)`` pairs within *date_range*.

    Args:
        date_range: The :class:`DateRange` to filter by.
        control_sheet_path: Path to the Excel control sheet.

    Returns:
        List of ``(invoice_number, dsno_filename)`` tuples.

    Raises:
        SheetNotFoundError: If *control_sheet_path* does not exist.
    """
    path = Path(control_sheet_path)
    if not path.exists():
        raise SheetNotFoundError(
            f"Control ASN Navistar sheet not found at: {path}"
        )

    df = pd.read_excel(path)

    df[_DATE_COL] = pd.to_datetime(
        df[_DATE_COL], format="%m/%d/%Y %I:%M:%S %p", errors="coerce"
    )

    mask = (df[_DATE_COL] >= date_range.start) & (df[_DATE_COL] <= date_range.end)
    df_filtered = df.loc[mask].dropna(subset=[_INVOICE_COL, _DSNO_COL])

    invoices = df_filtered[_INVOICE_COL].astype("Int64").tolist()
    dsnos = df_filtered[_DSNO_COL].astype(str).tolist()

    return list(zip(invoices, dsnos))
