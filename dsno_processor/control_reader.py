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

from .config import AppConfig, load_config
from .exceptions import ColumnMissingError, SheetNotFoundError
from .models import DateRange

log = logging.getLogger(__name__)


def _safe_config() -> AppConfig:
    """Return persisted config when available, otherwise default column names."""
    try:
        return load_config()
    except Exception:
        return AppConfig()


_cfg = _safe_config()
_DATE_COL = _cfg.control_sheet_cols.date.upper()
_DSNO_COL = _cfg.control_sheet_cols.dsno.upper()
_INVOICE_COL = _cfg.control_sheet_cols.invoice.upper()
_STATUS_COL = _cfg.control_sheet_cols.status.upper()
_FREIGHT_ORACLE_COL = _cfg.control_sheet_cols.freight_oracle.upper()
_FREIGHT_SOFTWAY_COL = _cfg.control_sheet_cols.freight_softway.upper()
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
    date_col = _DATE_COL
    dsno_col = _DSNO_COL
    invoice_col = _INVOICE_COL
    status_col = _STATUS_COL
    oracle_col = _FREIGHT_ORACLE_COL
    softway_col = _FREIGHT_SOFTWAY_COL

    required = _REQUIRED_COLUMNS

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

    # Remove duplicatas da coluna DSNO_FILENAME
    df_filtered = df_filtered.drop_duplicates(subset=[dsno_col], keep="first")

    invoices = df_filtered[invoice_col].astype("Int64").tolist()
    dsnos = df_filtered[dsno_col].astype(str).tolist()
    oracle_freights = df_filtered[oracle_col].tolist()
    softway_freights = df_filtered[softway_col].tolist()

    return list(zip(invoices, dsnos, oracle_freights, softway_freights))
