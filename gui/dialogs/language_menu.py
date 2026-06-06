"""Language selection popup dialog."""

from __future__ import annotations

import customtkinter as ctk

from gui.assets import get_asset_path
from gui.themes.appearance import FONT_FAMILY as _FONT_FAMILY


class LanguageMenu(ctk.CTkToplevel):
    """Small popup window for language selection."""

    def __init__(self, master, lang_btn, on_select) -> None:
        super().__init__(master)
        self.overrideredirect(True)  # Remove title bar
        self.attributes("-topmost", True)
        self.on_select = on_select

        # Position below the button
        self.update_idletasks()  # Ensure dimensions are calculated
        btn_x = lang_btn.winfo_rootx()
        btn_y = lang_btn.winfo_rooty()
        btn_h = lang_btn.winfo_height()

        # UI Setup - Using a transparency hack for rounded corners on Windows
        menu_bg = ("gray95", "gray10")
        self.configure(fg_color="#010101")
        self.attributes("-transparentcolor", "#010101")

        inner = ctk.CTkFrame(
            self,
            fg_color=menu_bg,
            corner_radius=10,
            border_width=1,
            border_color=("gray80", "gray20"),
        )
        inner.pack(padx=2, pady=2, fill="both", expand=False)

        from dsno_processor.i18n import SUPPORTED_LANGUAGES, get_language

        current_lang = get_language()

        try:
            from PIL import Image

            check_icon = ctk.CTkImage(
                light_image=Image.open(get_asset_path("assets/icons/check_light.png")),
                dark_image=Image.open(get_asset_path("assets/icons/check_dark.png")),
                size=(14, 14),
            )
        except Exception:
            check_icon = None

        # Margins inside the box
        margin_x = 8
        margin_y = 6
        spacing = 4

        for i, (code, name) in enumerate(SUPPORTED_LANGUAGES.items()):
            # Use specific padding for top and bottom elements to create a group margin
            p_top = margin_y if i == 0 else spacing // 2
            p_bottom = margin_y if i == len(SUPPORTED_LANGUAGES) - 1 else spacing // 2

            btn = ctk.CTkButton(
                inner,
                text=name,
                image=check_icon if code == current_lang else None,
                compound="left",
                anchor="w",
                height=28,
                width=120,
                corner_radius=6,
                fg_color="transparent",
                text_color=("gray20", "gray90"),
                hover_color=("gray80", "gray20"),
                font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
                command=lambda c=code: self._select(c),
            )
            btn.pack(fill="x", padx=margin_x, pady=(p_top, p_bottom))

        # Dynamic height calculation
        total_h = (
            (len(SUPPORTED_LANGUAGES) * 28)
            + (2 * margin_y)
            + ((len(SUPPORTED_LANGUAGES) - 1) * spacing)
            + 10
        )
        self.geometry(f"140x{total_h}+{btn_x - 100}+{btn_y + btn_h + 5}")

        # Close on focus out
        self.bind("<FocusOut>", lambda e: self.destroy())
        self.focus_set()

    def _select(self, code: str) -> None:
        self.on_select(code)
        self.destroy()
