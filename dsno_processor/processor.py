"""Main orchestrator for DSNO processing."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from .control_reader import get_invoice_dsno_pairs, read_control_sheet
from .customer_reader import get_dsno_info, read_customer_sheet
from .editor import edit_navstar_dsno, move_to_processed, normalize_file, get_size
from .exceptions import CanceledError, ColumnMissingError, DsnoProcessorError, SheetNotFoundError
from .models import DateRange, DsnoInfo, FreightMode, ProcessingResult
from .status_updater import update_control_sheet_status

log = logging.getLogger(__name__)


# ── Logging setup ────────────────────────────────────────────────────


def setup_logger(log_dir: Path | str = "logs") -> None:
    """Configure root logger to write to a timestamped file.

    Safe to call multiple times — a new file handler is added each time, but
    no duplicate stream handlers are created.
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%d%m%Y_%H%M")
    log_file = log_path / f"log_{timestamp}.txt"

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)


# ── Freight resolution ───────────────────────────────────────────────


def _resolve_freight(
    oracle_freight: object,
    softway_freight: object,
    mode: FreightMode,
) -> tuple[str | None, str | None]:
    """Choose the correct freight value based on user-selected mode.

    Returns a tuple containing:
      - The freight value as a string (or None).
      - An error/warning message as a string (or None).

    Rules:
      - **AIR mode**: Prefer Softway. If not available, fall back to Oracle.
      - **SEA mode**: If Softway differs from Oracle and is not null, 
        prefer Softway. Otherwise, fall back to Oracle.
    """
    
    def _clean(val: object) -> str:
        if val is None:
            return ""
        s = str(val).strip()
        return "" if s.lower() in ("nan", "") else s
    
    oracle = _clean(oracle_freight)
    softway = _clean(softway_freight)

    if not oracle and not softway:
        error = 'No freight information available.'
        log.error(error)
        return None, error

    if mode == FreightMode.AIR:
        if not softway and oracle:
            error = "Softway freight is not available. Using Oracle freight."
            log.warning(error)
            return oracle, error
        return softway, None
    
    if mode == FreightMode.SEA:
        if softway and softway != oracle:
            log.warning("Softway freight differs from Oracle. Using Softway freight.")
            return softway, None
        return oracle, None

    fallback_error = f"Unhandled freight mode: {mode}. Using Softway if available; otherwise, Oracle."
    log.warning(fallback_error)
    
    return (softway, fallback_error) if softway else (oracle, fallback_error)


# ── Single DSNO processing ──────────────────────────────────────────


def _process_single_dsno(
    invoice: int,
    dsno_path: Path,
    customer_sheet_path: Path | str,
) -> str | None:
    """Process one DSNO file. Returns an error message on failure, else ``None``."""
    try:
        customer_sheet_df = read_customer_sheet(customer_sheet_path)
        info = get_dsno_info(invoice, customer_sheet_df)

        if info is None:
            return f"Invoice {invoice} not found in customer sheet."

        # Resolve missing container → default to AIR FREIGHT
        container = info.container
        if not container or container.strip() == "nan":
            container = "AIR FREIGHT"

        booking = info.booking
        if not booking or booking.strip() == "nan":
            return f"Booking information is missing for invoice {invoice}."

        dsno_info = DsnoInfo(
            invoice=info.invoice,
            container=container,
            booking=booking,
        )

        if not dsno_path.exists():
            return f"DSNO file not found: {dsno_path.name}"

        original_size = get_size(dsno_path)
        edit_navstar_dsno(dsno_path, dsno_info)

        normalize_file(dsno_path)
        log.info("Normalized file %s", dsno_path.name)

        new_size = get_size(dsno_path)

        if new_size == original_size:
            return f"File size unchanged after processing: {dsno_path.name}"

        return None

    except CanceledError:
        raise
    except SheetNotFoundError as exc:
        log.exception(str(exc))
        return str(exc)
    except ColumnMissingError as exc:
        log.exception(str(exc))
        return str(exc)
    except Exception as exc:
        log.exception("Unexpected error processing %s: %s", dsno_path.name, exc)
        return f"Unexpected error: {exc}"


# ── Public API ───────────────────────────────────────────────────────


