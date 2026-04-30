"""Read and filter data from the internal control spreadsheet.

Provides functions to:
- Load the control sheet from disk.
- Extract available status options for the GUI filter.
- Build ``(invoice, dsno, oracle_freight, softway_freight)`` tuples
  filtered by date range and status.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from .config import load_config
from .exceptions import ColumnMissingError, SheetNotFoundError
from .models import DateRange

log = logging.getLogger(__name__)

cfg = load_config()

# Column names in the control spreadsheet
_DATE_COL = cfg.DATE_COL.upper()
_DSNO_COL = cfg.DSNO_COL.upper()
_INVOICE_COL = cfg.INVOICE_COL.upper()
_STATUS_COL = cfg.STATUS_COL.upper()
_FREIGHT_ORACLE_COL = cfg.FREIGHT_ORACLE_COL.upper()
_FREIGHT_SOFTWAY_COL = cfg.FREIGHT_SOFTWAY_COL.upper()

_REQUIRED_COLUMNS = {
    _DATE_COL,
    _DSNO_COL,
    _INVOICE_COL,
    _STATUS_COL,
    _FREIGHT_ORACLE_COL,
    _FREIGHT_SOFTWAY_COL,
}


# ── Sheet loading ────────────────────────────────────────────────────


def read_control_sheet(control_sheet_path: Path | str) -> pd.DataFrame:
    """Read the control spreadsheet into a DataFrame.

    Args:
        control_sheet_path: Path to the Excel control sheet.

    Raises:
        SheetNotFoundError: If the file does not exist.
    """
    path = Path(control_sheet_path)
    if not path.exists():
        raise SheetNotFoundError(f"Control sheet not found at: {path}")
    df = pd.read_excel(path)
    df.columns = df.columns.str.strip().str.upper().str.replace(r"\s+", " ", regex=True)
    return df


# ── Status options ───────────────────────────────────────────────────


def get_status_options(control_sheet: pd.DataFrame) -> list[str]:
    """Return sorted unique status values from the control sheet.

    Used by the GUI to populate the multi-select status filter.
    Returns an empty list if fewer than two distinct values exist.
    """
    try:
        values = sorted(control_sheet[_STATUS_COL].dropna().unique().tolist())
        return values if len(values) > 1 else []
    except Exception as exc:
        log.warning("Could not read status options from sheet: %s", exc)
        return []


# ── Invoice / DSNO pair extraction ───────────────────────────────────


def get_invoice_dsno_pairs(
    date_range: DateRange,
    control_sheet: pd.DataFrame,
    status_filter: list[str] | None = None,
) -> list[tuple[int, str, object, object]]:
    """Return filtered rows as ``(invoice, dsno, oracle_freight, softway_freight)`` tuples.

    Args:
        date_range: The :class:`DateRange` to filter by.
        control_sheet: A pre-loaded DataFrame of the control spreadsheet.
        status_filter: Optional list of status strings to include.
            An empty list or ``None`` means no filter (all statuses).

    Returns:
        List of ``(invoice, dsno_filename, oracle_freight, softway_freight)`` tuples.

    Raises:
        ColumnMissingError: If required columns are absent from the sheet.
    """
    df = control_sheet

    missing = _REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ColumnMissingError(
            f"Missing columns in sheet: {missing}. "
            "The column name might have changed — please check the sheet headers."
        )

    # Ensure STATUS column exists so we don't get KeyError
    if _STATUS_COL not in df.columns:
        df[_STATUS_COL] = pd.NA

    df[_DATE_COL] = pd.to_datetime(
        df[_DATE_COL], format="%m/%d/%Y %I:%M:%S %p", errors="coerce"
    )

    date_mask = (df[_DATE_COL] >= date_range.start) & (df[_DATE_COL] <= date_range.end)
    mask = date_mask

    if status_filter is not None and len(status_filter) > 0:
        if not isinstance(status_filter[0], str):
            raise ValueError("status_filter item must be a string")
        status_filter = [s.lower().strip() for s in status_filter]

        # Status filter: Only process allowed statuses or empty statuses
        status_series = df[_STATUS_COL].astype(str).str.strip().str.lower()
        status_mask = (
            df[_STATUS_COL].isna()
            | (status_series.isin(status_filter))
            | (status_series == "")
            | (status_series == "nan")
        )
        mask = date_mask & status_mask

    df_filtered = df.loc[mask].dropna(subset=[_INVOICE_COL, _DSNO_COL])

    invoices = df_filtered[_INVOICE_COL].astype("Int64").tolist()
    dsnos = df_filtered[_DSNO_COL].astype(str).tolist()
    oracle_freights = df_filtered[_FREIGHT_ORACLE_COL].tolist()
    softway_freights = df_filtered[_FREIGHT_SOFTWAY_COL].tolist()

    return list(zip(invoices, dsnos, oracle_freights, softway_freights))
