"""GUI action handlers that coordinate services and dialogs."""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from tkinter import filedialog, messagebox
from typing import Any

from dsno_processor import process_dsno
from dsno_processor.config import load_config, save_config
from dsno_processor.ebs_download import DownloadConfig, run_download
from dsno_processor.ebs_upload import UploadConfig, run_upload
from dsno_processor.exceptions import CanceledError, ConfigurationError, LoginError
from dsno_processor.i18n import t
from gui.dialogs.import_wizards import ImportControlWizard, ImportWizard
from gui.dialogs.language_menu import LanguageMenu
from gui.dialogs.settings_window import SettingsWindow

log = logging.getLogger(__name__)


class AppActionsMixin:
    """GUI action handlers that coordinate services and dialogs."""

    def _run_background(
        self,
        *,
        name: str,
        target: Callable[..., None],
        args: tuple[Any, ...] = (),
    ) -> None:
        """Start a named daemon worker thread for a long-running task."""
        thread = threading.Thread(target=target, args=args, name=name, daemon=True)
        thread.start()

    def _make_dashboard_progress_callback(self, dashboard):
        """Route backend progress events to a dashboard on the Tk main thread."""

        def apply_event(event: str, data: dict[str, Any]) -> None:
            if event == "phase":
                dashboard.set_phase(data["text"])
            elif event == "total":
                dashboard.reset(data["count"])
            elif event == "success":
                dashboard.mark_success(data["name"], data.get("detail", ""))
            elif event == "error":
                dashboard.mark_error(data["name"], data["detail"])
            elif event == "skipped":
                dashboard.mark_skipped(data["name"], data.get("detail", ""))
            elif event == "cancelled":
                dashboard._cancelled = True
            elif event == "finished":
                dashboard.finish()

        def callback(event: str, data: dict[str, Any]) -> None:
            self._run_on_ui_thread(apply_event, event, data)

        return callback

    def _show_info_async(self, title: str, message: str) -> None:
        """Show an info dialog from the Tk main thread."""
        self._run_on_ui_thread(messagebox.showinfo, title, message)

    def _show_error_async(self, title: str, message: str) -> None:
        """Show an error dialog from the Tk main thread."""
        self._run_on_ui_thread(messagebox.showerror, title, message)

    def _mark_dashboard_cancelled(self, dashboard, message: str) -> None:
        """Set a dashboard to the cancelled final state."""
        dashboard.set_phase(message)
        dashboard._cancelled = True
        dashboard.finish()

    def _finish_dashboard_with_error(self, dashboard, message: str) -> None:
        """Set a dashboard to an error final state."""
        dashboard.set_phase(message)
        dashboard.finish()

    def _finish_processing_ui(self) -> None:
        """Restore processor controls after worker completion."""
        self._hide_blocking_overlay()
        self._update_run_btn_state()
        self.dashboard.cancel_btn.configure(state="disabled")

    def _finish_download_ui(self) -> None:
        """Restore download controls after worker completion."""
        self._hide_blocking_overlay()
        self._update_dl_run_btn_state()
        self.dl_dashboard.cancel_btn.configure(state="disabled")

    def _finish_upload_ui(self) -> None:
        """Restore upload controls after worker completion."""
        self._hide_blocking_overlay()
        self._update_ul_run_btn_state()
        self.ul_dashboard.cancel_btn.configure(state="disabled")

    def _browse_customer(self) -> None:
        initial = (
            self._customer_pre_path if os.path.exists(self._customer_pre_path) else None
        )
        path = filedialog.askopenfilename(
            title=t("browse.customer_sheet"),
            initialdir=initial,
            filetypes=[("Excel Files", "*.xlsx *.xls")],
        )
        if path:
            self.customer_row.set(path)

    def _browse_control(self) -> None:
        current_dir = os.path.dirname(self.control_row.get())
        initial = current_dir if os.path.exists(current_dir) else None
        path = filedialog.askopenfilename(
            title=t("browse.control_sheet"),
            initialdir=initial,
            filetypes=[("Excel Files", "*.xlsx *.xls")],
        )
        if path:
            self.control_row.set(path)

    def _browse_dsno_dir(self) -> None:
        current = self.dsno_row.get()
        initial = current if os.path.exists(current) else None
        folder = filedialog.askdirectory(
            title=t("browse.dsno_directory"), initialdir=initial
        )
        if folder:
            self.dsno_row.set(folder)

    # ──────────────────────────────────────────────────────────────
    # Browse dialogs — EBS Download
    # ──────────────────────────────────────────────────────────────

    def _browse_dl_sheet(self) -> None:
        path = filedialog.askopenfilename(
            title=t("browse.customer_sheet"),
            filetypes=[("Excel Files", "*.xlsx *.xls")],
        )
        if path:
            self.dl_sheet_var.set(path)

    def _browse_dl_dir(self) -> None:
        folder = filedialog.askdirectory(title=t("browse.download_dir"))
        if folder:
            self.dl_dir_var.set(folder)

    # ──────────────────────────────────────────────────────────────
    # Browse dialogs — EBS Upload
    # ──────────────────────────────────────────────────────────────

    def _browse_ul_dir(self) -> None:
        folder = filedialog.askdirectory(title=t("browse.upload_dir"))
        if folder:
            self.ul_dir_var.set(folder)

    # ──────────────────────────────────────────────────────────────
    # Processing — Processor tab
    # ──────────────────────────────────────────────────────────────

    def _start_processing(self) -> None:
        self.run_btn.configure(state="disabled")
        self.dashboard.cancel_btn.configure(state="normal")
        self._processor_cancel_event = threading.Event()
        self._clear_log()

        date_range = f"{self.start_date.get()};{self.end_date.get()}"
        status_filter = self.filter_by_status.get_selected()  # [] means All
        args = (
            date_range,
            self.customer_row.get(),
            self.control_row.get(),
            self.dsno_row.get(),
            self.freight_mode_var.get(),
            status_filter,
            self._make_dashboard_progress_callback(self.dashboard),
        )
        self._run_background(
            name="dsno-processor", target=self._process_thread, args=args
        )

    def _process_thread(
        self,
        date_range: str,
        customer_sheet: str,
        control_sheet: str,
        dsno_dir: str,
        freight_mode: str,
        status_filter: list[str],
        progress_callback: Callable[[str, dict[str, Any]], None],
    ) -> None:
        try:
            result = process_dsno(
                date_range=date_range,
                customer_sheet=customer_sheet,
                control_sheet=control_sheet,
                dsno_dir=dsno_dir,
                freight_mode=freight_mode,
                progress_callback=progress_callback,
                cancel_event=getattr(self, "_processor_cancel_event", None),
                status_filter=status_filter,
            )

            summary = t(
                "msg.processing_complete", success=result.success, total=result.total
            )
            logging.info(summary)
            if result.failed > 0:
                self._show_info_async(
                    t("msg.complete_title"),
                    t("msg.processing_errors", summary=summary, failed=result.failed),
                )
            else:
                self._show_info_async(t("dash.success"), summary)
        except CanceledError:
            logging.info("Processing was cancelled by the user.")
            self._run_on_ui_thread(
                self._mark_dashboard_cancelled,
                self.dashboard,
                t("msg.cancelled_by_user", default="Cancelled by user"),
            )
        except LoginError as exc:
            logging.error("Login failed: %s", exc)
            self._run_on_ui_thread(
                self._finish_dashboard_with_error, self.dashboard, f"Login Error: {exc}"
            )
            self._show_error_async(t("settings.save_error_title"), str(exc))
        except Exception as exc:
            logging.error("Error during processing: %s", exc)
            self._run_on_ui_thread(
                self._finish_dashboard_with_error, self.dashboard, f"Error: {exc}"
            )
            self._show_error_async(t("settings.save_error_title"), str(exc))
        finally:
            self._run_on_ui_thread(self._finish_processing_ui)

    def _reset_current_dashboard(self) -> None:
        """Reset the dashboard and filters of the currently selected tab."""
        current_tab = self._tabview.get()
        if current_tab == self._TAB_PROC:
            # Reset dashboard
            self.dashboard.reset_to_idle()
            self._update_run_btn_state()
        elif current_tab == self._TAB_DOWNLOAD:
            # Reset dashboard
            self.dl_dashboard.reset_to_idle()
        elif current_tab == self._TAB_UPLOAD:
            # Upload doesn't have filters in the same way, just paths/index
            self.ul_dashboard.reset_to_idle()

    # ──────────────────────────────────────────────────────────────
    # Processing — EBS Download tab
    # ──────────────────────────────────────────────────────────────

    def _start_download(self) -> None:
        self.dl_start_btn.configure(state="disabled")
        self.dl_dashboard.cancel_btn.configure(state="normal")
        self._dl_cancel_event = threading.Event()
        self._dl_tabview.set(self._DL_TAB_PROGRESS)
        self._clear_log()

        try:
            folder_indices = [
                int(x.strip())
                for x in self.dl_folders_var.get().split(",")
                if x.strip()
            ]
        except ValueError:
            folder_indices = [92, 95, 101]

        cfg = self._app_config
        config = DownloadConfig(
            ebs_url=self.dl_url_var.get(),
            customer_sheet_path=self.dl_sheet_var.get(),
            download_dir=self.dl_dir_var.get(),
            email=cfg.ebs_email if cfg else "",
            password=cfg.ebs_password if cfg else "",
            dsno_col=self.dl_dsno_col_var.get(),
            date_col=self.dl_date_col_var.get(),
            status_col=self.dl_status_col_var.get(),
            date_start=self.dl_date_start.get(),
            date_end=self.dl_date_end.get(),
            status_filter=self.dl_status_filter_var.get(),
            headless=cfg.ebs_headless if cfg else False,
            folder_indices=folder_indices,
        )

        progress_cb = self._make_dashboard_progress_callback(self.dl_dashboard)
        self._run_background(
            name="dsno-ebs-download",
            target=self._download_thread,
            args=(config, progress_cb),
        )

    def _download_thread(self, config: DownloadConfig, progress_cb) -> None:
        try:
            result = run_download(
                config,
                progress_callback=progress_cb,
                cancel_event=getattr(self, "_dl_cancel_event", None),
            )
            total = result["success"] + result["skipped"] + len(result["failures"])
            summary = t(
                "msg.download_complete",
                success=result["success"],
                total=total - result["skipped"],
            )
            logging.getLogger("dsno_processor.ebs_download").info(summary)
            self._show_info_async(t("msg.download_title"), summary)
        except CanceledError:
            logging.getLogger("dsno_processor.ebs_download").info(
                "Download was cancelled by the user."
            )
            self._run_on_ui_thread(
                self._mark_dashboard_cancelled,
                self.dl_dashboard,
                t("msg.cancelled_by_user", default="Cancelled by user"),
            )
        except LoginError as exc:
            logging.getLogger("dsno_processor.ebs_download").error(
                "Login failed: %s", exc
            )
            self._run_on_ui_thread(
                self._finish_dashboard_with_error,
                self.dl_dashboard,
                f"Login Error: {exc}",
            )
            self._show_error_async(t("settings.save_error_title"), str(exc))
        except Exception as exc:
            logging.getLogger("dsno_processor.ebs_download").error("Error: %s", exc)
            self._run_on_ui_thread(
                self._finish_dashboard_with_error, self.dl_dashboard, f"Error: {exc}"
            )
            self._show_error_async(t("settings.save_error_title"), str(exc))
        finally:
            self._run_on_ui_thread(self._finish_download_ui)

    # ──────────────────────────────────────────────────────────────
    # Processing — EBS Upload tab
    # ──────────────────────────────────────────────────────────────

    def _start_upload(self) -> None:
        self.ul_start_btn.configure(state="disabled")
        self.ul_dashboard.cancel_btn.configure(state="normal")
        self._ul_cancel_event = threading.Event()
        self._ul_tabview.set(self._UL_TAB_PROGRESS)
        self._clear_log()

        try:
            folder_idx = int(self.ul_folder_var.get())
        except ValueError:
            folder_idx = 92

        cfg = self._app_config
        config = UploadConfig(
            ebs_url=self.ul_url_var.get(),
            upload_dir=self.ul_dir_var.get(),
            email=cfg.ebs_email if cfg else "",
            password=cfg.ebs_password if cfg else "",
            folder_index=folder_idx,
            headless=cfg.ebs_headless if cfg else False,
        )

        progress_cb = self._make_dashboard_progress_callback(self.ul_dashboard)
        self._run_background(
            name="dsno-ebs-upload",
            target=self._upload_thread,
            args=(config, progress_cb),
        )

    def _upload_thread(self, config: UploadConfig, progress_cb) -> None:
        try:
            result = run_upload(
                config,
                progress_callback=progress_cb,
                cancel_event=getattr(self, "_ul_cancel_event", None),
            )
            total = result["success"] + result["skipped"] + len(result["failures"])
            summary = t("msg.upload_complete", success=result["success"], total=total)
            logging.getLogger("dsno_processor.ebs_upload").info(summary)
            self._show_info_async(t("msg.upload_title"), summary)
        except CanceledError:
            logging.getLogger("dsno_processor.ebs_upload").info(
                "Upload was cancelled by the user."
            )
            self._run_on_ui_thread(
                self._mark_dashboard_cancelled,
                self.ul_dashboard,
                t("msg.cancelled_by_user", default="Cancelled by user"),
            )
        except LoginError as exc:
            logging.getLogger("dsno_processor.ebs_upload").error(
                "Login failed: %s", exc
            )
            self._run_on_ui_thread(
                self._finish_dashboard_with_error,
                self.ul_dashboard,
                f"Login Error: {exc}",
            )
            self._show_error_async(t("settings.save_error_title"), str(exc))
        except Exception as exc:
            logging.getLogger("dsno_processor.ebs_upload").error("Error: %s", exc)
            self._run_on_ui_thread(
                self._finish_dashboard_with_error, self.ul_dashboard, f"Error: {exc}"
            )
            self._show_error_async(t("settings.save_error_title"), str(exc))
        finally:
            self._run_on_ui_thread(self._finish_upload_ui)

    # ──────────────────────────────────────────────────────────────
    # Settings
    # ──────────────────────────────────────────────────────────────

    def _open_settings(self) -> None:
        SettingsWindow(self, on_save=self._reload_config)

    def _open_import_wizard(self) -> None:
        """Open the customer sheet → DB import wizard."""
        ImportWizard(self, self._app_config)

    def _open_import_control_wizard(self) -> None:
        """Open the control sheet → DB import wizard."""
        ImportControlWizard(self, self._app_config)

    def _change_language(self) -> None:
        """Show the language selection popup menu."""
        LanguageMenu(self, self._lang_btn, self._set_language_from_menu)

    def _set_language_from_menu(self, lang_code: str) -> None:
        """Callback from LanguageMenu to update application language."""
        if not self._app_config:
            return

        if self._app_config.language == lang_code:
            return

        self._app_config.language = lang_code
        try:
            save_config(self._app_config)
            messagebox.showinfo(
                t("settings.saved_title"), t("settings.general.restart_msg")
            )
        except Exception as e:
            messagebox.showerror(t("settings.save_error_title"), str(e))

    def _reload_config(self) -> None:
        """Reload config from disk and refresh main window defaults."""
        try:
            self._app_config = load_config()
        except ConfigurationError:
            return
        cfg = self._app_config
        self.customer_row.set(str(cfg.customer_sheet))
        self.control_row.set(str(cfg.control_sheet))
        self.dsno_row.set(str(cfg.dsno_directory))
        self._customer_pre_path = str(cfg.customer_sheet_pre_path)
        logging.info("Settings reloaded successfully.")
