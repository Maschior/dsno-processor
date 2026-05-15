"""EBS upload tab construction and state helpers."""

from __future__ import annotations

import logging

import customtkinter as ctk

from dsno_processor.i18n import t
from gui.themes.appearance import FONT_FAMILY as _FONT_FAMILY
from gui.widgets.dashboard import ProgressDashboard

log = logging.getLogger(__name__)


class UploadTabMixin:
    """EBS upload tab construction and state helpers."""

    def _build_tab_upload(self) -> None:
        cfg = self._app_config
        outer = self._tabview.tab(self._TAB_UPLOAD)

        inner_tab = ctk.CTkTabview(
            outer,
            corner_radius=10,
            segmented_button_fg_color=("gray80", "gray20"),
            segmented_button_selected_color=("#e65100", "#bf360c"),
            segmented_button_unselected_hover_color=("gray70", "gray30"),
        )
        inner_tab.pack(fill="both", expand=True)
        inner_tab.add(self._UL_TAB_CONFIG)
        inner_tab.add(self._UL_TAB_PROGRESS)
        self._ul_tabview = inner_tab

        # ── Configuration sub-tab ──────────────────────────────────
        tab = inner_tab.tab(self._UL_TAB_CONFIG)

        form = ctk.CTkFrame(tab, fg_color="transparent")
        form.pack(fill="x", pady=(4, 8))
        form.columnconfigure(1, weight=1)

        row = 0

        def _lbl(text, r):
            ctk.CTkLabel(
                form, text=text, anchor="w", width=150,
                font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
            ).grid(row=r, column=0, padx=(6, 8), pady=5, sticky="w")

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

        def _ent(r, default="", placeholder=""):
            e = ctk.CTkEntry(form, font=ctk.CTkFont(family=_FONT_FAMILY, size=12), placeholder_text=placeholder)
            if default:
                e.insert(0, default)
            e.grid(row=r, column=1, sticky="ew", pady=5, padx=(0, 6))
            var = _WrapperVar(e)
            e.bind("<KeyRelease>", lambda evt: [c() for c in var.cb])
            var.trace_add("write", lambda *_: self._update_ul_run_btn_state())
            return var

        # Connection
        ctk.CTkLabel(form, text=t("dl.section_connection"), anchor="w",
            font=ctk.CTkFont(family=_FONT_FAMILY, size=11, weight="bold"),
            text_color=("gray40", "gray55"),
        ).grid(row=row, column=0, columnspan=3, sticky="w", padx=6, pady=(8, 2))
        row += 1
        _lbl(t("dl.ebs_url"), row)
        self.ul_url_var = _ent(row, cfg.ebs_upload_url if cfg else "")
        row += 1

        # Files
        ctk.CTkLabel(form, text=t("dl.section_files"), anchor="w",
            font=ctk.CTkFont(family=_FONT_FAMILY, size=11, weight="bold"),
            text_color=("gray40", "gray55"),
        ).grid(row=row, column=0, columnspan=3, sticky="w", padx=6, pady=(10, 2))
        row += 1
        _lbl(t("ul.upload_dir"), row)
        self.ul_dir_var = _ent(row, str(cfg.upload_dir) if cfg and str(cfg.upload_dir) != "." else "", placeholder="C:\\...")
        ctk.CTkButton(form, text=t("btn.browse"), width=70,
            command=self._browse_ul_dir,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=11),
        ).grid(row=row, column=2, padx=(4, 6), pady=5)
        row += 1

        # Folders
        ctk.CTkLabel(form, text=t("dl.section_folders"), anchor="w",
            font=ctk.CTkFont(family=_FONT_FAMILY, size=11, weight="bold"),
            text_color=("gray40", "gray55"),
        ).grid(row=row, column=0, columnspan=3, sticky="w", padx=6, pady=(10, 2))
        row += 1
        _lbl(t("ul.folder_index"), row)
        self.ul_folder_var = _ent(row, str(cfg.ebs_upload_folder_index) if cfg else "92")
        row += 1

        # Start button
        self.ul_start_btn = ctk.CTkButton(
            tab,
            text=t("ul.start_btn"),
            height=40, corner_radius=10,
            fg_color=("#e65100", "#bf360c"),
            hover_color=("#f57c00", "#e65100"),
            font=ctk.CTkFont(family=_FONT_FAMILY, size=13, weight="bold"),
            command=self._start_upload,
        )
        self.ul_start_btn.pack(pady=(0, 6))

        # ── Progress sub-tab ─────────────────────────────────────
        prog_tab = inner_tab.tab(self._UL_TAB_PROGRESS)
        
        self.ul_dashboard = ProgressDashboard(
            prog_tab,
            cancel_command=lambda: (self._show_blocking_overlay(), getattr(self,("_ul_cancel_event")).set()) if hasattr(self, "_ul_cancel_event") else None
        )
        self.ul_dashboard.pack(fill="both", expand=True, pady=4)

        # Initial button state
        self._update_ul_run_btn_state()

    def _update_ul_run_btn_state(self) -> None:
        """Enable or disable the Upload Start button based on field completion."""
        if not hasattr(self, "ul_start_btn"):
            return
            
        c1 = self.ul_url_var.get().strip() if hasattr(self, "ul_url_var") else ""
        c2 = self.ul_dir_var.get().strip() if hasattr(self, "ul_dir_var") else ""
        c3 = self.ul_folder_var.get().strip() if hasattr(self, "ul_folder_var") else ""
        
        is_ready = bool(c1 and c2 and c3)

        self.ul_start_btn.configure(
            state="normal" if is_ready else "disabled",
            fg_color=("#e65100", "#bf360c") if is_ready else ("gray70", "gray30"),
        )

    # ──────────────────────────────────────────────────────────────
    # Browse dialogs — Processor
    # ──────────────────────────────────────────────────────────────

