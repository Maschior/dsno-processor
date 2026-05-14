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
    df.columns = (
        df.columns.astype(str)
        .str.strip()
        .str.upper()
        .str.replace(r"\s+", " ", regex=True)
    )
    return df


# ── Status options ───────────────────────────────────────────────────


def get_status_options(control_sheet: pd.DataFrame) -> list[str]:
    """Return sorted unique status values from the control sheet.

    Used by the GUI to populate the multi-select status filter.
    Returns an empty list if fewer than two distinct values exist.
    """
    try:

        cfg = load_config()
        status_col = cfg.STATUS_COL.upper()
        values = sorted(control_sheet[status_col].dropna().unique().tolist())
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
    cfg = load_config()

    date_col = cfg.DATE_COL.upper()
    dsno_col = cfg.DSNO_COL.upper()
    invoice_col = cfg.CONTROL_INVOICE_COL.upper()
    status_col = cfg.STATUS_COL.upper()
    oracle_col = cfg.FREIGHT_ORACLE_COL.upper()
    softway_col = cfg.FREIGHT_SOFTWAY_COL.upper()

    required = {
        date_col,
        dsno_col,
        invoice_col,
        status_col,
        oracle_col,
        softway_col,
    }

    missing = required - set(df.columns)
    if missing:
        raise ColumnMissingError(
            f"Missing columns in sheet: {missing}. "
            "The column name might have changed — please check the sheet headers."
        )

    # Ensure STATUS column exists so we don't get KeyError
    if status_col not in df.columns:
        df[status_col] = pd.NA

    df[date_col] = pd.to_datetime(
        df[date_col], format="%m/%d/%Y %I:%M:%S %p", errors="coerce"
    )

    date_mask = (df[date_col] >= date_range.start) & (df[date_col] <= date_range.end)
    mask = date_mask

    if status_filter is not None and len(status_filter) > 0:
        if not isinstance(status_filter[0], str):
            raise ValueError("status_filter item must be a string")
        status_filter = [s.lower().strip() for s in status_filter]

        # Status filter: Only process allowed statuses or empty statuses
        status_series = df[status_col].astype(str).str.strip().str.lower()
        status_mask = (
            df[status_col].isna()
            | (status_series.isin(status_filter))
            | (status_series == "")
            | (status_series == "nan")
        )
        mask = date_mask & status_mask

    df_filtered = df.loc[mask].dropna(subset=[invoice_col, dsno_col])

    invoices = df_filtered[invoice_col].astype("Int64").tolist()
    dsnos = df_filtered[dsno_col].astype(str).tolist()
    oracle_freights = df_filtered[oracle_col].tolist()
    softway_freights = df_filtered[softway_col].tolist()

    return list(zip(invoices, dsnos, oracle_freights, softway_freights))
