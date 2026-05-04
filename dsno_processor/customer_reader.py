"""Read shipping info (container, booking) from the customer spreadsheet.

Provides functions to:
- Load the customer sheet from disk (respecting the configured sheet name).
- Look up shipping details for a given invoice number.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import pandas as pd

from .config import load_config
from .exceptions import ColumnMissingError, SheetNotFoundError
from .models import DsnoInfo

log = logging.getLogger(__name__)

# region agent log helpers (debug-1ca7c5)
_DEBUG_LOG_PATH = "debug-1ca7c5.log"
_DEBUG_SESSION_ID = "1ca7c5"


def _append_debug_log(
    *, runId: str, hypothesisId: str, location: str, message: str, data: dict
) -> None:
    try:
        payload = {
            "sessionId": _DEBUG_SESSION_ID,
            "runId": runId,
            "hypothesisId": hypothesisId,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        return


def _suspicious_chars(s: str) -> list[str]:
    out: list[str] = []
    for ch in s:
        o = ord(ch)
        if o > 127:
            out.append(f"U+{o:04X}")
    return out


def _col_signature(cols: list[object], *, limit: int = 80) -> list[dict]:
    sig: list[dict] = []
    for c in cols[:limit]:
        s = str(c)
        sig.append(
            {
                "text": s[:200],
                "repr": repr(s)[:220],
                "len": len(s),
                "suspicious": _suspicious_chars(s)[:20],
                "has_nbsp": ("\u00A0" in s),
                "has_slash": ("/" in s),
                "has_backslash": ("\\" in s),
            }
        )
    return sig


# endregion


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

    cfg = load_config()
    sheet_name = cfg.CUSTOMER_SHEET_NAME
    required = {cfg.INVOICE_COL.upper(), cfg.BOOKING_COL.upper()}

    # Excel files often have a blank "cover" as the first sheet.
    # If sheet_name isn't configured, scan sheets and pick the first
    # that contains required columns after normalization.
    try:
        xls = pd.ExcelFile(path)
        sheet_names = list(xls.sheet_names)
    except Exception:
        sheet_names = []

    _append_debug_log(
        runId="pre-fix",
        hypothesisId="H4",
        location="dsno_processor/customer_reader.py:read_customer_sheet(sheet-list)",
        message="Customer workbook sheet names discovered",
        data={
            "path_name": path.name,
            "cfg_sheet_name": sheet_name or "",
            "sheet_count": int(len(sheet_names)),
            "sheet_names": sheet_names[:50],
            "required": sorted(required),
        },
    )

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
                _append_debug_log(
                    runId="pre-fix",
                    hypothesisId="H4",
                    location="dsno_processor/customer_reader.py:read_customer_sheet(scan)",
                    message="Scanning sheet for required columns",
                    data={
                        "sheet_name": str(name),
                        "nrows": int(getattr(candidate, "shape", (0, 0))[0]),
                        "ncols": int(getattr(candidate, "shape", (0, 0))[1]),
                        "missing_required": sorted(miss),
                    },
                )
                if not miss:
                    df = candidate
                    sheet_name = str(name)
                    break

    _append_debug_log(
        runId="pre-fix",
        hypothesisId="H1",
        location="dsno_processor/customer_reader.py:read_customer_sheet(raw)",
        message="Customer sheet loaded (raw headers)",
        data={
            "path_name": path.name,
            "sheet_name": sheet_name or "",
            "ncols": int(len(df.columns)),
            "columns_sig": _col_signature(list(df.columns)),
        },
    )

    # Normalize headers (strip whitespace, uppercase, collapse multiple spaces)
    df.columns = _normalize_cols(df.columns)

    _append_debug_log(
        runId="pre-fix",
        hypothesisId="H2",
        location="dsno_processor/customer_reader.py:read_customer_sheet(normalized)",
        message="Customer sheet normalized headers",
        data={
            "ncols": int(len(df.columns)),
            "columns_sig": _col_signature(list(df.columns)),
        },
    )
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
    cfg = load_config()

    invoice_col = cfg.INVOICE_COL.upper()
    booking_col = cfg.BOOKING_COL.upper()
    container_col = cfg.CONTAINER_COL.upper()
    required = {invoice_col, booking_col}

    missing = required - set(df.columns)
    if missing:
        _append_debug_log(
            runId="pre-fix",
            hypothesisId="H3",
            location="dsno_processor/customer_reader.py:get_dsno_info(missing)",
            message="Required columns missing (exact match failed)",
            data={
                "invoice": int(invoice),
                "required": sorted(required),
                "missing": sorted(missing),
                "available_sample": _col_signature(list(df.columns), limit=40),
                "cfg": {
                    "invoice_col_raw": cfg.INVOICE_COL,
                    "booking_col_raw": cfg.BOOKING_COL,
                    "container_col_raw": cfg.CONTAINER_COL,
                },
            },
        )
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
