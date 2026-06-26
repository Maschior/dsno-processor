"""JS-callable API for the pywebview frontend.

This is the web-UI equivalent of ``gui/presenters/app_presenter.py``: it wires
the React frontend to the unchanged ``dsno_processor`` backend. Every heavy
operation runs in a daemon thread (same pattern as ``_run_background``) and
streams progress to JS via ``window.evaluate_js(window.__onProgress(...))``.
"""

from __future__ import annotations

import json
import logging
import threading

import webview

from dsno_processor import process_dsno
from dsno_processor.config import (
    _config_to_dict,
    _dict_to_config,
    load_config,
    save_config,
)
from dsno_processor.ebs_download import DownloadConfig, run_download
from dsno_processor.ebs_upload import UploadConfig, run_upload
from dsno_processor.exceptions import CanceledError, LoginError

log = logging.getLogger(__name__)


class Api:
    """Methods here are callable from JS as ``pywebview.api.<name>(...)``."""

    def __init__(self) -> None:
        # Must stay underscore-private: pywebview walks public attrs of js_api to
        # expose them to JS and would recurse into the native window forever.
        self._window: webview.Window | None = None  # set in start_webui()
        self._events: dict[str, threading.Event] = {}

    # ── Progress bridge ──────────────────────────────────────────────
    def _bridge(self, op: str):
        """Build a ``(event, data)`` callback that forwards events to JS."""

        def cb(event: str, data: dict) -> None:
            if not self._window:
                return
            payload = json.dumps({"op": op, "event": event, "data": data or {}})
            # ponytail: evaluate_js is thread-safe in pywebview; no UI-thread marshalling needed
            self._window.evaluate_js(f"window.__onProgress({payload})")

        return cb

    def _run(self, op: str, target, *args) -> None:
        self._events[op] = threading.Event()
        cb = self._bridge(op)

        def worker():
            try:
                target(cb, self._events[op], *args)
            except CanceledError:
                cb("cancelled", {"name": "System", "detail": "Cancelled by user"})
            except LoginError as exc:
                cb("error", {"name": "Login", "detail": str(exc)})
            except Exception as exc:  # noqa: BLE001 — surface any failure to the UI
                log.exception("Operation %s failed", op)
                cb("error", {"name": "Process", "detail": str(exc)})

        threading.Thread(target=worker, name=f"webui-{op}", daemon=True).start()

    def cancel(self, op: str) -> None:
        """Signal a running operation to abort (op = process|download|upload)."""
        ev = self._events.get(op)
        if ev:
            ev.set()

    # ── Data prep (fast, synchronous — return counts straight to JS) ──
    # These mirror the CustomTkinter import wizards / status sync, reusing the
    # same dsno_processor domain functions. No progress bridge needed.
    def import_customer_to_db(self, path: str) -> dict:
        """Import a customer sheet into the local DB. Mirrors ImportWizard."""
        from dsno_processor.database import (
            get_connection,
            get_db_path,
            import_customer_sheet,
            init_db,
        )

        cfg = load_config()
        conn = get_connection(get_db_path())
        init_db(conn)
        try:
            imported, skipped = import_customer_sheet(
                conn,
                path,
                invoice_col=cfg.customer_sheet_cols.invoice,
                booking_col=cfg.customer_sheet_cols.booking,
                container_col=cfg.customer_sheet_cols.container,
                sheet_name=cfg.customer_sheet_properties.sheet_name or None,
            )
        finally:
            conn.close()
        return {"imported": imported, "skipped": skipped}

    def import_control_to_db(self, path: str) -> dict:
        """Import a control sheet into the local DB. Mirrors ImportControlWizard."""
        from dsno_processor.database import (
            get_connection,
            get_db_path,
            import_control_sheet,
            init_db,
        )

        cols = load_config().control_sheet_cols
        conn = get_connection(get_db_path())
        init_db(conn)
        try:
            imported, updated, skipped = import_control_sheet(
                conn,
                path,
                invoice_col=cols.invoice,
                dsno_col=cols.dsno,
                date_col=cols.date,
                status_col=cols.status,
                oracle_freight_col=cols.freight_oracle,
                softway_freight_col=cols.freight_softway,
                description_col=cols.description,
            )
        finally:
            conn.close()
        return {"imported": imported, "updated": updated, "skipped": skipped}

    def get_control_statuses(self, date_start: str = "", date_end: str = "") -> list:
        """Return distinct STATUS values from tb_control, optionally filtered by date range.

        date_start / date_end may be in HTML datetime-local format (YYYY-MM-DDTHH:MM).
        Falls back to all statuses when the DB is empty or unavailable.
        """
        from dsno_processor.database import get_connection, get_db_path, init_db

        try:
            conn = get_connection(get_db_path())
            init_db(conn)
            try:
                s = date_start.replace("T", " ") if date_start else ""
                e = date_end.replace("T", " ") if date_end else ""
                if s and e:
                    rows = conn.execute(
                        "SELECT DISTINCT STATUS FROM tb_control"
                        " WHERE CREATION_DATE BETWEEN ? AND ? AND STATUS IS NOT NULL ORDER BY STATUS",
                        (s, e),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT DISTINCT STATUS FROM tb_control WHERE STATUS IS NOT NULL ORDER BY STATUS"
                    ).fetchall()
                return [r[0] for r in rows]
            finally:
                conn.close()
        except Exception:
            return []

    def get_records(self, kind: str = "control") -> dict:
        """Return ``{columns, rows}`` from the internal DB for the records viewer.

        ``kind`` is ``"control"`` (tb_control) or ``"shipment"`` (tb_shipment_info).
        Best-effort: returns empty columns/rows if the DB is missing or unreadable.
        """
        from dsno_processor.database import (
            get_connection,
            get_db_path,
            init_db,
            list_control,
            list_shipments,
        )

        try:
            conn = get_connection(get_db_path())
            init_db(conn)
            try:
                columns, rows = (
                    list_shipments(conn) if kind == "shipment" else list_control(conn)
                )
            finally:
                conn.close()
            return {"columns": columns, "rows": rows}
        except Exception:  # noqa: BLE001 — viewer should never crash the UI
            return {"columns": [], "rows": []}

    def sync_oracle_pending(self) -> dict:
        """Step 1: pull the last N months of pending DSNOs from Oracle into the DB.

        Connection settings come from ``config.oracle``. Only new DSNOs are
        inserted; existing records keep their current status.
        """
        from dsno_processor.database import get_connection, get_db_path, init_db
        from dsno_processor.oracle_source import sync_oracle_pending

        cfg = load_config()
        conn = get_connection(get_db_path())
        init_db(conn)
        try:
            imported, skipped, columns, rows = sync_oracle_pending(conn, cfg.oracle)
        finally:
            conn.close()
        return {"imported": imported, "skipped": skipped, "columns": columns, "rows": rows}

    def sync_status(self, control_path: str, dsno_dir: str) -> dict:
        """Sync control-sheet + DB statuses. Mirrors _sync_status_thread."""
        from pathlib import Path

        from dsno_processor.status_updater import (
            update_control_sheet_status,
            update_excel_status_for_downloaded,
        )

        processed = downloaded = 0
        processed_dir = Path(dsno_dir) / "Processed"
        if processed_dir.exists():
            processed = update_control_sheet_status(control_path, str(processed_dir))

        try:
            dl_dir = str(load_config().paths.dsno_directory) or dsno_dir
        except Exception:  # noqa: BLE001 — fall back to the given dir
            dl_dir = dsno_dir
        if Path(dl_dir).exists():
            downloaded = update_excel_status_for_downloaded(control_path, dl_dir)

        # Mirror DB statuses too (best-effort, matches the CTk path).
        try:
            from dsno_processor.database import (
                get_connection,
                get_db_path,
                update_statuses_for_downloaded,
                update_statuses_for_processed,
            )

            db_path = get_db_path()
            if db_path.exists():
                conn = get_connection(db_path)
                if processed_dir.exists():
                    pf = {f.name for f in processed_dir.iterdir() if f.is_file()}
                    if pf:
                        update_statuses_for_processed(conn, pf)
                if Path(dl_dir).exists():
                    df = {f.name for f in Path(dl_dir).iterdir() if f.is_file()}
                    if df:
                        update_statuses_for_downloaded(conn, df)
                conn.close()
        except Exception as exc:  # noqa: BLE001 — DB sync is optional
            log.warning("Could not update database statuses: %s", exc)

        return {"processed": processed, "downloaded": downloaded}


    # ── Config round-trip ────────────────────────────────────────────
    def get_config(self) -> dict:
        """Return the current config as a JSON-friendly nested dict."""
        return _config_to_dict(load_config())

    def save_config(self, data: dict) -> None:
        """Persist a config dict (same shape as :meth:`get_config`)."""
        save_config(_dict_to_config(data))

    def export_config(self) -> str:
        """Write the current config to a user-chosen file. Returns the path or ''."""
        dest = self._window.create_file_dialog(
            webview.SAVE_DIALOG,
            save_filename="config.toml",
            file_types=("TOML (*.toml)", "All files (*.*)"),
        )
        if not dest:
            return ""
        path = dest if isinstance(dest, str) else dest[0]
        save_config(load_config(), path)  # normalises + exports the effective config
        return path

    # ── Native file dialogs ──────────────────────────────────────────
    def browse_file(self, excel: bool = True) -> str:
        types = ("Excel Files (*.xlsx;*.xls)",) if excel else ("All files (*.*)",)
        result = self._window.create_file_dialog(
            webview.OPEN_DIALOG, file_types=types
        )
        return result[0] if result else ""

    def browse_dir(self) -> str:
        result = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        return result[0] if result else ""

    # ── Operations ───────────────────────────────────────────────────
    def start_processing(self, form: dict) -> None:
        def target(cb, cancel, form):
            process_dsno(
                date_range=f"{form['start']};{form['end']}",
                customer_sheet=form["customer_sheet"],
                control_sheet=form["control_sheet"],
                dsno_dir=form["dsno_dir"],
                freight_mode=form.get("freight_mode", "SEA"),
                progress_callback=cb,
                cancel_event=cancel,
                status_filter=form.get("status_filter") or [],
            )

        self._run("process", target, form)

    def start_download(self, form: dict) -> None:
        cfg = load_config()
        try:
            folders = [int(x) for x in str(form.get("folders", "")).split(",") if x.strip()]
        except ValueError:
            folders = [92, 95, 101]

        config = DownloadConfig(
            ebs_url=form["url"],
            customer_sheet_path=form["sheet"],
            download_dir=form["dir"],
            email=cfg.credentials.email,
            password=cfg.credentials.password,
            dsno_col=form.get("dsno_col", "ARGUMENT2"),
            date_col=form.get("date_col", "CREATION_DATE"),
            status_col=form.get("status_col", "STATUS"),
            date_start=form.get("date_start", ""),
            date_end=form.get("date_end", ""),
            status_filter=form.get("status_filter", ""),
            headless=cfg.ebs.headless,
            folder_indices=folders,
        )

        def target(cb, cancel, config):
            run_download(config, progress_callback=cb, cancel_event=cancel)

        self._run("download", target, config)

    def start_upload(self, form: dict) -> None:
        cfg = load_config()
        try:
            folder_idx = int(form.get("folder", 92))
        except ValueError:
            folder_idx = 92

        config = UploadConfig(
            ebs_url=form["url"],
            upload_dir=form["dir"],
            email=cfg.credentials.email,
            password=cfg.credentials.password,
            folder_index=folder_idx,
            headless=cfg.ebs.headless,
        )

        def target(cb, cancel, config):
            run_upload(config, progress_callback=cb, cancel_event=cancel)

        self._run("upload", target, config)
