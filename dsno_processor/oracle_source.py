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
# range are bound at runtime; the window is always "the last N months".
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


@dataclass
class _Row:
    """Positional decoding of a :data:`_QUERY` result row."""

    delivery_id: int | None
    creation_date: datetime | None
    dsno: str | None
    invoice: object
    freight_oracle: str | None
    freight_softway: str | None


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

    return ControlRecord(
        delivery_id=row.delivery_id,
        invoice=invoice,
        dsno_filename=dsno,
        creation_date=row.creation_date,
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


def sync_oracle_pending(
    conn: sqlite3.Connection,
    oracle_cfg: OracleConfig,
) -> tuple[int, int]:
    """Fetch the last N months of pending deliveries and insert the new ones.

    Returns ``(imported, skipped)``. Existing DSNOs are skipped untouched so
    their current status is preserved.
    """
    if not (oracle_cfg.user and oracle_cfg.dsn and oracle_cfg.customer_id):
        raise ValueError(
            "Oracle connection not configured (user, dsn and customer_id required)."
        )

    import oracledb  # local import: optional dependency, only needed for step 1

    start, end = _date_window(oracle_cfg.lookback_months)
    log.info(
        "Oracle sync: customer %s, window %s → %s",
        oracle_cfg.customer_id, start.isoformat(), end.isoformat(),
    )

    with oracledb.connect(
        user=oracle_cfg.user,
        password=oracle_cfg.password,
        dsn=oracle_cfg.dsn,
    ) as ora:
        with ora.cursor() as cur:
            cur.execute(
                _QUERY,
                customer_id=oracle_cfg.customer_id,
                start_date=start,
                end_date=end,
            )
            rows = cur.fetchall()

    imported = 0
    skipped = 0
    for raw in rows:
        record = _row_to_record(_Row(*raw))
        if record is None or insert_control_if_absent(conn, record) is False:
            skipped += 1
        else:
            imported += 1

    log.info("Oracle sync done: %d new, %d skipped", imported, skipped)
    return imported, skipped


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
