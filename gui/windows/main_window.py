"""Main CustomTkinter application window."""

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
from dsno_processor.i18n import set_language, t
from gui.dialogs.import_wizards import ImportControlWizard, ImportWizard
from gui.dialogs.language_menu import LanguageMenu
from gui.dialogs.settings_window import SettingsWindow
from gui.themes.appearance import FONT_FAMILY as _FONT_FAMILY
from gui.widgets.dashboard import (
    BlockingOverlay,
    LogWindow,
    ProgressDashboard,
    _DashboardLogHandler,
)
from gui.widgets.dropdowns import MultiSelectDropdown
from gui.widgets.inputs import DateInput, DateTimeInput, FilePickerRow
from gui.controllers.app_actions import AppActionsMixin
from gui.frames.download_tab import DownloadTabMixin
from gui.frames.processor_tab import ProcessorTabMixin
from gui.frames.upload_tab import UploadTabMixin

log = logging.getLogger(__name__)


class DSNOApp(AppActionsMixin, UploadTabMixin, DownloadTabMixin, ProcessorTabMixin, ctk.CTk):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()

        # Tenta carregar o ícone
        try:
            icon_path = get_asset_path("assets/icons/favicon.ico")
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
            else:
                logging.error(f"Ícone não encontrado em: {icon_path}")
        except Exception as e:
            logging.error(f"Erro ao carregar ícone: {e}")

        # ── Load config ──────────────────────────────────────────
        try:
            self._app_config = load_config()
        except ConfigurationError:
            self._app_config = None

        cfg = self._app_config
        if cfg:
            set_language(cfg.language)

        self._TAB_PROC     = t("tab.processor")
        self._TAB_DOWNLOAD = t("tab.download")
        self._TAB_UPLOAD   = t("tab.upload")

        self.title(t("app.title"))
        
        # Center the window on the screen
        appResolution = "1270x720"
        x = (self.winfo_screenwidth() // 2) - (int(appResolution.split("x")[0]) // 2)
        y = (self.winfo_screenheight() // 2) - (int(appResolution.split("x")[1]) // 2)
        self.geometry(f"{appResolution}+{x}+{y}")
        
        self.minsize(640, 480)

        default_customer = str(cfg.customer_sheet) if cfg else ""
        default_control  = str(cfg.control_sheet)  if cfg else ""
        default_dsno_dir = str(cfg.dsno_directory)  if cfg else ""
        self._customer_pre_path = str(cfg.customer_sheet_pre_path) if cfg else ""

        self._dl_handler = None
        self._ul_handler = None

        self.log_window = LogWindow(self)
        self.log_handler = _DashboardLogHandler(self.log_window.textbox)
        self.log_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

        # ── Build UI ─────────────────────────────────────────────
        self._create_widgets(default_customer, default_control, default_dsno_dir)
        
        # Initialize blocking overlay
        h_imgs = getattr(self.dashboard, "_hourglass_imgs", [])
        self.blocking_overlay = BlockingOverlay(self, h_imgs)
        
        self._setup_logging()
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _on_closing(self) -> None:
        """Handle window close event to ensure background threads can clean up."""
        for ev_attr in ["_processor_cancel_event", "_dl_cancel_event", "_ul_cancel_event"]:
            if hasattr(self, ev_attr):
                ev = getattr(self, ev_attr)
                if ev:
                    ev.set()
        self.destroy()

    # ──────────────────────────────────────────────────────────────
    # Setup
    # ──────────────────────────────────────────────────────────────

    def _setup_logging(self) -> None:
        root_logger = logging.getLogger()
        root_logger.addHandler(self.log_handler)
        root_logger.setLevel(logging.INFO)
        
    def _show_log_window(self) -> None:
        self.log_window.show()

    def _clear_log(self) -> None:
        self.log_window.textbox.configure(state="normal")
        self.log_window.textbox.delete("1.0", "end")
        self.log_window.textbox.configure(state="disabled")

    def _show_blocking_overlay(self) -> None:
        # capture_blur() must run BEFORE place() so the overlay
        # itself is not yet visible in the screenshot
        self.blocking_overlay.capture_blur()
        self.blocking_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.blocking_overlay.lift()
        self.blocking_overlay.start_animation()

    def _hide_blocking_overlay(self) -> None:
        self.blocking_overlay.stop_animation()
        self.blocking_overlay.place_forget()
    
    def _create_widgets(
        self,
        default_customer: str,
        default_control: str,
        default_dsno_dir: str,
    ) -> None:
        pad = 16
        
        # Frame do rodapé
        footer_frame = ctk.CTkFrame(self, fg_color="transparent", height=30)
        footer_frame.pack(side="bottom", fill="x", padx=pad, pady=(0, 8))

        # Botão de log (esquerda)
        log_icon = ctk.CTkImage(
            light_image=Image.open(get_asset_path("assets/icons/bug_light.png")),
            dark_image=Image.open(get_asset_path("assets/icons/bug_dark.png")),
            size=(15, 15)
        )

        ctk.CTkButton(
            footer_frame,
            text="",
            image=log_icon,
            width=30,
            height=30,
            corner_radius=6,
            fg_color="transparent",
            command=self._show_log_window,
        ).pack(side="left")

        # Label autor (direita)
        ctk.CTkLabel(
            footer_frame,
            text="Made by Matheus Borges",
            font=ctk.CTkFont(family=_FONT_FAMILY, size=9),
            text_color="gray60",
        ).pack(side="right")

        # ── Header ───────────────────────────────────────────────
        header = ctk.CTkFrame(self, corner_radius=12)
        header.pack(fill="x", padx=pad, pady=(pad, 6))

        header_inner = ctk.CTkFrame(header, fg_color="transparent")
        header_inner.pack(fill="x", padx=12, pady=(10, 0))
        
        # 1. Text Container - Perfectly Centered
        # We use a subframe that we will pack with expand=True to center it
        text_container = ctk.CTkFrame(header_inner, fg_color="transparent")
        text_container.pack(expand=True)

        title_label = ctk.CTkLabel(
            text_container,
            text=t("app.title"),
            font=ctk.CTkFont(family=_FONT_FAMILY, size=22, weight="bold"),
        )
        title_label.pack()

        ctk.CTkLabel(
            text_container,
            text=t("app.subtitle"),
            font=ctk.CTkFont(family=_FONT_FAMILY, size=13),
            text_color="gray60",
        ).pack()

        # 2. Logo - Placed relative to the title_label without affecting its layout
        try:
            logo_img = ctk.CTkImage(
                light_image=Image.open(get_asset_path("assets/icons/swap_light.png")),
                dark_image=Image.open(get_asset_path("assets/icons/swap_dark.png")),
                size=(28, 28)
            )
            logo_label = ctk.CTkLabel(text_container, image=logo_img, text="")
            # Place it to the left of the title_label using relative coordinates
            logo_label.place(in_=title_label, relx=0, x=-35, rely=0.5, anchor="center")
        except Exception:
            pass

        # 3. Buttons Container - On the far right
        # We use a separate frame inside header_inner and place it using absolute positioning or packing
        header_btns = ctk.CTkFrame(header_inner, fg_color="transparent")
        header_btns.place(relx=1.0, rely=0, anchor="ne")

        ctk.CTkButton(
            header_btns,
            image=ctk.CTkImage(
                light_image=Image.open(get_asset_path("assets/icons/settings_light.png")),
                dark_image=Image.open(get_asset_path("assets/icons/settings_dark.png")),
                size=(18, 18)
            ),
            text="",
            width=30,
            height=30,
            corner_radius=6,
            fg_color="transparent",
            command=self._open_settings,
        ).pack(side="right")

        self._lang_btn = ctk.CTkButton(
            header_btns,
            image=ctk.CTkImage(
                light_image=Image.open(get_asset_path("assets/icons/language_light.png")),
                dark_image=Image.open(get_asset_path("assets/icons/language_dark.png")),
                size=(18, 18)
            ),
            text="",
            width=30,
            height=30,
            corner_radius=6,
            fg_color="transparent",
            command=self._change_language,
        )
        self._lang_btn.pack(side="right", padx=(0, 4))

        # Refresh/Reset button
        ctk.CTkButton(
            header_btns,
            image=ctk.CTkImage(
                light_image=Image.open(get_asset_path("assets/icons/refresh_light.png")),
                dark_image=Image.open(get_asset_path("assets/icons/refresh_dark.png")),
                size=(18, 18)
            ),
            text="",
            width=30,
            height=30,
            corner_radius=6,
            fg_color="transparent",
            command=self._reset_current_dashboard,
        ).pack(side="right", padx=(0, 2))

        # ── Tabview ──────────────────────────────────────────────
        self._tabview = ctk.CTkTabview(
            self,
            corner_radius=10,
            segmented_button_fg_color=("gray80", "gray20"),
            segmented_button_selected_color=("#1f6aa5", "#1f6aa5"),
            segmented_button_unselected_hover_color=("gray70", "gray30"),
        )
        self._tabview.pack(fill="both", expand=True, padx=pad, pady=(0, 8))
        self._tabview.add(self._TAB_PROC)
        self._tabview.add(self._TAB_DOWNLOAD)
        self._tabview.add(self._TAB_UPLOAD)

        self._build_tab_processor(default_customer, default_control, default_dsno_dir)
        self._build_tab_download()
        self._build_tab_upload()



def start_gui() -> None:
    """Launch the DSNO Processor GUI."""
    app = DSNOApp()
    app.mainloop()
