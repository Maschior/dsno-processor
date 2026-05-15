"""GUI action handlers that coordinate services and dialogs."""

from __future__ import annotations

import logging
import os
import threading
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image

from core.assets import get_asset_path
from dsno_processor import process_dsno
from dsno_processor.config import load_config, save_config
from dsno_processor.control_reader import get_status_options, read_control_sheet
from dsno_processor.ebs_download import DownloadConfig, run_download
from dsno_processor.ebs_upload import UploadConfig, run_upload
from dsno_processor.exceptions import CanceledError, ConfigurationError, LoginError
from dsno_processor.i18n import t
from gui.dialogs.import_wizards import ImportControlWizard, ImportWizard
from gui.dialogs.language_menu import LanguageMenu
from gui.dialogs.settings_window import SettingsWindow
from gui.themes.appearance import FONT_FAMILY as _FONT_FAMILY
from gui.widgets.dashboard import ProgressDashboard
from gui.widgets.dropdowns import MultiSelectDropdown
from gui.widgets.inputs import DateInput, DateTimeInput, FilePickerRow

log = logging.getLogger(__name__)


class AppActionsMixin:
    """GUI action handlers that coordinate services and dialogs."""

    def _browse_customer(self) -> None:
        initial = (
            self._customer_pre_path
            if os.path.exists(self._customer_pre_path)
            else None
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
        thread = threading.Thread(target=self._process_thread, daemon=True)
        thread.start()

    def _make_progress_callback(self):
        """Create a callback that routes backend events to the processor dashboard."""
        def callback(event, data):
            if event == "phase":
                self.dashboard.set_phase(data["text"])
            elif event == "total":
                self.dashboard.reset(data["count"])
            elif event == "success":
                self.dashboard.mark_success(data["name"], data.get("detail", ""))
            elif event == "error":
                self.dashboard.mark_error(data["name"], data["detail"])
            elif event == "skipped":
                self.dashboard.mark_skipped(data["name"], data.get("detail", ""))
            elif event == "cancelled":
                self.dashboard._cancelled = True
            elif event == "finished":
                self.dashboard.finish()
        return callback

    def _process_thread(self) -> None:
        try:
            date_range = f"{self.start_date.get()};{self.end_date.get()}"
            status_filter = self.filter_by_status.get_selected()  # [] means All
            result = process_dsno(
                date_range=date_range,
                customer_sheet=self.customer_row.get(),
                control_sheet=self.control_row.get(),
                dsno_dir=self.dsno_row.get(),
                freight_mode=self.freight_mode_var.get(),
                progress_callback=self._make_progress_callback(),
                cancel_event=getattr(self, "_processor_cancel_event", None),
                status_filter=status_filter,
            )

            summary = t("msg.processing_complete", success=result.success, total=result.total)
            logging.info(summary)
            if result.failed > 0:
                messagebox.showinfo(t("msg.complete_title"), t("msg.processing_errors", summary=summary, failed=result.failed))
            else:
                messagebox.showinfo(t("dash.success"), summary)
        except CanceledError:
            logging.info("Processing was cancelled by the user.")
            self.dashboard.set_phase(t("msg.cancelled_by_user", default="Cancelled by user"))
            self.dashboard._cancelled = True
            self.dashboard.finish()
        except LoginError as exc:
            logging.error("Login failed: %s", exc)
            self.dashboard.set_phase(f"Login Error: {exc}")
            self.dashboard.finish()
            messagebox.showerror(t("settings.save_error_title"), str(exc))
        except Exception as exc:
            logging.error("Error during processing: %s", exc)
            self.dashboard.set_phase(f"Error: {exc}")
            self.dashboard.finish()
            messagebox.showerror(t("settings.save_error_title"), str(exc))
        finally:
            self._hide_blocking_overlay()
            # If finished, we could optionally show the start button again,
            # but for now we follow the user's "botão sumirá" (it remains hidden while showing final status)
            # We only ensure it's enabled if we were to show it again.
            self._update_run_btn_state()
            self.dashboard.cancel_btn.configure(state="disabled")

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
            folder_indices = [int(x.strip()) for x in self.dl_folders_var.get().split(",") if x.strip()]
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

        def _cb(event, data):
            if event == "phase":     self.dl_dashboard.set_phase(data["text"])
            elif event == "total":   self.dl_dashboard.reset(data["count"])
            elif event == "success": self.dl_dashboard.mark_success(data["name"], data.get("detail", ""))
            elif event == "error":   self.dl_dashboard.mark_error(data["name"], data["detail"])
            elif event == "skipped": self.dl_dashboard.mark_skipped(data["name"], data.get("detail", ""))
            elif event == "cancelled": self.dl_dashboard._cancelled = True
            elif event == "finished":self.dl_dashboard.finish()

        threading.Thread(target=self._download_thread, args=(config, _cb), daemon=True).start()

    def _download_thread(self, config: DownloadConfig, progress_cb) -> None:
        try:
            result = run_download(config, progress_callback=progress_cb, cancel_event=getattr(self, "_dl_cancel_event", None))
            total = result["success"] + result["skipped"] + len(result["failures"])
            summary = t("msg.download_complete", success=result['success'], total=total - result['skipped'])
            logging.getLogger("dsno_processor.ebs_download").info(summary)
            messagebox.showinfo(t("msg.download_title"), summary)
        except CanceledError:
            logging.getLogger("dsno_processor.ebs_download").info("Download was cancelled by the user.")
            self.dl_dashboard.set_phase(t("msg.cancelled_by_user", default="Cancelled by user"))
            self.dl_dashboard._cancelled = True
            self.dl_dashboard.finish()
        except LoginError as exc:
            logging.getLogger("dsno_processor.ebs_download").error("Login failed: %s", exc)
            self.dl_dashboard.set_phase(f"Login Error: {exc}")
            self.dl_dashboard.finish()
            messagebox.showerror(t("settings.save_error_title"), str(exc))
        except Exception as exc:
            logging.getLogger("dsno_processor.ebs_download").error("Error: %s", exc)
            self.dl_dashboard.set_phase(f"Error: {exc}")
            self.dl_dashboard.finish()
            messagebox.showerror(t("settings.save_error_title"), str(exc))
        finally:
            self._hide_blocking_overlay()
            self._update_dl_run_btn_state()
            self.dl_dashboard.cancel_btn.configure(state="disabled")

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

        def _cb(event, data):
            if event == "phase":     self.ul_dashboard.set_phase(data["text"])
            elif event == "total":   self.ul_dashboard.reset(data["count"])
            elif event == "success": self.ul_dashboard.mark_success(data["name"], data.get("detail", ""))
            elif event == "error":   self.ul_dashboard.mark_error(data["name"], data["detail"])
            elif event == "skipped": self.ul_dashboard.mark_skipped(data["name"], data.get("detail", ""))
            elif event == "cancelled": self.ul_dashboard._cancelled = True
            elif event == "finished":self.ul_dashboard.finish()

        threading.Thread(target=self._upload_thread, args=(config, _cb), daemon=True).start()

    def _upload_thread(self, config: UploadConfig, progress_cb) -> None:
        try:
            result = run_upload(config, progress_callback=progress_cb, cancel_event=getattr(self, "_ul_cancel_event", None))
            total = result["success"] + result["skipped"] + len(result["failures"])
            summary = t("msg.upload_complete", success=result['success'], total=total)
            logging.getLogger("dsno_processor.ebs_upload").info(summary)
            messagebox.showinfo(t("msg.upload_title"), summary)
        except CanceledError:
            logging.getLogger("dsno_processor.ebs_upload").info("Upload was cancelled by the user.")
            self.ul_dashboard.set_phase(t("msg.cancelled_by_user", default="Cancelled by user"))
            self.ul_dashboard._cancelled = True
            self.ul_dashboard.finish()
        except LoginError as exc:
            logging.getLogger("dsno_processor.ebs_upload").error("Login failed: %s", exc)
            self.ul_dashboard.set_phase(f"Login Error: {exc}")
            self.ul_dashboard.finish()
            messagebox.showerror(t("settings.save_error_title"), str(exc))
        except Exception as exc:
            logging.getLogger("dsno_processor.ebs_upload").error("Error: %s", exc)
            self.ul_dashboard.set_phase(f"Error: {exc}")
            self.ul_dashboard.finish()
            messagebox.showerror(t("settings.save_error_title"), str(exc))
        finally:
            self._hide_blocking_overlay()
            self._update_ul_run_btn_state()
            self.ul_dashboard.cancel_btn.configure(state="disabled")

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
                t("settings.saved_title"),
                t("settings.general.restart_msg")
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
