"""Processor processing tab construction and state helpers."""

from __future__ import annotations

import getpass
import logging

import customtkinter as ctk
from PIL import Image

from core.assets import get_asset_path
from dsno_processor.config import load_config
from dsno_processor.control_reader import get_status_options, read_control_sheet
from dsno_processor.i18n import t
from gui.themes.appearance import FONT_FAMILY as _FONT_FAMILY
from gui.widgets.dashboard import ProgressDashboard
from gui.widgets.dropdowns import MultiSelectDropdown
from gui.widgets.inputs import DateInput, FilePickerRow

log = logging.getLogger(__name__)


class ProcessorTabMixin:
    """Processor processing tab construction and state helpers."""

    def _build_tab_processor(
        self,
        default_customer: str,
        default_control: str,
        default_dsno_dir: str,
    ) -> None:
        tab = self._tabview.tab(self._TAB_PROC)

        # Date range
        date_frame = ctk.CTkFrame(tab, fg_color="transparent")
        date_frame.pack(fill="x", pady=(8, 4))
        ctk.CTkLabel(
            date_frame,
            text=t("proc.date_range"),
            font=ctk.CTkFont(family=_FONT_FAMILY, size=13),
            width=130,
            anchor="w",
        ).pack(side="left")
        self.start_date = DateInput(
            date_frame, label=t("proc.start"), prefill_today=True
        )
        self.start_date.pack(side="left", padx=(0, 20))
        self.end_date = DateInput(date_frame, label=t("proc.end"), prefill_today=True)
        self.end_date.pack(side="left", padx=(0, 20))

        # Status filter (inline with date range) — multi-select
        ctk.CTkLabel(
            date_frame,
            text=t("proc.status"),
            font=ctk.CTkFont(family=_FONT_FAMILY, size=13),
            anchor="w",
        ).pack(side="left", padx=(0, 6))
        try:
            cfg = load_config()
            if getattr(cfg.general, "data_source", "spreadsheet") == "database":
                from dsno_processor.database import (
                    get_db_path,
                    get_connection,
                    get_status_options as db_get_status_options,
                )

                conn = get_connection(get_db_path())
                status_options = db_get_status_options(conn)
                conn.close()
            else:
                sheet_df = read_control_sheet(default_control)
                status_options = get_status_options(sheet_df)
        except Exception:
            status_options = []

        self.filter_by_status = MultiSelectDropdown(
            date_frame,
            options=status_options,
            placeholder="All",
        )
        self.filter_by_status.pack(side="left")

        # Freight mode selector
        ctk.CTkLabel(
            date_frame,
            text=t("proc.freight_mode"),
            font=ctk.CTkFont(family=_FONT_FAMILY, size=13),
            anchor="w",
        ).pack(side="left", padx=(16, 6))
        self.freight_mode_var = ctk.StringVar(value=t("proc.sea"))
        self.freight_mode_combo = ctk.CTkComboBox(
            date_frame,
            values=[t("proc.sea"), t("proc.air")],
            variable=self.freight_mode_var,
            width=100,
            state="readonly",
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
        )
        self.freight_mode_combo.pack(side="left")

        # File pickers
        self.customer_row = FilePickerRow(
            tab,
            label=t("proc.customer_sheet"),
            default=default_customer,
            placeholder="Z:\\Documentação\\ORACLE\\EDI\\ASN NAVSTAR\\17-04-2026\\International Motors Shipment track 15.04.2026.xlsx",
            browse_command=self._browse_customer,
            on_change=self._update_run_btn_state,
        )
        self.customer_row.pack(fill="x", pady=4)

        self.control_row = FilePickerRow(
            tab,
            label=t("proc.control_sheet"),
            default=default_control,
            placeholder=t("settings.paths.control_sheet_hint"),
            browse_command=self._browse_control,
            on_change=self._update_run_btn_state,
        )
        self.control_row.pack(fill="x", pady=4)

        self.dsno_row = FilePickerRow(
            tab,
            label=t("proc.dsno_directory"),
            default=default_dsno_dir,
            placeholder=f"C:\\Users\\{getpass.getuser()}\\edi-process",
            browse_command=self._browse_dsno_dir,
            on_change=self._update_run_btn_state,
        )
        self.dsno_row.pack(fill="x", pady=4)

        # Import customer sheet to DB button
        import_frame = ctk.CTkFrame(tab, fg_color="transparent")
        import_frame.pack(fill="x", pady=(4, 0))
        try:
            db_icon = ctk.CTkImage(
                light_image=Image.open(get_asset_path("assets/icons/save_light.png")),
                dark_image=Image.open(get_asset_path("assets/icons/save_dark.png")),
                size=(14, 14),
            )
        except Exception:
            db_icon = None
        ctk.CTkButton(
            import_frame,
            text=t("import.btn_label"),
            image=db_icon,
            height=28,
            corner_radius=8,
            fg_color=("gray75", "gray25"),
            hover_color=("gray65", "gray35"),
            font=ctk.CTkFont(family=_FONT_FAMILY, size=11),
            command=self._open_import_wizard,
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            import_frame,
            text=t("import_control.btn_label"),
            image=db_icon,
            height=28,
            corner_radius=8,
            fg_color=("gray75", "gray25"),
            hover_color=("gray65", "gray35"),
            font=ctk.CTkFont(family=_FONT_FAMILY, size=11),
            command=self._open_import_control_wizard,
        ).pack(side="right")

        # Progress dashboard with integrated Start button
        self.dashboard = ProgressDashboard(
            tab,
            cancel_command=lambda: (
                (
                    self._show_blocking_overlay(),
                    getattr(self, "_processor_cancel_event").set(),
                )
                if hasattr(self, "_processor_cancel_event")
                else None
            ),
            enable_idle_hourglass=False,
            start_btn_text=t("proc.start_btn"),
            start_btn_command=self._start_processing,
        )
        self.dashboard.pack(fill="both", expand=True, pady=(10, 0))
        self.run_btn = self.dashboard.start_btn  # Alias for existing logic

        # Initial button state
        self._update_run_btn_state()

    def _update_run_btn_state(self) -> None:
        """Enable or disable the Start button based on field completion."""
        if not hasattr(self, "run_btn"):
            return

        c1 = self.customer_row.get().strip()
        c2 = self.control_row.get().strip()
        c3 = self.dsno_row.get().strip()

        is_ready = bool(c1 and c2 and c3)

        if not self.run_btn:
            log.warning("Run button not found when updating state")
            return

        self.run_btn.configure(
            state="normal" if is_ready else "disabled",
            fg_color=("#1f6aa5", "#1f6aa5") if is_ready else ("gray70", "gray30"),
        )

    # ─────────────────────────────────────────────────────── ───────
    # Tab: EBS Download
    # ──────────────────────────────────────────────────────────────

    _DL_TAB_CONFIG = t("tab.configuration")
    _DL_TAB_PROGRESS = t("tab.progress")