def process_dsno(
    date_range: str,
    customer_sheet: str,
    control_sheet: str,
    dsno_dir: str,
    freight_mode: str = "SEA",
    progress_callback=None,
    cancel_event=None,
    status_filter: list[str] | None = None,
) -> ProcessingResult:
    """Run a full DSNO processing batch.

    This is the main public entry point called by the GUI. The signature
    accepts raw strings to keep the GUI layer simple.

    Args:
        date_range: Date range in ``DD/MM/YYYY;DD/MM/YYYY`` format.
        customer_sheet: Path to the customer Excel file.
        control_sheet: Path to the internal control sheet.
        dsno_dir: Root directory containing DSNO files.
        freight_mode: ``"AIR"`` or ``"SEA"`` — controls freight resolution.
        progress_callback: Optional ``(event, data_dict)`` callable for
            real-time progress updates consumed by the GUI dashboard.
        cancel_event: Optional threading.Event to abort the operation.
        status_filter: Optional list of status values to include.
            An empty list or ``None`` means no filter (all statuses).

    Returns:
        A :class:`ProcessingResult` with counts and error details.
    """

    def _cb(event: str, data: dict | None = None) -> None:
        if progress_callback:
            progress_callback(event, data or {})

    setup_logger()
    result = ProcessingResult()
    mode = FreightMode.from_string(freight_mode)

    if not isinstance(status_filter, list):
        raise ValueError("status_filter must be a list of strings or None")

    if not status_filter:
        log.info("No status filter applied; processing all statuses.")
        status_filter = None

    _cb("phase", {"text": "Starting processing..."})
    log.info("Starting processing...")
    log.info("Customer Sheet: %s", customer_sheet)
    log.info("Control Sheet: %s", control_sheet)
    log.info("Date Range: %s", date_range)
    log.info("DSNO Target Directory: %s", dsno_dir)
    log.info("Freight Mode: %s", mode.value)

    _cb("phase", {"text": "Reading control sheet..."})
    parsed_range = DateRange.from_string(date_range)

    if cancel_event and cancel_event.is_set():
        log.info("Processing cancelled by user.")
        _cb("cancelled", {"name": "System", "detail": "Cancelled by user"})
        raise CanceledError("Cancelled by user")

    try:
        control_sheet_df = read_control_sheet(control_sheet)
    except Exception as exc:
        log.error("Failed to read control sheet: %s", exc)
        _cb("error", {"name": "System", "detail": f"Failed to read control sheet: {exc}"})
        return result

    pairs = get_invoice_dsno_pairs(parsed_range, control_sheet_df, status_filter=status_filter)

    if not pairs:
        log.info("No DSNO files found matching the criteria.")
        _cb("error", {"name": "System", "detail": "No DSNO files found matching the criteria."})
        return result

    if cancel_event and cancel_event.is_set():
        log.info("Processing cancelled by user.")
        _cb("cancelled", {"name": "System", "detail": "Cancelled by user"})
        raise CanceledError("Cancelled by user")

    base_dir = Path(dsno_dir)
    processed_dir = base_dir / "Processed"
    result.total = len(pairs)
    _cb("total", {"count": len(pairs)})

    for invoice, dsno_filename, oracle_freight, softway_freight in pairs:
        if cancel_event and cancel_event.is_set():
            log.info("Processing cancelled by user.")
            _cb("cancelled", {"name": "System", "detail": "Cancelled by user"})
            raise CanceledError("Cancelled by user")

        dsno_path = base_dir / dsno_filename
        _cb("phase", {"text": f"Processing {dsno_path.name}..."})
        log.info("---- Processing DSNO: %s ----", dsno_path.name)

        # Resolve freight based on user-selected mode
        freight, exc = _resolve_freight(oracle_freight, softway_freight, mode)
        if freight is None:
            error = f"No freight information found for invoice {invoice}"
            log.error("%s", error)
            _cb("error", {"name": dsno_path.name, "detail": error})
            continue

        log.info("Freight selected: %s. Freight resolved: %s", mode.value, freight)

        error = _process_single_dsno(
            invoice=invoice,
            dsno_path=dsno_path,
            customer_sheet_path=customer_sheet,
        )

        if error:
            result.errors.append(error)
            log.error(error)
            _cb("error", {"name": dsno_path.name, "detail": error})
        else:
            result.success += 1
            move_to_processed(dsno_path, processed_dir)
            _cb("success", {"name": dsno_path.name})

    # Update CONTROL_SHEET status after processing all DSNO files
    _cb("phase", {"text": "Updating control sheet..."})
    update_control_sheet_status(control_sheet, processed_dir)

    log.info(
        "Processing complete: %d/%d successful, %d errors.",
        result.success,
        result.total,
        result.failed,
    )
    _cb("finished", {})
    return result
