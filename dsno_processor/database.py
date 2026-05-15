"""SQLite database layer for the DSNO Processor.

Provides two tables that mirror (and can replace) the spreadsheet-based
storage used historically:

- ``tb_control``       — delivery/invoice records (replaces Control Sheet)
- ``tb_shipment_info`` — shipping details per invoice (replaces Customer Sheet)

The database file lives alongside ``config.toml`` in the project root.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

_DEFAULT_DB_NAME = "dsno_processor.db"

# Register explicit adapters for Python 3.12+ (default ones are deprecated).
sqlite3.register_adapter(datetime, lambda dt: dt.isoformat())
sqlite3.register_converter("TIMESTAMP", lambda b: datetime.fromisoformat(b.decode()))


# ── Data models ──────────────────────────────────────────────────────


@dataclass
class ControlRecord:
    """A single row in ``tb_control``."""

    id: int | None = None
    created_at: datetime | None = None
    delivery_id: int | None = None
    invoice: int = 0
    dsno_filename: str = ""
    creation_date: datetime | None = None
    status: str | None = None
    freight_oracle: str | None = None
    freight_softway: str | None = None
    description: str | None = None


@dataclass
class ShipmentRecord:
    """A single row in ``tb_shipment_info``."""

    id: int | None = None
    created_at: datetime | None = None
    delivery_id: int | None = None
    esn: int | None = None
    invoice: int = 0
    booking: str = ""
    container: str = ""


# ── Schema ───────────────────────────────────────────────────────────

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS tb_control (
    ID              INTEGER PRIMARY KEY AUTOINCREMENT,
    CREATED_AT      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    DELIVERY_ID     BIGINT,
    INVOICE         INTEGER NOT NULL,
    DSNO_FILENAME   VARCHAR NOT NULL UNIQUE,
    CREATION_DATE   TIMESTAMP NOT NULL,
    STATUS          VARCHAR,
    FREIGHT_ORACLE  VARCHAR,
    FREIGHT_SOFTWAY VARCHAR,
    DESCRIPTION     VARCHAR
);

CREATE INDEX IF NOT EXISTS idx_control_delivery_id
    ON tb_control (DELIVERY_ID);
CREATE INDEX IF NOT EXISTS idx_control_creation_date
    ON tb_control (CREATION_DATE);
CREATE INDEX IF NOT EXISTS idx_control_invoice
    ON tb_control (INVOICE);

CREATE TABLE IF NOT EXISTS tb_shipment_info (
    ID              INTEGER PRIMARY KEY AUTOINCREMENT,
    CREATED_AT      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    DELIVERY_ID     BIGINT,
    ESN             BIGINT UNIQUE,
    INVOICE         INTEGER NOT NULL,
    BOOKING         VARCHAR NOT NULL,
    CONTAINER       VARCHAR NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_shipment_invoice
    ON tb_shipment_info (INVOICE);
CREATE INDEX IF NOT EXISTS idx_shipment_delivery_id
    ON tb_shipment_info (DELIVERY_ID);
"""


# ── Connection / lifecycle ───────────────────────────────────────────


def get_db_path(config_dir: Path | str | None = None) -> Path:
    """Return the default database path (same directory as config.toml)."""
    if config_dir:
        return Path(config_dir) / _DEFAULT_DB_NAME
    return Path(_DEFAULT_DB_NAME)


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Open (or create) a SQLite connection with sensible defaults."""
    path = db_path or get_db_path()
    conn = sqlite3.connect(str(path), detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create tables if they do not already exist."""
    conn.executescript(_SCHEMA_SQL)
    
    # Simple migration: add DESCRIPTION column if it doesn't exist
    try:
        conn.execute("ALTER TABLE tb_control ADD COLUMN DESCRIPTION VARCHAR")
    except sqlite3.OperationalError:
        pass  # Column already exists
        
    log.info("Database schema initialized.")


# ── tb_control CRUD ──────────────────────────────────────────────────


