"""Main orchestrator for DSNO processing."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from .editor import edit_navstar_dsno, move_to_processed, normalize_file
from .exceptions import DsnoProcessorError
from .info_reader import get_dsno_info
from .invoice_reader import get_invoice_dsno_pairs
from .models import DateRange, DsnoInfo, ProcessingResult

log = logging.getLogger(__name__)


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


def _process_single_dsno(
    invoice: int,
    dsno_path: Path,
    customer_sheet_path: Path | str,
) -> str | None:
    """Process one DSNO file. Returns an error message on failure, else ``None``."""
    try:
        info = get_dsno_info(invoice=invoice, customer_sheet_path=customer_sheet_path)

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

        edit_navstar_dsno(dsno_path, dsno_info)

        if dsno_path.exists():
            normalize_file(dsno_path)
            log.info("Normalized file %s", dsno_path.name)

        return None  # success

    except DsnoProcessorError as exc:
        return str(exc)


def process_dsno(
    date_range: str,
    customer_sheet: str,
    control_sheet: str,
    dsno_dir: str,
) -> ProcessingResult:
    """Run a full DSNO processing batch.

    This is the main public entry point called by the GUI. The signature
    accepts raw strings to keep the GUI layer simple.

    Args:
        date_range: Date range in ``DD/MM/YYYY;DD/MM/YYYY`` format.
        customer_sheet: Path to the customer Excel file.
        control_sheet: Path to the internal control sheet.
        dsno_dir: Root directory containing DSNO files.

    Returns:
        A :class:`ProcessingResult` with counts and error details.
    """
    setup_logger()
    result = ProcessingResult()

    log.info("Starting processing...")
    log.info("Customer Sheet: %s", customer_sheet)
    log.info("Control Sheet: %s", control_sheet)
    log.info("Date Range: %s", date_range)
    log.info("DSNO Target Directory: %s", dsno_dir)

    parsed_range = DateRange.from_string(date_range)
    pairs = get_invoice_dsno_pairs(parsed_range, control_sheet)

    base_dir = Path(dsno_dir)
    processed_dir = base_dir / "Processed"
    result.total = len(pairs)

    for invoice, dsno_filename in pairs:
        dsno_path = base_dir / dsno_filename
        log.info("---- Processing DSNO: %s ----", dsno_path.name)

        error = _process_single_dsno(
            invoice=invoice,
            dsno_path=dsno_path,
            customer_sheet_path=customer_sheet,
        )

        if error:
            result.errors.append(error)
            log.error(error)
        else:
            result.success += 1
            move_to_processed(dsno_path, processed_dir)

    log.info(
        "Processing complete: %d/%d successful, %d errors.",
        result.success,
        result.total,
        result.failed,
    )
    return result
