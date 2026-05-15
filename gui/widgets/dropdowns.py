"""Reusable dropdown widgets."""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from gui.themes.appearance import FONT_FAMILY as _FONT_FAMILY


class MultiSelectDropdown(ctk.CTkFrame):
    """A button that opens a popup with checkboxes for multi-select."""

    def __init__(self, master, options: list[str], placeholder: str = "All", **kwargs) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self._options_list = options
        self._placeholder = placeholder
        self._vars: dict[str, tk.BooleanVar] = {}
        self._popup: tk.Toplevel | None = None

        self._btn = ctk.CTkButton(
            self,
            text=placeholder,
            width=160,
            height=28,
            corner_radius=6,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
            anchor="w",
            command=self._toggle_popup,
        )
        self._btn.pack()

    def set_options(self, options: list[str]) -> None:
        self._options_list = options
        self._vars = {}
        self._update_label()

    def _toggle_popup(self) -> None:
        if self._popup and self._popup.winfo_exists():
            self._popup.destroy()
            self._popup = None
            return
        self._open_popup()

    def _open_popup(self) -> None:
        popup = tk.Toplevel(self)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        self._popup = popup

        # Position below button
        self.update_idletasks()
        bx = self._btn.winfo_rootx()
        by = self._btn.winfo_rooty() + self._btn.winfo_height() + 2
        popup.geometry(f"+{bx}+{by}")

        # Styling based on appearance mode
        mode = ctk.get_appearance_mode().lower()
        bg = "#1c1c1e" if mode == "dark" else "#f0f0f0"
        fg = "white" if mode == "dark" else "black"
        check_bg = "#2c2c2e" if mode == "dark" else "#e0e0e0"
        hover_bg = "#3a3a3c" if mode == "dark" else "#d0d0d0"
        border_color = "#444" if mode == "dark" else "#bbb"

        frame = tk.Frame(
            popup, bg=bg,
            relief="flat",
            bd=1,
            highlightthickness=1,
            highlightbackground=border_color,
        )
        frame.pack(fill="both", expand=True)

        if not self._options_list:
            tk.Label(
                frame, text="No options available", bg=bg, fg="gray",
                font=(_FONT_FAMILY, 10), padx=10, pady=6,
            ).pack(fill="x")
        else:
            for opt in self._options_list:
                var = self._vars.setdefault(opt, tk.BooleanVar(value=False))
                row = tk.Frame(frame, bg=bg, cursor="hand2")
                row.pack(fill="x", padx=4, pady=1)

                cb = tk.Checkbutton(
                    row, text=opt, variable=var,
                    bg=bg, fg=fg, selectcolor=check_bg,
                    activebackground=hover_bg, activeforeground=fg,
                    font=(_FONT_FAMILY, 11),
                    anchor="w",
                    relief="flat",
                    bd=0,
                    padx=6, pady=4,
                    command=self._update_label,
                )
                cb.pack(fill="x")

            # Separator + Clear/All buttons
            sep = tk.Frame(frame, bg=border_color, height=1)
            sep.pack(fill="x", padx=4, pady=(4, 0))

            btn_row = tk.Frame(frame, bg=bg)
            btn_row.pack(fill="x", padx=4, pady=4)

            def _make_action_btn(parent, text, cmd, side="left"):
                b = tk.Label(
                    parent, text=text, bg=check_bg, fg=fg,
                    font=(_FONT_FAMILY, 10), padx=8, pady=3,
                    cursor="hand2", relief="flat",
                )
                b.pack(side=side, padx=2)
                b.bind("<Button-1>", cmd)
                b.bind("<Enter>", lambda e: b.configure(bg=hover_bg))
                b.bind("<Leave>", lambda e: b.configure(bg=check_bg))
                return b

            _make_action_btn(btn_row, "All", lambda e: self._check_all())
            _make_action_btn(btn_row, "Clear", lambda e: self._check_none())

        # Close when clicking outside
        popup.bind("<FocusOut>", lambda e: self._close_popup_if_outside(e))
        popup.focus_set()

    def _close_popup_if_outside(self, event) -> None:
        try:
            wx, wy = event.widget.winfo_rootx(), event.widget.winfo_rooty()
            _ = wx + wy  # just ensure it exists
        except Exception:
            pass
        # Delay check so clicks on child widgets register first
        self.after(100, self._maybe_close_popup)

    def _maybe_close_popup(self) -> None:
        if self._popup and self._popup.winfo_exists():
            try:
                focused = self._popup.focus_get()
                if focused is None:
                    self._popup.destroy()
                    self._popup = None
            except Exception:
                pass

    def _check_all(self) -> None:
        for var in self._vars.values():
            var.set(True)
        self._update_label()

    def _check_none(self) -> None:
        for var in self._vars.values():
            var.set(False)
        self._update_label()

    def _update_label(self) -> None:
        selected = self.get_selected()
        if not selected:
            self._btn.configure(text=self._placeholder)
        elif len(selected) == len(self._options_list) and self._options_list:
            self._btn.configure(text="All")
        else:
            label = ", ".join(selected)
            if len(label) > 22:
                label = f"{len(selected)} selected"
            self._btn.configure(text=label)

    def get_selected(self) -> list[str]:
        """Return list of checked options; empty list means 'All'."""
        return [opt for opt, var in self._vars.items() if var.get()]

    def reset(self) -> None:
        """Uncheck all options."""
        self._check_none()

