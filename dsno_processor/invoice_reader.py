"""Read invoice/DSNO pairs from the internal control sheet."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from .config import load_config
from .exceptions import SheetNotFoundError
from .models import DateRange

log = logging.getLogger(__name__)

cfg = load_config()

# Column names in the control spreadsheet
_DATE_COL = cfg.DATE_COL
_DSNO_COL = cfg.DSNO_COL
_INVOICE_COL = cfg.INVOICE_COL
_STATUS_COL = cfg.STATUS_COL
_FREIGHT_ORACLE_COL = cfg.FREIGHT_ORACLE_COL
_FREIGHT_SOFTWAY_COL = cfg.FREIGHT_SOFTWAY_COL

_REQUIRED_COLUMNS = {_DATE_COL, _DSNO_COL, _INVOICE_COL, _STATUS_COL, _FREIGHT_ORACLE_COL, _FREIGHT_SOFTWAY_COL}

class FreightType:
    ORACLE = "ORACLE"
    SOFTWAY = "SOFTWAY"

    @classmethod
    def from_string(cls, freight_type: str) -> str:
        if freight_type.upper() == cls.ORACLE:
            return cls.ORACLE
        elif freight_type.upper() == cls.SOFTWAY:
            return cls.SOFTWAY
        else:
            raise ValueError(f"Invalid freight type: {freight_type}")


def read_control_sheet(control_sheet_path: Path | str) -> pd.DataFrame:
    """Read the control sheet."""
    path = Path(control_sheet_path)
    if not path.exists():
        raise SheetNotFoundError(f"Control sheet not found at: {path}")
    return pd.read_excel(path)

def get_status_options(control_sheet: pd.DataFrame) -> list[str]:
    """Get status options for filtering."""
    try:
        values = sorted(control_sheet[_STATUS_COL].dropna().unique().tolist())
        return values if len(values) > 1 else []
    except Exception as exc:
        log.warning("Could not read status options from sheet: %s", exc)
        return []

def get_invoice_dsno_pairs(
    date_range: DateRange,
    control_sheet: pd.DataFrame,
    status_filter: list[str] | None = None,
) -> list[tuple[int, str]]:
    """Return a list of ``(invoice, dsno_filename)`` pairs within *date_range*.

    Args:
        date_range: The :class:`DateRange` to filter by.
        control_sheet_path: Path to the Excel control sheet.
        status_filter: Optional status to filter by. If "All", processes all allowed statuses.

    Returns:
        List of ``(invoice_number, dsno_filename)`` tuples.

    Raises:
        SheetNotFoundError: If *control_sheet_path* does not exist.
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
