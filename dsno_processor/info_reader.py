"""Read shipping info (container, booking) from the customer sheet."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from .exceptions import ColumnMissingError, SheetNotFoundError
from .models import DsnoInfo

log = logging.getLogger(__name__)

_INVOICE_COL = "Invoice"
_CONTAINER_COL = "Container"
_BOOKING_COL = "Booking/HAWB"
_REQUIRED_COLUMNS = {_INVOICE_COL, _CONTAINER_COL, _BOOKING_COL}


def get_dsno_info(invoice: int, customer_sheet_path: Path | str) -> DsnoInfo | None:
    """Look up shipping details for *invoice* in the customer spreadsheet.

    Args:
        invoice: The invoice number to search for.
        customer_sheet_path: Path to the customer Excel file.

    Returns:
        A :class:`DsnoInfo` instance, or ``None`` if the invoice was not found.

    Raises:
        SheetNotFoundError: If the file does not exist.
        ColumnMissingError: If required columns are absent from the sheet.
    """
    path = Path(customer_sheet_path)
    if not path.exists():
        raise SheetNotFoundError(f"Customer sheet not found: {path}")

    df = pd.read_excel(path, sheet_name="Details")

    # Normalize headers (strip whitespace, collapse multiple spaces)
    df.columns = df.columns.str.strip().str.replace(r"\s+", " ", regex=True)

    missing = _REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ColumnMissingError(
            f"Missing columns in sheet: {missing}. "
            "The column name might have changed — please check the sheet headers."
        )

    row = df.loc[df[_INVOICE_COL] == invoice]
    if row.empty:
        log.info(
            "Invoice %s not found in sheet %s — DSNO ignored.", invoice, path.name
        )
        return None

    first = row.head(1).iloc[0]
    container = str(first[_CONTAINER_COL])
    booking = str(first[_BOOKING_COL])

    return DsnoInfo(
        invoice=str(invoice),
        container=container,
        booking=booking,
    )
