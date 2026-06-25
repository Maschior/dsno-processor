"""EBS download tab construction and state helpers."""

from __future__ import annotations

import logging

import customtkinter as ctk

from dsno_processor.i18n import t
from gui.themes.appearance import FONT_FAMILY as _FONT_FAMILY
from gui.widgets.dashboard import ProgressDashboard
from gui.widgets.inputs import DateTimeInput

log = logging.getLogger(__name__)


class DownloadTabMixin:
    """EBS download tab construction and state helpers."""

    def _build_tab_download(self) -> None:
        cfg = self._app_config
        outer = self._tabview.tab(self._TAB_DOWNLOAD)

        inner_tab = ctk.CTkTabview(
            outer,
            corner_radius=10,
            segmented_button_fg_color=("gray80", "gray20"),
            segmented_button_selected_color=("#2e7d32", "#1b5e20"),
            segmented_button_unselected_hover_color=("gray70", "gray30"),
        )
        inner_tab.pack(fill="both", expand=True)
        inner_tab.add(self._DL_TAB_CONFIG)
        inner_tab.add(self._DL_TAB_PROGRESS)
        self._dl_tabview = inner_tab

        # ── Configuration sub-tab ──────────────────────────────────
        tab = inner_tab.tab(self._DL_TAB_CONFIG)

        form = ctk.CTkScrollableFrame(tab, corner_radius=8, fg_color="transparent")
        form.pack(fill="both", expand=True, pady=(4, 8))
        form.columnconfigure(1, weight=1)

        row = 0

        def _lbl(text, r):
            ctk.CTkLabel(
                form,
                text=text,
                anchor="w",
                width=150,
                font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
            ).grid(row=r, column=0, padx=(6, 8), pady=4, sticky="w")

        class _WrapperVar:
            def __init__(self, e):
                self.e = e
                self.cb = []

            def get(self):
                return self.e.get()

            def set(self, val):
                self.e.delete(0, "end")
                self.e.insert(0, val)
                for c in self.cb:
                    c()

            def trace_add(self, mode, callback):
                self.cb.append(callback)

        def _ent(r, default="", width=None, placeholder=""):
            e = ctk.CTkEntry(
                form,
                font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
                placeholder_text=placeholder,
            )
            if width:
                e.configure(width=width)
            if default:
                e.insert(0, default)
            e.grid(row=r, column=1, sticky="ew", pady=4, padx=(0, 6))
            var = _WrapperVar(e)
            e.bind("<KeyRelease>", lambda evt: [c() for c in var.cb])
            var.trace_add("write", lambda *_: self._update_dl_run_btn_state())
            return var, e

        # Period
        ctk.CTkLabel(
            form,
            text=t("dl.section_period"),
            anchor="w",
            font=ctk.CTkFont(family=_FONT_FAMILY, size=11, weight="bold"),
            text_color=("gray40", "gray55"),
        ).grid(row=row, column=0, columnspan=3, sticky="w", padx=6, pady=(8, 2))
        row += 1
        _lbl(t("dl.start_date"), row)
        self.dl_date_start = DateTimeInput(form)
        self.dl_date_start.grid(
            row=row, column=1, columnspan=2, sticky="w", pady=4, padx=(0, 6)
        )
        self.dl_date_start.entry.bind(
            "<KeyRelease>", lambda e: self._update_dl_run_btn_state(), add="+"
        )
        orig_set_start = self.dl_date_start._set_datetime
        self.dl_date_start._set_datetime = lambda *a, **k: (
            orig_set_start(*a, **k),
            self._update_dl_run_btn_state(),
        )
        row += 1
        _lbl(t("dl.end_date"), row)
        self.dl_date_end = DateTimeInput(form)
        self.dl_date_end.grid(
            row=row, column=1, columnspan=2, sticky="w", pady=4, padx=(0, 6)
        )
        self.dl_date_end.entry.bind(
            "<KeyRelease>", lambda e: self._update_dl_run_btn_state(), add="+"
        )
        orig_set_end = self.dl_date_end._set_datetime
        self.dl_date_end._set_datetime = lambda *a, **k: (
            orig_set_end(*a, **k),
            self._update_dl_run_btn_state(),
        )
        row += 1
        _lbl(t("dl.status_filter"), row)
        self.dl_status_filter_var, _e = _ent(
            row, "", placeholder="Processed, Downloaded, <empty>"
        )
        row += 1

        # Files
        ctk.CTkLabel(
            form,
            text=t("dl.section_files"),
            anchor="w",
            font=ctk.CTkFont(family=_FONT_FAMILY, size=11, weight="bold"),
            text_color=("gray40", "gray55"),
        ).grid(row=row, column=0, columnspan=3, sticky="w", padx=6, pady=(10, 2))
        row += 1
        _lbl(t("dl.ebs.download_dir"), row)
        self.dl_dir_var, _ = _ent(
            row,
            str(cfg.ebs.download_dir) if cfg and str(cfg.ebs.download_dir) != "." else "",
            placeholder="C:\\...",
        )
        ctk.CTkButton(
            form,
            text=t("btn.browse"),
            width=70,
            command=self._browse_dl_dir,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=11),
        ).grid(row=row, column=2, padx=(4, 6), pady=4)
        row += 1
        _lbl(t("proc.paths.control_sheet"), row)
        self.dl_sheet_var, _ = _ent(
            row,
            str(cfg.paths.control_sheet) if cfg and str(cfg.paths.control_sheet) != "." else "",
            placeholder="C:\\...",
        )
        ctk.CTkButton(
            form,
            text=t("btn.browse"),
            width=70,
            command=self._browse_dl_sheet,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=11),
        ).grid(row=row, column=2, padx=(4, 6), pady=4)
        row += 1

        # Connection
        ctk.CTkLabel(
            form,
            text=t("dl.section_connection"),
            anchor="w",
            font=ctk.CTkFont(family=_FONT_FAMILY, size=11, weight="bold"),
            text_color=("gray40", "gray55"),
        ).grid(row=row, column=0, columnspan=3, sticky="w", padx=6, pady=(10, 2))
        row += 1
        _lbl(t("dl.ebs_url"), row)
        self.dl_url_var, _ = _ent(row, cfg.ebs.download_url if cfg else "")
        row += 1

        # Columns
        ctk.CTkLabel(
            form,
            text=t("dl.section_columns"),
            anchor="w",
            font=ctk.CTkFont(family=_FONT_FAMILY, size=11, weight="bold"),
            text_color=("gray40", "gray55"),
        ).grid(row=row, column=0, columnspan=3, sticky="w", padx=6, pady=(10, 2))
        row += 1
        _lbl(t("dl.dsno_column"), row)
        self.dl_dsno_col_var, _ = _ent(row, cfg.control_sheet_cols.dsno if cfg else "ARGUMENT2")
        row += 1
        _lbl(t("dl.date_column"), row)
        self.dl_date_col_var, _ = _ent(
            row, cfg.control_sheet_cols.date if cfg else "CREATION_DATE"
        )
        row += 1
        _lbl(t("dl.status_column"), row)
        self.dl_status_col_var, _ = _ent(row, cfg.control_sheet_cols.status if cfg else "STATUS")
        row += 1

        # Folders
        ctk.CTkLabel(
            form,
            text=t("dl.section_folders"),
            anchor="w",
            font=ctk.CTkFont(family=_FONT_FAMILY, size=11, weight="bold"),
            text_color=("gray40", "gray55"),
        ).grid(row=row, column=0, columnspan=3, sticky="w", padx=6, pady=(10, 2))
        row += 1
        indices_str = ",".join(
            str(x) for x in (cfg.ebs.folders.download_indices if cfg else [92, 95, 101])
        )
        _lbl(t("dl.folder_indices"), row)
        self.dl_folders_var, _ = _ent(row, indices_str)
        row += 1

        # Start button
        self.dl_start_btn = ctk.CTkButton(
            tab,
            text=t("dl.start_btn"),
            height=40,
            corner_radius=10,
            fg_color=("#2e7d32", "#1b5e20"),
            hover_color=("#388e3c", "#2e7d32"),
            font=ctk.CTkFont(family=_FONT_FAMILY, size=13, weight="bold"),
            command=self._start_download,
        )
        self.dl_start_btn.pack(pady=(0, 6))

        # ── Progress sub-tab ─────────────────────────────────────
        prog_tab = inner_tab.tab(self._DL_TAB_PROGRESS)

        self.dl_dashboard = ProgressDashboard(
            prog_tab,
            cancel_command=lambda: (
                (
                    self._show_blocking_overlay(),
                    getattr(self, ("_dl_cancel_event")).set(),
                )
                if hasattr(self, "_dl_cancel_event")
                else None
            ),
        )
        self.dl_dashboard.pack(fill="both", expand=True, pady=4)

        # Initial button state
        self._update_dl_run_btn_state()

    def _update_dl_run_btn_state(self) -> None:
        """Enable or disable the Download Start button based on field completion."""
        if not hasattr(self, "dl_start_btn"):
            return

        c1 = self.dl_date_start.get().strip() if hasattr(self, "dl_date_start") else ""
        c2 = self.dl_date_end.get().strip() if hasattr(self, "dl_date_end") else ""
        c3 = self.dl_dir_var.get().strip() if hasattr(self, "dl_dir_var") else ""
        c4 = self.dl_url_var.get().strip() if hasattr(self, "dl_url_var") else ""
        c5 = self.dl_sheet_var.get().strip() if hasattr(self, "dl_sheet_var") else ""

        is_ready = bool(c1 and c2 and c3 and c4 and c5)

        self.dl_start_btn.configure(
            state="normal" if is_ready else "disabled",
            fg_color=("#2e7d32", "#1b5e20") if is_ready else ("gray70", "gray30"),
        )

    # ──────────────────────────────────────────────────────────────
    # Tab: EBS Upload
    # ──────────────────────────────────────────────────────────────

    _UL_TAB_CONFIG = t("tab.configuration")
    _UL_TAB_PROGRESS = t("tab.progress")