def insert_control_record(conn: sqlite3.Connection, record: ControlRecord) -> int:
    """Insert a control record and return its row ID."""
    cursor = conn.execute(
        """
        INSERT INTO tb_control
            (DELIVERY_ID, INVOICE, DSNO_FILENAME, CREATION_DATE,
             STATUS, FREIGHT_ORACLE, FREIGHT_SOFTWAY, DESCRIPTION)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.delivery_id, record.invoice, record.dsno_filename,
            record.creation_date, record.status,
            record.freight_oracle, record.freight_softway,
            record.description,
        ),
    )
    conn.commit()
    return cursor.lastrowid


def upsert_control_record(conn: sqlite3.Connection, record: ControlRecord) -> int:
    """Insert or update a control record keyed by DSNO_FILENAME."""
    cursor = conn.execute(
        """
        INSERT INTO tb_control
            (DELIVERY_ID, INVOICE, DSNO_FILENAME, CREATION_DATE,
             STATUS, FREIGHT_ORACLE, FREIGHT_SOFTWAY, DESCRIPTION)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (DSNO_FILENAME) DO UPDATE SET
            DELIVERY_ID     = COALESCE(excluded.DELIVERY_ID, tb_control.DELIVERY_ID),
            INVOICE         = excluded.INVOICE,
            CREATION_DATE   = excluded.CREATION_DATE,
            STATUS          = COALESCE(excluded.STATUS, tb_control.STATUS),
            FREIGHT_ORACLE  = COALESCE(excluded.FREIGHT_ORACLE, tb_control.FREIGHT_ORACLE),
            FREIGHT_SOFTWAY = COALESCE(excluded.FREIGHT_SOFTWAY, tb_control.FREIGHT_SOFTWAY),
            DESCRIPTION     = COALESCE(excluded.DESCRIPTION, tb_control.DESCRIPTION)
        """,
        (
            record.delivery_id, record.invoice, record.dsno_filename,
            record.creation_date, record.status,
            record.freight_oracle, record.freight_softway,
            record.description,
        ),
    )
    conn.commit()
    return cursor.lastrowid


def get_control_pairs(
    conn: sqlite3.Connection,
    start: datetime,
    end: datetime,
    status_filter: list[str] | None = None,
) -> list[tuple[int, str, str | None, str | None]]:
    """Return ``(invoice, dsno_filename, freight_oracle, freight_softway)`` tuples.

    Mirrors ``control_reader.get_invoice_dsno_pairs`` but reads from SQLite.
    """
    query = """
        SELECT INVOICE, DSNO_FILENAME, FREIGHT_ORACLE, FREIGHT_SOFTWAY
        FROM tb_control
        WHERE CREATION_DATE >= ? AND CREATION_DATE <= ?
    """
    params: list = [start.isoformat(), end.isoformat()]

    if status_filter:
        placeholders = ",".join("?" for _ in status_filter)
        query += f"""
            AND (
                STATUS IS NULL
                OR TRIM(LOWER(STATUS)) = ''
                OR TRIM(LOWER(STATUS)) IN ({placeholders})
            )
        """
        params.extend(s.lower().strip() for s in status_filter)

    query += " ORDER BY CREATION_DATE"
    rows = conn.execute(query, params).fetchall()
    return [
        (row["INVOICE"], row["DSNO_FILENAME"], row["FREIGHT_ORACLE"], row["FREIGHT_SOFTWAY"])
        for row in rows
    ]


def get_status_options(conn: sqlite3.Connection) -> list[str]:
    """Return sorted unique non-null status values.

    Returns an empty list if fewer than two distinct values exist
    (matching the spreadsheet-based behaviour).
    """
    rows = conn.execute(
        """
        SELECT DISTINCT STATUS FROM tb_control
        WHERE STATUS IS NOT NULL AND TRIM(STATUS) != ''
        ORDER BY STATUS
        """
    ).fetchall()
    values = [row["STATUS"] for row in rows]
    return values if len(values) > 1 else []


def update_status(
    conn: sqlite3.Connection,
    dsno_filename: str,
    new_status: str,
) -> bool:
    """Update the STATUS of a control record by DSNO filename."""
    cursor = conn.execute(
        "UPDATE tb_control SET STATUS = ? WHERE DSNO_FILENAME = ?",
        (new_status, dsno_filename),
    )
    conn.commit()
    return cursor.rowcount > 0


def update_statuses_for_processed(
    conn: sqlite3.Connection,
    processed_filenames: set[str],
) -> int:
    """Bulk-update STATUS to ``'Processed'`` for all matching DSNO filenames.

    Returns the number of rows updated.
    """
    if not processed_filenames:
        return 0

    updated = 0
    for filename in processed_filenames:
        cursor = conn.execute(
            """
            UPDATE tb_control SET STATUS = 'Processed'
            WHERE DSNO_FILENAME = ? AND (STATUS IS NULL OR STATUS != 'Processed')
            """,
            (filename,),
        )
        updated += cursor.rowcount
    conn.commit()
    return updated


# ── tb_shipment_info CRUD ────────────────────────────────────────────


def insert_shipment(conn: sqlite3.Connection, record: ShipmentRecord) -> int:
    """Insert a shipment record and return its row ID."""
    cursor = conn.execute(
        """
        INSERT INTO tb_shipment_info
            (DELIVERY_ID, ESN, INVOICE, BOOKING, CONTAINER)
        VALUES (?, ?, ?, ?, ?)
        """,
        (record.delivery_id, record.esn, record.invoice,
         record.booking, record.container),
    )
    conn.commit()
    return cursor.lastrowid


def upsert_shipment(conn: sqlite3.Connection, record: ShipmentRecord) -> int:
    """Insert or update a shipment record.

    When ``ESN`` is provided and conflicts, the existing row is updated.
    When ``ESN`` is ``None``, a new row is always inserted (SQLite treats
    each ``NULL`` as distinct for ``UNIQUE`` constraints).
    """
    cursor = conn.execute(
        """
        INSERT INTO tb_shipment_info
            (DELIVERY_ID, ESN, INVOICE, BOOKING, CONTAINER)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (ESN) DO UPDATE SET
            DELIVERY_ID = COALESCE(excluded.DELIVERY_ID, tb_shipment_info.DELIVERY_ID),
            INVOICE     = excluded.INVOICE,
            BOOKING     = excluded.BOOKING,
            CONTAINER   = excluded.CONTAINER
        """,
        (record.delivery_id, record.esn, record.invoice,
         record.booking, record.container),
    )
    conn.commit()
    return cursor.lastrowid


def get_shipment_info(
    conn: sqlite3.Connection,
    invoice: int,
) -> ShipmentRecord | None:
    """Look up shipping details for *invoice*.

    Returns the first matching :class:`ShipmentRecord`, or ``None``.
    """
    row = conn.execute(
        "SELECT * FROM tb_shipment_info WHERE INVOICE = ? LIMIT 1",
        (invoice,),
    ).fetchone()

    if row is None:
        return None

    return ShipmentRecord(
        id=row["ID"],
        created_at=row["CREATED_AT"],
        delivery_id=row["DELIVERY_ID"],
        esn=row["ESN"],
        invoice=row["INVOICE"],
        booking=row["BOOKING"],
        container=row["CONTAINER"],
    )


# ── Import from spreadsheets ────────────────────────────────────────


def import_customer_sheet(
    conn: sqlite3.Connection,
    excel_path: Path | str,
    invoice_col: str = "Invoice",
    booking_col: str = "Booking/HAWB",
    container_col: str = "Container",
    sheet_name: str | int | None = None,
) -> tuple[int, int]:
    """Import rows from a customer spreadsheet into ``tb_shipment_info``.

    Args:
        conn: Open database connection.
        excel_path: Path to the Excel file.
        invoice_col: Column name for invoice number.
        booking_col: Column name (or list of aliases) for booking/HAWB.
        container_col: Column name for container.
        sheet_name: Specific worksheet name/index, or ``None`` for first sheet.

    Returns:
        Tuple of ``(imported_count, skipped_count)``.
    """
    import pandas as pd

    path = Path(excel_path)
    if not path.exists():
        raise FileNotFoundError(f"Customer sheet not found: {path}")

    if sheet_name is not None:
        df = pd.read_excel(path, sheet_name=sheet_name)
    else:
        # Scan sheets to find one with the required columns
        xls = pd.ExcelFile(path)
        sheet_names = xls.sheet_names
        df = None
        
        inv_col_upper = invoice_col.upper()
        # Resolve booking column: accept a single name or a list of aliases
        booking_aliases = (
            [b.upper() for b in booking_col]
            if isinstance(booking_col, (list, tuple))
            else [booking_col.upper()]
        )

        for name in sheet_names:
            candidate = pd.read_excel(xls, sheet_name=name)
            cols = (
                candidate.columns.astype(str)
                .str.strip()
                .str.upper()
                .str.replace(r"\s+", " ", regex=True)
            )
            candidate.columns = cols
            
            has_inv = inv_col_upper in cols
            has_bk = any(a in cols for a in booking_aliases)
            
            if has_inv and has_bk:
                df = candidate
                break
                
        if df is None:
            # Fall back to first sheet to throw a clear error
            df = pd.read_excel(xls, sheet_name=0)

    # Normalize headers one more time (in case we fell back, or sheet_name was specified)
    df.columns = (
        df.columns.astype(str)
        .str.strip()
        .str.upper()
        .str.replace(r"\s+", " ", regex=True)
    )

    inv_col = invoice_col.upper()
    cnt_col = container_col.upper()

    # Resolve booking column alias for the loaded dataframe
    booking_aliases = (
        [b.upper() for b in booking_col]
        if isinstance(booking_col, (list, tuple))
        else [booking_col.upper()]
    )
    bk_col = next((a for a in booking_aliases if a in df.columns), booking_aliases[0])

    required = {inv_col, bk_col}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    imported = 0
    skipped = 0

    for _, row in df.iterrows():
        invoice_val = row.get(inv_col)
        if pd.isna(invoice_val):
            skipped += 1
            continue

        booking = str(row.get(bk_col, "")).strip()
        container = str(row.get(cnt_col, "")).strip() if cnt_col in df.columns else ""

        if booking.lower() in ("nan", ""):
            booking = ""
        if container.lower() in ("nan", ""):
            container = ""

        record = ShipmentRecord(
            invoice=int(invoice_val),
            booking=booking,
            container=container,
        )
        try:
            insert_shipment(conn, record)
            imported += 1
        except sqlite3.IntegrityError:
            skipped += 1
        except Exception as exc:
            log.warning("Skipping invoice %s: %s", invoice_val, exc)
    log.info("Imported %d shipment records from %s (%d skipped)", imported, path.name, skipped)
    return imported, skipped


def import_control_sheet(
    conn: sqlite3.Connection,
    excel_path: Path | str,
    invoice_col: str | None = None,
    dsno_col: str | None = None,
    date_col: str | None = None,
    status_col: str | None = None,
    oracle_freight_col: str | None = None,
    softway_freight_col: str | None = None,
    description_col: str | None = None,
    sheet_name: str | int | None = None,
) -> tuple[int, int]:
    """Import rows from a control spreadsheet into ``tb_control``.

    Args:
        conn: Open database connection.
        excel_path: Path to the Excel file.
        invoice_col: Column name for invoice number.
        dsno_col: Column name for DSNO filename.
        date_col: Column name for creation date.
        status_col: Column name for status.
        oracle_freight_col: Column name for Oracle freight.
        softway_freight_col: Column name for Softway freight.
        description_col: Column name for description/obs.
        sheet_name: Specific worksheet name/index.

    Returns:
        Tuple of ``(imported_count, skipped_count)``.
    """
    import pandas as pd
    from .config import load_config

    path = Path(excel_path)
    if not path.exists():
        raise FileNotFoundError(f"Control sheet not found: {path}")

    kwargs: dict = {}
    if sheet_name is not None:
        kwargs["sheet_name"] = sheet_name

    df = pd.read_excel(path, **kwargs)

    # Normalize headers
    df.columns = (
        df.columns.astype(str)
        .str.strip()
        .str.upper()
        .str.replace(r"\s+", " ", regex=True)
    )

    cfg = load_config()

    inv_col = (invoice_col or cfg.CONTROL_INVOICE_COL).upper()
    dsno_c = (dsno_col or cfg.DSNO_COL).upper()
    dt_col = (date_col or cfg.DATE_COL).upper()
    stat_col = (status_col or cfg.STATUS_COL).upper()
    ora_col = (oracle_freight_col or cfg.FREIGHT_ORACLE_COL).upper()
    sft_col = (softway_freight_col or cfg.FREIGHT_SOFTWAY_COL).upper()
    desc_col = (description_col or cfg.DESCRIPTION_COL).upper()

    required = {inv_col, dsno_c, dt_col}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns in control sheet: {missing}")

    imported = 0
    skipped = 0

    # Ensure optional columns exist
    for col in [stat_col, ora_col, sft_col, desc_col]:
        if col not in df.columns:
            df[col] = pd.NA

    df[dt_col] = pd.to_datetime(df[dt_col], errors="coerce")

    # Garante que não haverá DSNO repetidos importados da planilha
    df = df.drop_duplicates(subset=[dsno_c], keep='first')

    for _, row in df.iterrows():
        invoice_val = row.get(inv_col)
        dsno_val = row.get(dsno_c)
        if pd.isna(invoice_val) or pd.isna(dsno_val) or str(dsno_val).strip() == "":
            skipped += 1
            continue

        date_val = row.get(dt_col)
        date_val = date_val.to_pydatetime() if pd.notna(date_val) else None

        stat_val = str(row.get(stat_col, "")).strip()
        ora_val = str(row.get(ora_col, "")).strip()
        sft_val = str(row.get(sft_col, "")).strip()
        desc_val = str(row.get(desc_col, "")).strip()

        if stat_val.lower() in ("nan", "nat", ""):
            stat_val = ""
        if ora_val.lower() in ("nan", "nat", ""):
            ora_val = ""
        if sft_val.lower() in ("nan", "nat", ""):
            sft_val = ""
        if desc_val.lower() in ("nan", "nat", ""):
            desc_val = ""

        record = ControlRecord(
            invoice=int(invoice_val),
            dsno_filename=str(dsno_val).strip(),
            creation_date=date_val,
            status=stat_val,
            freight_oracle=ora_val,
            freight_softway=sft_val,
            description=desc_val,
        )
        try:
            upsert_control_record(conn, record)
            imported += 1
        except Exception as exc:
            log.warning("Skipping DSNO %s: %s", dsno_val, exc)
            skipped += 1

    log.info("Imported %d control records from %s (%d skipped)", imported, path.name, skipped)
    return imported, skipped
