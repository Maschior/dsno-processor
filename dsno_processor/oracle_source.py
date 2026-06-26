"""Oracle source-database sync — step 1 of the workflow.

Pulls the last ``lookback_months`` of pending DSNO deliveries for a customer
from the Oracle EBS database and inserts the *new* ones into the internal
SQLite ``tb_control`` table. Existing records are never touched, so a DSNO's
current status is preserved across syncs.

Connection settings come from ``config.oracle`` (:class:`OracleConfig`).
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from .config import OracleConfig
from .database import ControlRecord, insert_control_if_absent

log = logging.getLogger(__name__)


# Pending deliveries for a customer in a date window. Customer id and the date
# range are bound at runtime; the window is always "the last N months". Written
# with named binds for readability; the executed form is the positional-? JDBC
# version below (jaydebeapi).
_QUERY = """
SELECT WND.DELIVERY_ID
     , WND.CREATION_DATE
     , FCR.ARGUMENT2
     , RILA.ATTRIBUTE14
     , WND.FREIGHT_TERMS_CODE AS FRETE_ORACLE
     , TRS.DESCRICAO          AS FRETE_SOFTWAY
  FROM APPS.WSH_NEW_DELIVERIES WND
 INNER JOIN APPS.WSH_DELIVERY_STOPS_V WDS
    ON WDS.DELIVERY_ID = WND.DELIVERY_ID
   AND WDS.STOP_LOCATION_ID = WND.INITIAL_PICKUP_LOCATION_ID
  LEFT OUTER JOIN APPS.FND_CONCURRENT_REQUESTS FCR
    ON FCR.ARGUMENT5 = WDS.STOP_ID
   AND FCR.ARGUMENT3 = 'DSNO'
  LEFT OUTER JOIN APPS.RA_INTERFACE_LINES_ALL RILA
    ON RILA.INTERFACE_LINE_ATTRIBUTE3 = TO_CHAR(WND.DELIVERY_ID)
   AND RILA.LINE_NUMBER = '1'
  LEFT OUTER JOIN INVOICES@LNK_SOFTWAY INV
    ON RILA.ATTRIBUTE14 = INV.NUM_INVOICE
  LEFT OUTER JOIN SFW_TAB_VIA_TRANSPORTE_SISCOME@LNK_SOFTWAY TRS
    ON INV.TP_VIA_TRANSP = TRS.CODIGO
 WHERE WND.CUSTOMER_ID = :customer_id
   AND WND.CREATION_DATE BETWEEN :start_date AND :end_date
 ORDER BY WND.CREATION_DATE
"""

# DBAPI2 positional form used by jaydebeapi/JDBC.
_QUERY_JDBC = _QUERY.replace(":customer_id", "?").replace(":start_date", "?").replace(":end_date", "?")

# Full original query — display only (see PendenciasTab). Same window/customer as
# _QUERY so the table mirrors what the import considered. Dates come back as
# strings via TO_CHAR, so the result is JSON-safe as-is.
_PREVIEW_QUERY = """
SELECT WND.DELIVERY_ID
     , TO_CHAR(WND.CREATION_DATE, 'DD/MM/YYYY HH24:MI:SS') AS CREATION_DATE
     , TO_CHAR(WND.ASN_DATE_SENT, 'DD/MM/YYYY HH24:MI:SS') AS ASN_DATE_SENT
     , WDS.STOP_ID
     , WDS.TRIP_ID
     , FCR.REQUEST_ID
     , FCR.ARGUMENT1
     , FCR.ARGUMENT2
     , FCR.ARGUMENT5
     , RILA.ATTRIBUTE14
     , 'Pendente'             AS STATUS
     , WND.FREIGHT_TERMS_CODE  AS FRETE_ORACLE
     , TRS.DESCRICAO           AS FRETE_SOFTWAY
     , WND.CREATION_DATE       AS CREATION_DATE_ORDER
  FROM APPS.WSH_NEW_DELIVERIES WND
 INNER JOIN APPS.WSH_DELIVERY_STOPS_V WDS
    ON WDS.DELIVERY_ID = WND.DELIVERY_ID
   AND WDS.STOP_LOCATION_ID = WND.INITIAL_PICKUP_LOCATION_ID
  LEFT OUTER JOIN APPS.FND_CONCURRENT_REQUESTS FCR
    ON FCR.ARGUMENT5 = WDS.STOP_ID
   AND FCR.ARGUMENT3 = 'DSNO'
  LEFT OUTER JOIN APPS.RA_INTERFACE_LINES_ALL RILA
    ON RILA.INTERFACE_LINE_ATTRIBUTE3 = TO_CHAR(WND.DELIVERY_ID)
   AND RILA.LINE_NUMBER = '1'
  LEFT OUTER JOIN INVOICES@LNK_SOFTWAY INV
    ON RILA.ATTRIBUTE14 = INV.NUM_INVOICE
  LEFT OUTER JOIN SFW_TAB_VIA_TRANSPORTE_SISCOME@LNK_SOFTWAY TRS
    ON INV.TP_VIA_TRANSP = TRS.CODIGO
 WHERE WND.CUSTOMER_ID = :customer_id
   AND WND.CREATION_DATE BETWEEN :start_date AND :end_date
 ORDER BY CREATION_DATE_ORDER
