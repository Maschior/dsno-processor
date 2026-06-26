"""Settings editor dialog."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image

from gui.assets import get_asset_path

from dsno_processor.config import (
    AppConfig,
    ControlSheetColsConfig,
    CredentialsConfig,
    CustomerSheetColsConfig,
    CustomerSheetPropertiesConfig,
    EbsConfig,
    EbsFoldersConfig,
    GeneralConfig,
    PathsConfig,
    ProcessorConfig,
    load_config,
    save_config,
)
from dsno_processor.i18n import SUPPORTED_LANGUAGES, t
from gui.themes.appearance import FONT_FAMILY as _FONT_FAMILY


class SettingsWindow(ctk.CTkToplevel):
    """Window to view and edit the persistent config.toml settings.

    Uses a tabbed layout so each config domain (Paths, Processor, EBS,
    Columns, Folders, Credentials) gets its own focused view.
    """

    def __init__(self, master, on_save=None) -> None:
        super().__init__(master)

        self._TAB_NAMES = [
            t("settings.tab.general"),
            t("settings.tab.paths"),
            t("settings.tab.processor"),
            t("settings.tab.ebs"),
            t("dl.section_columns"),
            t("dl.section_folders"),
            t("settings.tab.credentials"),
        ]

        self.title(t("btn.settings"))
        self.geometry("800x620")
        self.minsize(700, 520)
        self._on_save = on_save

        # Load current config
        try:
            self._cfg = load_config()
        except Exception:
            self._cfg = None

        self._vars: dict[str, tk.StringVar] = {}
        self._path_indicators: dict[str, ctk.CTkLabel] = {}
        self._build_ui()
        self.after(50, self._bring_to_front)

    # ──────────────────────────────────────────────────────────────
    # UI Construction
    # ──────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        pad = 14
        cfg = self._cfg

        # ── Header ────────────────────────────────────────────────
        header = ctk.CTkFrame(self, corner_radius=12)
        header.pack(fill="x", padx=pad, pady=(pad, 8))
        ctk.CTkLabel(
            header,
            text=t("settings.header"),
            font=ctk.CTkFont(family=_FONT_FAMILY, size=20, weight="bold"),
        ).pack(pady=(12, 2))
        ctk.CTkLabel(
            header,
            text=t("settings.subtitle"),
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
            text_color="gray60",
        ).pack(pady=(0, 12))

        # ── Tabview ───────────────────────────────────────────────
        self._tabview = ctk.CTkTabview(
            self,
            corner_radius=10,
            segmented_button_fg_color=("gray80", "gray20"),
            segmented_button_selected_color=("#1f6aa5", "#1f6aa5"),
            segmented_button_unselected_hover_color=("gray70", "gray30"),
        )
        self._tabview.pack(fill="both", expand=True, padx=pad, pady=4)

        for name in self._TAB_NAMES:
            self._tabview.add(name)

        self._build_tab_general(cfg)
        self._build_tab_paths(cfg)
        self._build_tab_processor(cfg)
        self._build_tab_ebs(cfg)
        self._build_tab_columns(cfg)
        self._build_tab_folders(cfg)
        self._build_tab_credentials(cfg)

        # ── Buttons ───────────────────────────────────────────────
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=pad, pady=(8, pad))

        ctk.CTkButton(
            btn_frame,
            image=ctk.CTkImage(
                light_image=Image.open(get_asset_path("assets/icons/cancel_light.png")),
                dark_image=Image.open(get_asset_path("assets/icons/cancel_dark.png")),
            ),
            text=t("btn.cancel"),
            height=38,
            corner_radius=10,
            fg_color=("gray70", "gray30"),
            hover_color=("gray60", "gray40"),
            font=ctk.CTkFont(family=_FONT_FAMILY, size=13),
            command=self.destroy,
        ).pack(side="left", expand=True, fill="x", padx=(0, 4))

        ctk.CTkButton(
            btn_frame,
            image=ctk.CTkImage(
                light_image=Image.open(get_asset_path("assets/icons/save_light.png")),
                dark_image=Image.open(get_asset_path("assets/icons/save_dark.png")),
            ),
            text=t("btn.save"),
            height=38,
            corner_radius=10,
            fg_color=("#2e7d32", "#1b5e20"),
            hover_color=("#388e3c", "#2e7d32"),
            font=ctk.CTkFont(family=_FONT_FAMILY, size=13, weight="bold"),
            command=self._save,
        ).pack(side="left", expand=True, fill="x", padx=(4, 0))

    # ──────────────────────────────────────────────────────────────
    # Tab builders
    # ──────────────────────────────────────────────────────────────

    def _bring_to_front(self) -> None:
        """Ensure this toplevel window is visible above the main window."""
        self.lift()
        self.attributes("-topmost", True)
        self.focus_force()
        self.after(50, lambda: self.attributes("-topmost", False))

    def _build_tab_general(self, cfg) -> None:
        tab = self._tabview.tab(t("settings.tab.general"))
        form = self._make_form(tab)

        self._tab_hint(form, t("settings.general.hint"))

        row = 1
        ctk.CTkLabel(
            form,
            text=t("settings.general.language"),
            anchor="w",
            width=150,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
        ).grid(row=row, column=0, padx=(0, 8), pady=3, sticky="w")

        # Map language internal codes to display names
        lang_options = list(SUPPORTED_LANGUAGES.values())
        current_lang_code = cfg.general.language if cfg else "en"
        current_lang_display = SUPPORTED_LANGUAGES.get(current_lang_code, "English")

        self.language_var = tk.StringVar(value=current_lang_display)
        ctk.CTkComboBox(
            form,
            values=lang_options,
            variable=self.language_var,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
        ).grid(row=row, column=1, sticky="w", pady=3)

        self._hint_label(
            form,
            t("settings.general.language_hint"),
            row + 1,
        )

        row += 2
        ctk.CTkLabel(
            form,
            text=t("settings.general.data_source"),
            anchor="w",
            width=150,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
        ).grid(row=row, column=0, padx=(0, 8), pady=3, sticky="w")

        data_source_options = [
            t("settings.data_source.spreadsheet"),
            t("settings.data_source.database"),
        ]
        current_data_source = cfg.general.data_source if cfg else "spreadsheet"
        current_data_source_display = t(f"settings.data_source.{current_data_source}")

        self.data_source_var = tk.StringVar(value=current_data_source_display)
        ctk.CTkComboBox(
            form,
            values=data_source_options,
            variable=self.data_source_var,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
        ).grid(row=row, column=1, sticky="w", pady=3)

        self._hint_label(
            form,
            t("settings.general.data_source_hint"),
            row + 1,
        )

    def _build_tab_paths(self, cfg) -> None:
        tab = self._tabview.tab(t("settings.tab.paths"))
        form = self._make_form(tab)

        self._tab_hint(form, t("settings.paths.hint"))

        self._add_path_field(
            form,
            1,
            t("proc.dsno_directory"),
            "dsno_directory",
            str(cfg.paths.dsno_directory) if cfg else "",
            mode="dir",
            hint=t("settings.paths.dsno_directory_hint"),
        )
        self._add_path_field(
            form,
            3,
            t("proc.control_sheet"),
            "control_sheet",
            str(cfg.paths.control_sheet) if cfg else "",
            mode="file",
            filetypes=[("Excel", "*.xlsx *.xls")],
            hint=t("settings.paths.control_sheet_hint"),
        )
        self._add_path_field(
            form,
            5,
            t("proc.customer_sheet"),
            "customer_sheet",
            str(cfg.paths.customer_sheet) if cfg else "",
            mode="file",
            filetypes=[("Excel", "*.xlsx *.xls")],
            hint=t("settings.paths.customer_sheet_hint"),
        )
        self._add_path_field(
            form,
            7,
            t("settings.paths.customer_pre_path"),
            "customer_sheet_pre_path",
            str(cfg.paths.customer_sheet_pre_path) if cfg else "",
            mode="dir",
            hint=t("settings.paths.customer_pre_path_hint"),
        )
        self._add_path_field(
            form,
            9,
            t("settings.paths.database_dir"),
            "database_dir",
            str(cfg.paths.database_dir) if cfg else "",
            mode="dir",
            hint=t("settings.paths.database_dir_hint"),
        )

    def _build_tab_processor(self, cfg) -> None:
        tab = self._tabview.tab(t("settings.tab.processor"))
        form = self._make_form(tab)

        self._tab_hint(form, t("settings.processor.hint"))

        # Bypass file size verification toggle
        row = 1
        self._hint_label(
            form,
            t("settings.processor.bypass_file_size_check_hint"),
            row,
        )
        row += 1

        ctk.CTkLabel(
            form,
            text=t("settings.processor.bypass_file_size_check"),
            anchor="w",
            width=240,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
        ).grid(row=row, column=0, padx=(0, 8), pady=3, sticky="w")

        self._bypass_size_check_var = tk.BooleanVar(
            value=bool(getattr(cfg, "processor", None).bypass_file_size_check)
            if cfg
            else False
        )
        ctk.CTkSwitch(
            form,
            text="",
            variable=self._bypass_size_check_var,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
            onvalue=True,
            offvalue=False,
        ).grid(row=row, column=1, sticky="w", pady=3, columnspan=2)

        # Keep original toggle
        row += 1
        self._hint_label(
            form,
            t("settings.processor.keep_original_hint"),
            row,
        )
        row += 1

        ctk.CTkLabel(
            form,
            text=t("settings.processor.keep_original"),
            anchor="w",
            width=240,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
        ).grid(row=row, column=0, padx=(0, 8), pady=3, sticky="w")

        self._keep_original_var = tk.BooleanVar(
            value=bool(getattr(cfg, "processor", None).keep_original)
            if cfg
            else False
        )
        ctk.CTkSwitch(
            form,
            text="",
            variable=self._keep_original_var,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
            onvalue=True,
            offvalue=False,
        ).grid(row=row, column=1, sticky="w", pady=3, columnspan=2)

    def _build_tab_ebs(self, cfg) -> None:
        tab = self._tabview.tab(t("settings.tab.ebs"))
        form = self._make_form(tab)

        self._tab_hint(form, t("settings.ebs.hint"))

        self._add_text_field(
            form,
            1,
            t("settings.ebs.download_url"),
            "ebs_download_url",
            cfg.ebs.download_url if cfg else "",
            hint=t("settings.ebs.download_url_hint"),
        )
        self._add_text_field(
            form,
            3,
            t("settings.ebs.upload_url"),
            "ebs_upload_url",
            cfg.ebs.upload_url if cfg else "",
            hint=t("settings.ebs.upload_url_hint"),
        )
        self._add_path_field(
            form,
            5,
            t("dl.download_dir"),
            "download_dir",
            str(cfg.ebs.download_dir) if cfg else "",
            mode="dir",
            hint=t("settings.ebs.download_dir_hint"),
        )
        self._add_path_field(
            form,
            7,
            t("ul.upload_dir"),
            "upload_dir",
            str(cfg.ebs.upload_dir) if cfg else "",
            mode="dir",
            hint=t("settings.ebs.upload_dir_hint"),
        )

        # Headless mode toggle
        row = 9
        self._hint_label(
            form,
            t("settings.ebs.headless_hint"),
            row,
        )
        row += 1

        ctk.CTkLabel(
            form,
            text=t("settings.ebs.headless"),
            anchor="w",
            width=150,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
        ).grid(row=row, column=0, padx=(0, 8), pady=3, sticky="w")

        self._headless_var = tk.BooleanVar(value=cfg.ebs.headless if cfg else False)
        ctk.CTkSwitch(
            form,
            text=t("settings.ebs.headless_switch"),
            variable=self._headless_var,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
            onvalue=True,
            offvalue=False,
        ).grid(row=row, column=1, sticky="w", pady=3, columnspan=2)

    def _build_tab_columns(self, cfg) -> None:
        tab = self._tabview.tab(t("dl.section_columns"))
        form = self._make_form(tab)
        row = 0

        ctk.CTkLabel(
            form,
            text=t("settings.columns.control_columns_section"),
            font=ctk.CTkFont(family=_FONT_FAMILY, size=13, weight="bold"),
            text_color=("#1f6aa5", "#3a9ad9"),
        ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(15, 5))
        row += 1

        row = self._add_text_field(
            form,
            row,
            t("dl.invoice_column"),
            "ebs_col_invoice",
            (cfg.control_sheet_cols.invoice if cfg else "INVOICE"),
            hint=t("settings.columns.invoice_hint"),
        )
        row = self._add_text_field(
            form,
            row,
            t("dl.dsno_column"),
            "ebs_col_dsno",
            (cfg.control_sheet_cols.dsno if cfg else "ARGUMENT2"),
            hint=t("settings.columns.dsno_hint"),
        )
        row = self._add_text_field(
            form,
            row,
            t("dl.date_column"),
            "ebs_col_date",
            (cfg.control_sheet_cols.date if cfg else "CREATION_DATE"),
            hint=t("settings.columns.date_hint"),
        )
        row = self._add_text_field(
            form,
            row,
            t("dl.status_column"),
            "ebs_col_status",
            (cfg.control_sheet_cols.status if cfg else "STATUS"),
            hint=t("settings.columns.status_hint"),
        )
        row = self._add_text_field(
            form,
            row,
            t("dl.description_column"),
            "ebs_col_description",
            (cfg.control_sheet_cols.description if cfg else "Obs"),
            hint=t("settings.columns.description_hint"),
        )

        # ── Customer Sheet Section ─────────────────────────────────
        ctk.CTkLabel(
            form,
            text=t("settings.columns.customer_columns_section"),
            font=ctk.CTkFont(family=_FONT_FAMILY, size=13, weight="bold"),
            text_color=("#1f6aa5", "#3a9ad9"),
        ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(15, 5))
        row += 1

        row = self._add_text_field(
            form,
            row,
            t("settings.columns.cust_invoice"),
            "cust_col_invoice",
            (cfg.customer_sheet_cols.invoice if cfg else "Invoice"),
        )
        row = self._add_text_field(
            form,
            row,
            t("settings.columns.cust_booking"),
            "cust_col_booking",
            (cfg.customer_sheet_cols.booking if cfg else "Booking/HAWB"),
        )
        row = self._add_text_field(
            form,
            row,
            t("settings.columns.cust_container"),
            "cust_col_container",
            (cfg.customer_sheet_cols.container if cfg else "Container"),
        )

        ctk.CTkLabel(
            form,
            text=t("settings.columns.customer_config_section"),
            font=ctk.CTkFont(family=_FONT_FAMILY, size=13, weight="bold"),
            text_color=("#1f6aa5", "#3a9ad9"),
        ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(15, 5))
        row += 1
        row = self._add_text_field(
            form,
            row,
            t("settings.columns.cust_sheet_name", default="Sheet Name"),
            "cust_sheet_name",
            (cfg.customer_sheet_properties.sheet_name if cfg else ""),
            hint=t(
                "settings.columns.cust_sheet_name_hint",
                default="Leave empty to use the first sheet",
            ),
        )

    def _build_tab_folders(self, cfg) -> None:
        tab = self._tabview.tab(t("dl.section_folders"))
        form = self._make_form(tab)

        self._tab_hint(
            form,
            t("settings.folders.hint"),
        )

        indices = (
            ", ".join(str(x) for x in cfg.ebs.folders.download_indices)
            if cfg
            else "92, 95, 101"
        )
        self._add_text_field(
            form,
            1,
            t("settings.folders.download_indices"),
            "ebs_folders_download",
            indices,
            hint=t("settings.folders.download_indices_hint"),
        )
        self._add_text_field(
            form,
            3,
            t("settings.folders.upload_index"),
            "ebs_folder_upload",
            str(cfg.ebs.folders.upload_index) if cfg else "92",
            hint=t("settings.folders.upload_index_hint"),
        )

    def _build_tab_credentials(self, cfg) -> None:
        tab = self._tabview.tab(t("settings.tab.credentials"))
        form = self._make_form(tab)

        self._tab_hint(
            form,
            t("settings.credentials.hint"),
        )

        self._add_text_field(
            form,
            1,
            t("settings.credentials.email"),
            "cred_email",
            cfg.credentials.email if cfg else "",
            hint=t("settings.credentials.email_hint"),
        )

        # Password with toggle
        row = 3
        self._hint_label(form, t("settings.credentials.password_hint"), row)
        row += 1

        ctk.CTkLabel(
            form,
            text=t("settings.credentials.password"),
            anchor="w",
            width=150,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
        ).grid(row=row, column=0, padx=(0, 8), pady=3, sticky="w")

        var = tk.StringVar(value=cfg.credentials.password if cfg else "")
        self._password_entry = ctk.CTkEntry(
            form,
            textvariable=var,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
            show="•",
        )
        self._password_entry.grid(row=row, column=1, sticky="ew", pady=3)

        self._password_visible = False
        self._toggle_btn = ctk.CTkButton(
            form,
            text="👁",
            width=36,
            height=28,
            corner_radius=6,
            fg_color="transparent",
            hover_color=("gray75", "gray30"),
            font=ctk.CTkFont(size=14),
            command=self._toggle_password,
        )
        self._toggle_btn.grid(row=row, column=2, padx=(4, 0), pady=3)

        self._vars["cred_password"] = var

    # ──────────────────────────────────────────────────────────────
    # Widget helpers
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def _make_form(tab) -> ctk.CTkFrame:
        """Create a scrollable form container inside a tab."""
        form = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=4, pady=4)
        form.columnconfigure(1, weight=1)
        return form

    @staticmethod
    def _tab_hint(form, text: str) -> None:
        """Add a descriptive hint at the top of a tab form."""
        ctk.CTkLabel(
            form,
            text=text,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=11),
            text_color="gray55",
            anchor="w",
        ).grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 10))

    @staticmethod
    def _hint_label(form, text: str, row: int) -> None:
        """Add a small hint label above a field."""
        ctk.CTkLabel(
            form,
            text=text,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=10),
            text_color="gray50",
            anchor="w",
        ).grid(row=row, column=0, columnspan=3, sticky="ew", pady=(8, 0))

    def _add_text_field(
        self,
        parent,
        row: int,
        label: str,
        key: str,
        default: str = "",
        show: str | None = None,
        hint: str | None = None,
    ) -> int:
        if hint:
            self._hint_label(parent, hint, row)
            row += 1

        ctk.CTkLabel(
            parent,
            text=label,
            anchor="w",
            width=150,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
        ).grid(row=row, column=0, padx=(0, 8), pady=3, sticky="w")

        var = tk.StringVar(value=default)
        entry_kwargs = {
            "textvariable": var,
            "font": ctk.CTkFont(family=_FONT_FAMILY, size=12),
        }
        if show:
            entry_kwargs["show"] = show
        ctk.CTkEntry(parent, **entry_kwargs).grid(
            row=row,
            column=1,
            sticky="ew",
            pady=3,
            columnspan=2,
        )

        self._vars[key] = var
        return row + 1

    def _add_path_field(
        self,
        parent,
        row: int,
        label: str,
        key: str,
        default: str = "",
        mode: str = "dir",
        filetypes=None,
        hint: str | None = None,
    ) -> int:
        if hint:
            self._hint_label(parent, hint, row)
            row += 1

        ctk.CTkLabel(
            parent,
            text=label,
            anchor="w",
            width=150,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
        ).grid(row=row, column=0, padx=(0, 8), pady=3, sticky="w")

        var = tk.StringVar(value=default)
        ctk.CTkEntry(
            parent,
            textvariable=var,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
        ).grid(row=row, column=1, sticky="ew", pady=3)

        # If default is '.', clear it so it doesn't block placeholders (if any)
        if default == ".":
            var.set("")

        # Path validity indicator + browse button frame
        btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        btn_frame.grid(row=row, column=2, padx=(4, 0), pady=3)

        # Validity indicator
        indicator = ctk.CTkLabel(
            btn_frame,
            text="",
            width=20,
            font=ctk.CTkFont(size=13),
        )
        indicator.pack(side="left", padx=(0, 2))
        self._path_indicators[key] = indicator

        def _browse():
            if mode == "dir":
                result = filedialog.askdirectory(title=f"Select {label.rstrip(':')}")
            else:
                result = filedialog.askopenfilename(
                    title=f"Select {label.rstrip(':')}",
                    filetypes=filetypes or [],
                )
            if result:
                var.set(result)
                self._update_indicator(key, result, mode)

        ctk.CTkButton(
            btn_frame,
            text=t("btn.browse"),
            width=70,
            command=_browse,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=11),
        ).pack(side="left")

        self._vars[key] = var

        # Set initial indicator
        self._update_indicator(key, default, mode)

        return row + 1

    def _update_indicator(self, key: str, value: str, mode: str) -> None:
        """Update the validity indicator for a path field."""
        indicator = self._path_indicators.get(key)
        if not indicator:
            return
        if not value or value == ".":
            indicator.configure(text="")
            return
        from pathlib import Path as _P

        path = _P(value)
        if mode == "dir":
            exists = path.is_dir()
        else:
            exists = path.is_file()
        indicator.configure(
            text="✅" if exists else "❌",
        )

    def _toggle_password(self) -> None:
        """Toggle password field visibility."""
        self._password_visible = not self._password_visible
        if self._password_visible:
            self._password_entry.configure(show="")
            self._toggle_btn.configure(text="🙈")
        else:
            self._password_entry.configure(show="•")
            self._toggle_btn.configure(text="👁")

    # ──────────────────────────────────────────────────────────────
    # Save
    # ──────────────────────────────────────────────────────────────

    def _save(self) -> None:
        """Build an AppConfig from the form fields and persist to disk."""
        from pathlib import Path as _Path

        try:
            folder_indices = [
                int(x.strip())
                for x in self._vars["ebs_folders_download"].get().split(",")
                if x.strip()
            ]
        except ValueError:
            folder_indices = [92, 95, 101]

        try:
            upload_folder_index = int(self._vars["ebs_folder_upload"].get())
        except ValueError:
            upload_folder_index = 92

        selected_display = getattr(
            self, "language_var", tk.StringVar(value="English")
        ).get()
        selected_code = "en"
        for code, disp in SUPPORTED_LANGUAGES.items():
            if disp == selected_display:
                selected_code = code
                break

        selected_ds_display = getattr(
            self,
            "data_source_var",
            tk.StringVar(value=t("settings.data_source.spreadsheet")),
        ).get()
        selected_ds_code = "spreadsheet"
        if selected_ds_display == t("settings.data_source.database"):
            selected_ds_code = "database"

        new_config = AppConfig(
            general=GeneralConfig(language=selected_code, data_source=selected_ds_code),
            paths=PathsConfig(
                dsno_directory=_Path(self._vars["dsno_directory"].get()),
                control_sheet=_Path(self._vars["control_sheet"].get()),
                customer_sheet=_Path(self._vars["customer_sheet"].get()),
                customer_sheet_pre_path=_Path(
                    self._vars["customer_sheet_pre_path"].get()
                ),
                database_dir=_Path(self._vars["database_dir"].get()),
            ),
            processor=ProcessorConfig(
                bypass_file_size_check=bool(
                    getattr(
                        self, "_bypass_size_check_var", tk.BooleanVar(value=False)
                    ).get()
                ),
                keep_original=bool(
                    getattr(
                        self, "_keep_original_var", tk.BooleanVar(value=False)
                    ).get()
                ),
            ),
            control_sheet_cols=ControlSheetColsConfig(
                invoice=self._vars.get(
                    "ebs_col_invoice", tk.StringVar(value="INVOICE")
                ).get(),
                dsno=self._vars.get(
                    "ebs_col_dsno", tk.StringVar(value="ARGUMENT2")
                ).get(),
                date=self._vars.get(
                    "ebs_col_date", tk.StringVar(value="CREATION_DATE")
                ).get(),
                status=self._vars.get(
                    "ebs_col_status", tk.StringVar(value="STATUS")
                ).get(),
                description=self._vars.get(
                    "ebs_col_description", tk.StringVar(value="Obs")
                ).get(),
            ),
            customer_sheet_cols=CustomerSheetColsConfig(
                invoice=self._vars.get(
                    "cust_col_invoice", tk.StringVar(value="Invoice")
                ).get(),
                booking=self._vars.get(
                    "cust_col_booking", tk.StringVar(value="Booking/HAWB")
                ).get(),
                container=self._vars.get(
                    "cust_col_container", tk.StringVar(value="Container")
                ).get(),
            ),
            customer_sheet_properties=CustomerSheetPropertiesConfig(
                sheet_name=self._vars.get(
                    "cust_sheet_name", tk.StringVar(value="")
                ).get(),
            ),
            ebs=EbsConfig(
                download_url=self._vars["ebs_download_url"].get(),
                upload_url=self._vars["ebs_upload_url"].get(),
                download_dir=_Path(self._vars["download_dir"].get()),
                upload_dir=_Path(self._vars["upload_dir"].get()),
                headless=self._headless_var.get(),
                folders=EbsFoldersConfig(
                    download_indices=folder_indices,
                    upload_index=upload_folder_index,
                ),
            ),
            credentials=CredentialsConfig(
                email=self._vars["cred_email"].get(),
                password=self._vars["cred_password"].get(),
            ),
        )

        try:
            save_config(new_config)
            messagebox.showinfo(
                t("settings.saved_title"),
                t("settings.saved_msg"),
            )
            if self._on_save:
                self._on_save()
            self.destroy()
        except Exception as exc:
            messagebox.showerror(
                t("settings.save_error_title"), f"Error saving settings:\n{exc}"
            )
