"""Read shipping info (container, booking) from the customer spreadsheet.

Provides functions to:
- Load the customer sheet from disk (respecting the configured sheet name).
- Look up shipping details for a given invoice number.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from .config import AppConfig, load_config
from .exceptions import ColumnMissingError, SheetNotFoundError
from .models import DsnoInfo

log = logging.getLogger(__name__)


def _safe_config() -> AppConfig:
    """Return persisted config when available, otherwise default column names."""
    try:
        return load_config()
    except Exception:
        return AppConfig()


cfg = _safe_config()
_INVOICE_COL = cfg.INVOICE_COL.upper()
_CONTAINER_COL = cfg.CONTAINER_COL.upper()
_BOOKING_COL = cfg.BOOKING_COL.upper()
_REQUIRED_COLUMNS = {_INVOICE_COL, _BOOKING_COL}

# ── Sheet loading ────────────────────────────────────────────────────


def read_customer_sheet(customer_sheet_path: Path | str) -> pd.DataFrame:
    """Read the customer spreadsheet into a DataFrame.

    Respects the ``CUSTOMER_SHEET_NAME`` config value: when set, that
    specific worksheet is loaded; otherwise a sheet is auto-detected.

    Args:
        customer_sheet_path: Path to the customer Excel file.

    Raises:
        SheetNotFoundError: If the file or named sheet does not exist.
    """
    path = Path(customer_sheet_path)
    if not path.exists():
        raise SheetNotFoundError(f"Customer sheet not found: {path}")

    sheet_name = cfg.CUSTOMER_SHEET_NAME
    required = _REQUIRED_COLUMNS

    # Excel files often have a blank "cover" as the first sheet.
    # If sheet_name isn't configured, scan sheets and pick the first
    # that contains required columns after normalization.
    try:
        xls = pd.ExcelFile(path)
        sheet_names = list(xls.sheet_names)
    except Exception:
        sheet_names = []

    def _normalize_cols(cols: pd.Index) -> pd.Index:
        return (
            cols.astype(str)
            .str.strip()
            .str.upper()
            .str.replace(r"\s+", " ", regex=True)
        )

    def _read_one(name: str | int | None) -> pd.DataFrame:
        return pd.read_excel(path, sheet_name=name)  # header=0 by default

    if sheet_name:
        try:
            df = _read_one(sheet_name)
        except ValueError as exc:
            raise SheetNotFoundError(
                f"Sheet '{sheet_name}' not found in {path.name}"
            ) from exc
    else:
        # Start with first sheet then scan if required columns missing
        df = _read_one(0)
        probe_cols = _normalize_cols(df.columns)
        if sheet_names and (required - set(probe_cols)):
            for name in sheet_names[1:]:
                candidate = _read_one(name)
                cand_cols = _normalize_cols(candidate.columns)
                miss = required - set(cand_cols)
                if not miss:
                    df = candidate
                    sheet_name = str(name)
                    break

    # Normalize headers (strip whitespace, uppercase, collapse multiple spaces)
    df.columns = _normalize_cols(df.columns)

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
    invoice_col = _INVOICE_COL
    booking_col = _BOOKING_COL
    container_col = _CONTAINER_COL
    required = _REQUIRED_COLUMNS

    missing = required - set(df.columns)
    if missing:
        raise ColumnMissingError(
            f"Missing columns in sheet: {missing}. "
            "The column name might have changed — please check the sheet headers."
        )

    row = df.loc[df[invoice_col] == invoice]
    if row.empty:
        log.info("Invoice %s not found in customer sheet — DSNO ignored.", invoice)
        return None

    first = row.head(1).iloc[0]
    booking = str(first[booking_col])
    container = str(first[container_col]) if container_col in df.columns else ""

    return DsnoInfo(
        invoice=str(invoice),
        container=container,
        booking=booking,
    )