"""

_PREVIEW_QUERY_JDBC = (
    _PREVIEW_QUERY.replace(":customer_id", "?").replace(":start_date", "?").replace(":end_date", "?")
)


@dataclass
class _Row:
    """Positional decoding of a :data:`_QUERY` result row."""

    delivery_id: int | None
    creation_date: datetime | None
    dsno: str | None
    invoice: object
    freight_oracle: str | None
    freight_softway: str | None


def _resolve_jvm(jvm_path: str) -> str | None:
    """Return the path to jvm.dll/.so/.dylib from a JDK home, bin dir, or direct path."""
    if not jvm_path:
        return None
    import sys
    from pathlib import Path

    p = Path(jvm_path)
    if p.is_file():
        return str(p)
    # Strip trailing /bin so both "jdk_home" and "jdk_home/bin" work.
    if p.name.lower() == "bin":
        p = p.parent
    lib_name = "jvm.dll" if sys.platform == "win32" else ("libjvm.dylib" if sys.platform == "darwin" else "libjvm.so")
    candidate = p / "bin" / "server" / lib_name
    return str(candidate) if candidate.exists() else str(p / "lib" / "server" / lib_name)


def _connect_jdbc(oracle_cfg: OracleConfig):
    """jaydebeapi connection using the Oracle JDBC thin driver.

    JDBC handles old password verifiers (e.g. 10g 0x939) since it uses the same
    auth path as the Java client, and needs no Oracle Client install.

    The jar must be on the classpath at JVM startup — jpype cannot add it after
    the JVM is already running, so we start it ourselves with classpath set.
    """
    import jaydebeapi  # noqa: PLC0415
    import jpype

    if not jpype.isJVMStarted():
        jvm = _resolve_jvm(oracle_cfg.jvm_path) or jpype.getDefaultJVMPath()
        log.debug("Starting JVM: %s  classpath: %s", jvm, oracle_cfg.jdbc_jar)
        jpype.startJVM(jvm, classpath=[oracle_cfg.jdbc_jar], convertStrings=True)

    dsn = oracle_cfg.dsn
    if not dsn.startswith("jdbc:"):
        dsn = f"jdbc:oracle:thin:@{dsn}"
    # Jar already on classpath — don't pass it again or jaydebeapi tries addClassPath.
    return jaydebeapi.connect(
        "oracle.jdbc.OracleDriver",
        dsn,
        [oracle_cfg.user, oracle_cfg.password],
    )


def _row_to_record(row: _Row) -> ControlRecord | None:
    """Map an Oracle row to a ``ControlRecord``, or ``None`` if not importable.

    Rows without a DSNO (``ARGUMENT2``) or a numeric invoice (``ATTRIBUTE14``)
    are not yet processable into ``tb_control`` (both columns are NOT NULL) and
    are skipped by the caller.
    """
    dsno = (str(row.dsno).strip() if row.dsno is not None else "")
    if not dsno:
        return None
    try:
        invoice = int(row.invoice)
    except (TypeError, ValueError):
        return None

    # JDBC may return creation_date as a string; coerce to datetime when needed.
    creation_date = row.creation_date
    if creation_date is not None and not isinstance(creation_date, datetime):
        try:
            creation_date = datetime.fromisoformat(str(creation_date)[:19])
        except (ValueError, TypeError):
            creation_date = None

    return ControlRecord(
        delivery_id=row.delivery_id,
        invoice=invoice,
        dsno_filename=dsno,
        creation_date=creation_date,
        status="Pendente",  # new records start pending; existing ones are untouched
        freight_oracle=(str(row.freight_oracle).strip() if row.freight_oracle else ""),
        freight_softway=(str(row.freight_softway).strip() if row.freight_softway else ""),
    )


def _date_window(months: int, now: datetime | None = None) -> tuple[datetime, datetime]:
    """Return ``(start, end)`` for the last *months* months ending now."""
    end = now or datetime.now()
    # Subtract whole months without a date lib: walk the (year, month) back.
    y, m = end.year, end.month - months
    while m <= 0:
        m += 12
        y -= 1
    day = min(end.day, 28)  # clamp to keep a valid date in any month
    start = end.replace(year=y, month=m, day=day)
    return start, end


def _query_runner(oracle_cfg: OracleConfig, start: datetime, end: datetime):
    """Open one JDBC connection; return ``(run, close)``.

    ``run(query)`` executes a SELECT with ``customer_id`` and the date window
    already bound (positional ``?`` binds), returning ``(columns, rows)``.
    Keeping a single connection lets the import and preview queries share a session.
    """
    log.debug("Using JDBC driver: %s", oracle_cfg.jdbc_jar)
    ora = _connect_jdbc(oracle_cfg)
    import jpype
    Timestamp = jpype.JClass("java.sql.Timestamp")
    binds = [oracle_cfg.customer_id, Timestamp.valueOf(start.strftime("%Y-%m-%d %H:%M:%S")),
             Timestamp.valueOf(end.strftime("%Y-%m-%d %H:%M:%S"))]

    def run(jdbc):
        cur = ora.cursor()
        cur.execute(jdbc, binds)
        return [d[0] for d in cur.description], cur.fetchall()

    return run, ora.close


def sync_oracle_pending(
    conn: sqlite3.Connection,
    oracle_cfg: OracleConfig,
) -> tuple[int, int, list[str], list[list[str]]]:
    """Fetch the last N months of pending deliveries and insert the new ones.

    Returns ``(imported, skipped, columns, rows)``. ``columns``/``rows`` are the
    full display query result (all original fields, JSON-safe strings) for the
    Pendências table. Existing DSNOs are skipped untouched so their current
    status is preserved.
    """
    if not (oracle_cfg.user and oracle_cfg.dsn and oracle_cfg.customer_id and oracle_cfg.jdbc_jar):
        raise ValueError(
            "Oracle connection not configured (user, dsn, customer_id and jdbc_jar required)."
        )

    start, end = _date_window(oracle_cfg.lookback_months)
    log.info(
        "Oracle sync: customer %s, window %s → %s",
        oracle_cfg.customer_id, start.isoformat(), end.isoformat(),
    )

    run, close = _query_runner(oracle_cfg, start, end)
    try:
        _, rows = run(_QUERY_JDBC)
        columns, preview_raw = run(_PREVIEW_QUERY_JDBC)
    finally:
        close()

    preview = [["" if c is None else str(c) for c in row] for row in preview_raw]

    # Map rows before touching the DB so a bad row never leaves a partial write.
    records = [_row_to_record(_Row(*raw)) for raw in rows]

    imported = 0
    skipped = 0
    try:
        for record in records:
            if record is None or not insert_control_if_absent(conn, record, commit=False):
                skipped += 1
            else:
                imported += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    log.info("Oracle sync done: %d new, %d skipped", imported, skipped)
    return imported, skipped, columns, preview


def _demo() -> None:
    """Self-check for the row mapping and date window (no Oracle needed)."""
    # New, importable row → mapped with status "Pendente".
    r = _row_to_record(
        _Row(123, datetime(2026, 6, 1, 9, 0), "DSNO7722817", "5551234", "PRE", "MARITIMA")
    )
    assert r is not None and r.dsno_filename == "DSNO7722817"
    assert r.invoice == 5551234 and r.status == "Pendente"

    # Missing DSNO or non-numeric invoice → not importable.
    assert _row_to_record(_Row(1, None, None, "5551234", "", "")) is None
    assert _row_to_record(_Row(1, None, "DSNO1", None, "", "")) is None

    # Two-month window lands two months earlier.
    start, end = _date_window(2, datetime(2026, 6, 26, 12, 0))
    assert (start.year, start.month) == (2026, 4), (start.year, start.month)
    assert end.month == 6
    print("oracle_source self-check OK")


if __name__ == "__main__":
    _demo()
