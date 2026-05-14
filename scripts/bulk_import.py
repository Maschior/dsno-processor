"""Bulk import customer sheets into the local SQLite database.

Recursively scans a directory (and all subdirectories) for Excel files
matching the customer sheet pattern and imports their data into
``tb_shipment_info``.

A JSON history file (``import_history.json``) is kept next to the database
so that re-running the script automatically skips files that were already
imported successfully.

Usage::

    python scripts/bulk_import.py "Z:\\Documentação\\ORACLE\\EDI\\ASN NAVSTAR\\customer_sheets"

Options:
    --invoice-col   Column name for invoice (default: Invoice)
    --container-col Column name for container (default: Container)
    --dry-run       Show files that would be imported without actually importing
    --force         Ignore history and re-import all files
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

# Ensure the project root is on sys.path so dsno_processor can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dsno_processor.database import (
    get_connection,
    get_db_path,
    import_customer_sheet,
    init_db,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# Booking column can have two names depending on the customer sheet version
_BOOKING_ALIASES = ["Booking/HAWB", "Booking"]

_EXCEL_GLOBS = ("*.xlsx", "*.xls")

_HISTORY_FILENAME = "import_history.json"


# ── History helpers ──────────────────────────────────────────────────


def _history_path() -> Path:
    """History file lives next to the database."""
    return get_db_path().parent / _HISTORY_FILENAME


def load_history() -> dict:
    """Load the import history from disk."""
    path = _history_path()
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except json.JSONDecodeError:
            log.warning("Corrupted history file — starting fresh.")
            return {}
    return {}


def save_history(history: dict) -> None:
    """Persist the import history to disk."""
    path = _history_path()
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(history, fh, ensure_ascii=False, indent=2)


def record_success(history: dict, key: str, imported: int, skipped: int) -> None:
    """Record a successful import in the history."""
    history[key] = {
        "status": "success",
        "imported": imported,
        "skipped": skipped,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    save_history(history)


def already_imported(history: dict, key: str) -> bool:
    """Check whether a file was already imported successfully."""
    entry = history.get(key, {})
    return entry.get("status") == "success"


# ── File discovery ───────────────────────────────────────────────────


def find_excel_files(root: Path) -> list[Path]:
    """Recursively find all Excel files under *root*."""
    files: list[Path] = []
    for pattern in _EXCEL_GLOBS:
        files.extend(root.rglob(pattern))
    # Exclude files inside the not-imported folder and temp lock files
    not_imported = root / "not-imported"
    files = [
        f for f in files 
        if not f.is_relative_to(not_imported) and not f.name.startswith("~$")
    ]
    # Sort by path for deterministic ordering
    return sorted(set(files))


# ── Main ─────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bulk import customer sheets into the DSNO Processor database.",
    )
    parser.add_argument(
        "directory",
        type=str,
        help="Root directory to scan for customer sheet Excel files.",
    )
    parser.add_argument(
        "--invoice-col",
        default="Invoice",
        help="Column name for invoice number (default: Invoice).",
    )
    parser.add_argument(
        "--container-col",
        default="Container",
        help="Column name for container (default: Container).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List files that would be imported without actually importing.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignore history and re-import all files.",
    )
    args = parser.parse_args()

    root = Path(args.directory)
    if not root.exists():
        log.error("Directory not found: %s", root)
        sys.exit(1)

    log.info("Scanning: %s", root)
    files = find_excel_files(root)

    if not files:
        log.warning("No Excel files found under %s", root)
        sys.exit(0)

    log.info("Found %d Excel file(s)", len(files))

    # Load history
    history = load_history() if not args.force else {}

    # Separate already-imported from pending
    pending: list[Path] = []
    skipped_history: list[Path] = []
    for f in files:
        key = str(f.relative_to(root))
        if already_imported(history, key):
            skipped_history.append(f)
        else:
            pending.append(f)

    if skipped_history:
        log.info("Skipping %d file(s) already imported (use --force to re-import)", len(skipped_history))

    if not pending:
        log.info("All files have already been imported!")
        return

    log.info("%d file(s) to import:", len(pending))
    for f in pending:
        log.info("  • %s", f.relative_to(root))

    if args.dry_run:
        log.info("Dry run — no data imported.")
        return

    # Open database
    db_path = get_db_path()
    conn = get_connection(db_path)
    init_db(conn)
    log.info("Database: %s", db_path.resolve())

    total_imported = 0
    total_skipped = 0
    errors: list[str] = []
    start_time = time.time()

    for i, filepath in enumerate(pending, 1):
        rel = filepath.relative_to(root)
        key = str(rel)
        log.info("[%d/%d] Importing %s ...", i, len(pending), rel)
        try:
            imported, skipped = import_customer_sheet(
                conn,
                filepath,
                invoice_col=args.invoice_col,
                booking_col=_BOOKING_ALIASES,
                container_col=args.container_col,
            )
            total_imported += imported
            total_skipped += skipped
            log.info("  → %d imported, %d skipped", imported, skipped)
            record_success(history, key, imported, skipped)
        except Exception as exc:
            log.error("  ✗ Failed: %s", exc)
            errors.append(f"{rel}: {exc}")

            # Copy failed file to not-imported folder (preserve subfolder structure)
            not_imported_dir = root / "not-imported"
            dest = not_imported_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(filepath, dest)
                log.info("  → Copied to %s", dest.relative_to(root))
            except Exception as copy_exc:
                log.warning("  → Could not copy: %s", copy_exc)

    conn.close()
    elapsed = time.time() - start_time

    # Summary
    log.info("=" * 60)
    log.info("  Files processed:    %d", len(pending))
    log.info("  Files from history: %d", len(skipped_history))
    log.info("  Records imported:   %d", total_imported)
    log.info("  Records skipped:    %d", total_skipped)
    log.info("  Errors:             %d", len(errors))
    log.info("  Time:               %.1fs", elapsed)

    if errors:
        not_imported_dir = root / "not-imported"
        log.info("")
        log.info("Failed files (copied to %s):", not_imported_dir)
        for e in errors:
            log.info("  • %s", e)

    log.info("=" * 60)


if __name__ == "__main__":
    main()
