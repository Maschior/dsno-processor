"""Read shipping info (container, booking) from the customer spreadsheet.

Provides functions to:
- Load the customer sheet from disk (respecting the configured sheet name).
- Look up shipping details for a given invoice number.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from .config import load_config
from .exceptions import ColumnMissingError, SheetNotFoundError
from .models import DsnoInfo

log = logging.getLogger(__name__)

cfg = load_config()

# Customer sheet columns
_INVOICE_COL = cfg.INVOICE_COL.upper()
_CONTAINER_COL = cfg.CONTAINER_COL.upper()
_BOOKING_COL = cfg.BOOKING_COL.upper()

# Required columns
_REQUIRED_COLUMNS = {_INVOICE_COL, _BOOKING_COL}

# ── Sheet loading ────────────────────────────────────────────────────


def read_customer_sheet(customer_sheet_path: Path | str) -> pd.DataFrame:
    """Read the customer spreadsheet into a DataFrame.

    Respects the ``CUSTOMER_SHEET_NAME`` config value: when set, that
    specific worksheet is loaded; otherwise the first sheet is used.

    Args:
        customer_sheet_path: Path to the customer Excel file.

    Raises:
        SheetNotFoundError: If the file or named sheet does not exist.
    """
    path = Path(customer_sheet_path)
    if not path.exists():
        raise SheetNotFoundError(f"Customer sheet not found: {path}")

    sheet_name = cfg.CUSTOMER_SHEET_NAME
    if sheet_name:
        try:
            df = pd.read_excel(path, sheet_name=sheet_name)
        except ValueError as exc:
            raise SheetNotFoundError(
                f"Sheet '{sheet_name}' not found in {path.name}"
            ) from exc
    else:
        df = pd.read_excel(path)

    # Normalize headers (strip whitespace, uppercase, collapse multiple spaces)
    df.columns = df.columns.str.strip().str.upper().str.replace(r"\s+", " ", regex=True)
    return df


# ── Invoice lookup ───────────────────────────────────────────────────


def get_dsno_info(invoice: int, customer_sheet: pd.DataFrame) -> DsnoInfo | None:
    """Look up shipping details for *invoice* in a pre-loaded customer DataFrame.

    Args:
        invoice: The invoice number to search for.
        customer_sheet: A pre-loaded DataFrame of the customer spreadsheet.

    Returns:
        A :class:`DsnoInfo` instance, or ``None`` if the invoice was not found.

    Raises:
        ColumnMissingError: If required columns are absent from the sheet.
    """
    df = customer_sheet
    
    missing = _REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ColumnMissingError(
            f"Missing columns in sheet: {missing}. "
            "The column name might have changed — please check the sheet headers."
        )

    row = df.loc[df[_INVOICE_COL] == invoice]
    if row.empty:
        log.info("Invoice %s not found in customer sheet — DSNO ignored.", invoice)
        return None

    first = row.head(1).iloc[0]
    booking = str(first[_BOOKING_COL])
    container = str(first[_CONTAINER_COL]) if _CONTAINER_COL in df.columns else ""

    return DsnoInfo(
        invoice=str(invoice),
        container=container,
        booking=booking,
    )
