"""Reusable form input widgets."""

from __future__ import annotations

import calendar
import tkinter as tk
from datetime import datetime
from typing import Callable

import customtkinter as ctk

from dsno_processor.i18n import t
from gui.themes.appearance import (
    DATE_PATTERN as _DATE_PATTERN,
    DATETIME_PATTERN as _DATETIME_PATTERN,
    FONT_FAMILY as _FONT_FAMILY,
)


def add_placeholder(entry, placeholder_text):
    entry.insert(0, placeholder_text)
    entry.configure(text_color="gray")

    def on_focus_in(event):
        if entry.get() == placeholder_text:
            entry.delete(0, "end")
            entry.configure(text_color=("black", "white"))

    def on_focus_out(event):
        if not entry.get():
            entry.insert(0, placeholder_text)
            entry.configure(text_color="gray")

    entry.bind("<FocusIn>", on_focus_in)
    entry.bind("<FocusOut>", on_focus_out)


class _CalendarPopup(ctk.CTkToplevel):
    """Month calendar popup. When *show_time* is True an HH:MM:SS spinner
    section and Apply/Cancel buttons are shown; otherwise clicking a day
    immediately confirms the selection and closes the popup."""

    _DAYS = t("cal.days").split(",")
    _CELL = 38  # px per column

    def __init__(
        self,
        master_input: "DateInput",
        year: int,
        month: int,
        *,
        show_time: bool = False,
        initial_day: int | None = None,
        initial_hour: int = 0,
        initial_minute: int = 0,
        initial_second: int = 0,
    ) -> None:
        super().__init__()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self._master_input = master_input
        self._year = year
        self._month = month
        self._show_time = show_time
        self._selected_day: int | None = initial_day
        self._hour = initial_hour
        self._minute = initial_minute
        self._second = initial_second

        outer = ctk.CTkFrame(self, corner_radius=10, border_width=1)
        outer.pack(fill="both", expand=True, padx=2, pady=2)

        # ── Calendar section ──────────────────────────────────────
        self._cal_frame = ctk.CTkFrame(outer, fg_color="transparent")
        self._cal_frame.pack(fill="x", padx=8, pady=(8, 4))

        # ── Time section (only when show_time) ────────────────────
        if show_time:
            time_frame = ctk.CTkFrame(
                outer, fg_color=("gray85", "gray17"), corner_radius=8
            )
            time_frame.pack(fill="x", padx=8, pady=(4, 6))

            ctk.CTkLabel(
                time_frame,
                text=t("cal.time"),
                font=ctk.CTkFont(family=_FONT_FAMILY, size=11, weight="bold"),
                text_color=("gray40", "gray55"),
            ).pack(pady=(6, 2))

            spinners = ctk.CTkFrame(time_frame, fg_color="transparent")
            spinners.pack(pady=(0, 6))

            self._h_var = tk.StringVar(value=f"{initial_hour:02d}")
            self._m_var = tk.StringVar(value=f"{initial_minute:02d}")
            self._s_var = tk.StringVar(value=f"{initial_second:02d}")

            def _spinner(parent, label, var, delta_fn):
                col = ctk.CTkFrame(parent, fg_color="transparent")
                col.pack(side="left", padx=6)
                ctk.CTkLabel(
                    col,
                    text=label,
                    font=ctk.CTkFont(family=_FONT_FAMILY, size=10),
                    text_color=("gray50", "gray60"),
                ).pack()
                ctk.CTkButton(
                    col,
                    text="▲",
                    width=34,
                    height=22,
                    corner_radius=4,
                    fg_color=("gray75", "gray25"),
                    hover_color=("gray65", "gray35"),
                    font=ctk.CTkFont(size=11),
                    command=lambda: delta_fn(1),
                ).pack()
                ctk.CTkEntry(
                    col,
                    textvariable=var,
                    width=38,
                    height=28,
                    justify="center",
                    font=ctk.CTkFont(family=_FONT_FAMILY, size=13, weight="bold"),
                ).pack(pady=2)
                ctk.CTkButton(
                    col,
                    text="▼",
                    width=34,
                    height=22,
                    corner_radius=4,
                    fg_color=("gray75", "gray25"),
                    hover_color=("gray65", "gray35"),
                    font=ctk.CTkFont(size=11),
                    command=lambda: delta_fn(-1),
                ).pack()

            def _upd_h(d):
                self._hour = (self._hour + d) % 24
                self._h_var.set(f"{self._hour:02d}")

            def _upd_m(d):
                self._minute = (self._minute + d) % 60
                self._m_var.set(f"{self._minute:02d}")

            def _upd_s(d):
                self._second = (self._second + d) % 60
                self._s_var.set(f"{self._second:02d}")

            _spinner(spinners, "HH", self._h_var, _upd_h)
            ctk.CTkLabel(
                spinners,
                text=":",
                font=ctk.CTkFont(size=18, weight="bold"),
                text_color=("gray50", "gray60"),
            ).pack(side="left", pady=(14, 0))
            _spinner(spinners, "MM", self._m_var, _upd_m)
            ctk.CTkLabel(
                spinners,
                text=":",
                font=ctk.CTkFont(size=18, weight="bold"),
                text_color=("gray50", "gray60"),
            ).pack(side="left", pady=(14, 0))
            _spinner(spinners, "SS", self._s_var, _upd_s)

            # Sync manual typing
            def _sync(var, lo, hi, attr):
                try:
                    setattr(self, attr, max(lo, min(hi, int(var.get()))))
                except ValueError:
                    pass

            self._h_var.trace_add(
                "write", lambda *_: _sync(self._h_var, 0, 23, "_hour")
            )
            self._m_var.trace_add(
                "write", lambda *_: _sync(self._m_var, 0, 59, "_minute")
            )
            self._s_var.trace_add(
                "write", lambda *_: _sync(self._s_var, 0, 59, "_second")
            )

            # Apply / Cancel buttons
            btn_row = ctk.CTkFrame(outer, fg_color="transparent")
            btn_row.pack(fill="x", padx=8, pady=(0, 8))
            ctk.CTkButton(
                btn_row,
                text=t("btn.cancel"),
                width=90,
                height=30,
                corner_radius=6,
                fg_color=("gray70", "gray30"),
                hover_color=("gray60", "gray40"),
                font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
                command=self.destroy,
            ).pack(side="left", expand=True, padx=(0, 4))
            ctk.CTkButton(
                btn_row,
                text="✔  Apply",
                width=90,
                height=30,
                corner_radius=6,
                font=ctk.CTkFont(family=_FONT_FAMILY, size=12, weight="bold"),
                command=self._apply,
            ).pack(side="left", expand=True, padx=(4, 0))

        self._build_calendar()
        self.after(10, self._position)

        # Close on outside click (date-only mode)
        if not show_time:
            self._click_id = self._master_input.winfo_toplevel().bind(
                "<Button-1>", self._on_root_click, add="+"
            )

    # ── Destroy ────────────────────────────────────────────────────
    def destroy(self) -> None:
        if not self._show_time:
            try:
                self._master_input.winfo_toplevel().unbind("<Button-1>", self._click_id)
            except Exception:
                pass
        self._master_input._popup = None
        super().destroy()

    def _on_root_click(self, event) -> None:
        try:
            w = event.widget.winfo_containing(event.x_root, event.y_root)
            while w is not None:
                if w is self:
                    return
                w = w.master
        except Exception:
            pass
        self.destroy()

    # ── Calendar grid ──────────────────────────────────────────────
    def _build_calendar(self) -> None:
        cell = self._CELL

        for w in self._cal_frame.winfo_children():
            w.destroy()

        # Navigation row
        nav = ctk.CTkFrame(self._cal_frame, fg_color="transparent")
        nav.pack(fill="x")
        ctk.CTkButton(
            nav,
            text="◀",
            width=28,
            height=26,
            corner_radius=5,
            fg_color="transparent",
            hover_color=("gray70", "gray30"),
            command=self._prev_month,
            font=ctk.CTkFont(size=12),
        ).pack(side="left")
        ctk.CTkLabel(
            nav,
            text=f"{calendar.month_name[self._month]}  {self._year}",
            font=ctk.CTkFont(family=_FONT_FAMILY, size=13, weight="bold"),
        ).pack(side="left", expand=True)
        ctk.CTkButton(
            nav,
            text="▶",
            width=28,
            height=26,
            corner_radius=5,
            fg_color="transparent",
            hover_color=("gray70", "gray30"),
            command=self._next_month,
            font=ctk.CTkFont(size=12),
        ).pack(side="right")

        # Day grid
        grid = ctk.CTkFrame(self._cal_frame, fg_color="transparent")
        grid.pack(fill="x", pady=(4, 0))
        for col in range(7):
            grid.columnconfigure(col, minsize=cell)
        for col, d in enumerate(self._DAYS):
            ctk.CTkLabel(
                grid,
                text=d,
                width=cell,
                font=ctk.CTkFont(family=_FONT_FAMILY, size=11),
                text_color="gray55",
            ).grid(row=0, column=col, padx=1, pady=(0, 2))

        cal_obj = calendar.Calendar(firstweekday=0)
        weeks = cal_obj.monthdayscalendar(self._year, self._month)
        today = datetime.now()

        for row_i, week in enumerate(weeks, start=1):
            for col, day in enumerate(week):
                if day == 0:
                    ctk.CTkLabel(grid, text="", width=cell).grid(
                        row=row_i, column=col, padx=1, pady=1
                    )
                else:
                    selected = day == self._selected_day
                    is_today = (
                        day == today.day
                        and self._month == today.month
                        and self._year == today.year
                    )
                    bg = (
                        ("#1f6aa5", "#1f6aa5")
                        if selected
                        else (("gray80", "gray25") if is_today else "transparent")
                    )
                    tc = (
                        "white"
                        if selected
                        else (("#1f6aa5", "#4ba3e3") if is_today else None)
                    )
                    hover = (
                        ("#2979b5", "#2979b5")
                        if selected
                        else (
                            ("gray70", "gray35") if is_today else ("gray75", "gray30")
                        )
                    )
                    ctk.CTkButton(
                        grid,
                        text=str(day),
                        width=cell,
                        height=30,
                        corner_radius=6,
                        font=ctk.CTkFont(
                            family=_FONT_FAMILY,
                            size=12,
                            weight="bold" if is_today else "normal",
                        ),
                        fg_color=bg,
                        hover_color=hover,
                        text_color=tc,
                        command=lambda d=day: self._pick_day(d),
                    ).grid(row=row_i, column=col, padx=1, pady=1)

    # ── Day / month actions ────────────────────────────────────────
    def _pick_day(self, day: int) -> None:
        self._selected_day = day
        if not self._show_time:
            # No time picker → confirm immediately
            self._master_input._set_date(day, self._month, self._year)
            self.destroy()
        else:
            self._build_calendar()

    def _prev_month(self) -> None:
        if self._month == 1:
            self._month, self._year = 12, self._year - 1
        else:
            self._month -= 1
        self._build_calendar()

    def _next_month(self) -> None:
        if self._month == 12:
            self._month, self._year = 1, self._year + 1
        else:
            self._month += 1
        self._build_calendar()

    def _apply(self) -> None:
        """Called only in show_time mode via the Apply button."""
        day = self._selected_day if self._selected_day is not None else 1
        self._master_input._set_datetime(
            day,
            self._month,
            self._year,
            self._hour,
            self._minute,
            self._second,
        )
        self.destroy()

    # ── Positioning ────────────────────────────────────────────────
    def _position(self) -> None:
        self.update_idletasks()
        entry = self._master_input.entry
        x = entry.winfo_rootx()
        y = entry.winfo_rooty() + entry.winfo_height() + 4
        sh, h = self.winfo_screenheight(), self.winfo_height()

        if y + h > sh - 40:
            y_above = entry.winfo_rooty() - h - 4
            if y_above >= 10:
                y = y_above

        y = max(10, min(y, sh - h - 40))
        self.geometry(f"+{x}+{y}")


# ── Unified date / date-time entry ───────────────────────────────────
class DateInput(ctk.CTkFrame):
    """Date entry with calendar popup.

    When *show_time* is False (default): displays DD/MM/YYYY, clicking a day
    in the calendar confirms immediately.
    When *show_time* is True: displays DD/MM/YYYY HH:MM:SS, the calendar
    includes time spinners and Apply/Cancel buttons.
    """

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        label: str = "",
        show_time: bool = False,
        prefill_today: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self._popup: _CalendarPopup | None = None
        self._show_time = show_time
        self._fmt = "%d/%m/%Y %H:%M:%S" if show_time else "%d/%m/%Y"
        self._pattern = _DATETIME_PATTERN if show_time else _DATE_PATTERN

        if label:
            ctk.CTkLabel(
                self,
                text=label,
                font=ctk.CTkFont(family=_FONT_FAMILY, size=13),
            ).pack(side="left", padx=(0, 6))

        placeholder = "DD/MM/YYYY HH:MM:SS" if show_time else "DD/MM/YYYY"
        self.entry = ctk.CTkEntry(
            self,
            width=190 if show_time else 120,
            placeholder_text=placeholder,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=13 if not show_time else 12),
        )
        self.entry.pack(side="left")

        ctk.CTkButton(
            self,
            text="📅",
            width=32,
            height=28,
            corner_radius=6,
            fg_color="transparent",
            hover_color=("gray75", "gray30"),
            command=self._toggle_popup,
            font=ctk.CTkFont(size=15),
        ).pack(side="left", padx=(4, 0))

        if prefill_today:
            self.entry.insert(0, datetime.now().strftime(self._fmt))

        self.entry.bind("<FocusOut>", self._validate)

    # ── Public API ────────────────────────────────────────────────
    def get(self) -> str:
        return self.entry.get().strip()

    def set(self, value: str) -> None:
        self.entry.delete(0, "end")
        self.entry.insert(0, value)

    def reset(self) -> None:
        """Reset the entry to today's date/time."""
        self.entry.delete(0, "end")
        self.entry.insert(0, datetime.now().strftime(self._fmt))
        # Reset border color in case it was invalid before
        theme_color = ctk.ThemeManager.theme["CTkEntry"]["border_color"]
        self.entry.configure(border_color=theme_color)

    # ── Callbacks from popup ──────────────────────────────────────
    def _set_date(self, day: int, month: int, year: int) -> None:
        """Called by the popup in date-only mode."""
        self.entry.delete(0, "end")
        self.entry.insert(0, f"{day:02d}/{month:02d}/{year}")
        self.entry.configure(
            border_color=ctk.ThemeManager.theme["CTkEntry"]["border_color"]
        )

    def _set_datetime(self, day, month, year, hour, minute, second) -> None:
        """Called by the popup in date+time mode."""
        self.entry.delete(0, "end")
        self.entry.insert(
            0, f"{day:02d}/{month:02d}/{year} {hour:02d}:{minute:02d}:{second:02d}"
        )
        self.entry.configure(
            border_color=ctk.ThemeManager.theme["CTkEntry"]["border_color"]
        )

    # ── Toggle ────────────────────────────────────────────────────
    def _toggle_popup(self) -> None:
        if self._popup is not None and self._popup.winfo_exists():
            self._popup.destroy()
            self._popup = None
            return

        now = datetime.now()
        day: int | None = None
        h, m, s = 0, 0, 0

        value = self.get()
        if self._pattern.match(value):
            try:
                dt = datetime.strptime(value, self._fmt)
                now, day = dt, dt.day
                if self._show_time:
                    h, m, s = dt.hour, dt.minute, dt.second
            except ValueError:
                pass

        self._popup = _CalendarPopup(
            self,
            now.year,
            now.month,
            show_time=self._show_time,
            initial_day=day,
            initial_hour=h,
            initial_minute=m,
            initial_second=s,
        )

    # ── Validation ────────────────────────────────────────────────
    def _validate(self, _event=None) -> None:
        value = self.get()
        if not value:
            return
        theme_color = ctk.ThemeManager.theme["CTkEntry"]["border_color"]
        if self._pattern.match(value):
            try:
                datetime.strptime(value, self._fmt)
                self.entry.configure(border_color=theme_color)
                return
            except ValueError:
                pass
        self.entry.configure(border_color="#e74c3c")


# Alias for convenience — behaves exactly like DateInput(show_time=True)
class DateTimeInput(DateInput):
    """DateInput with time picker enabled by default."""

    def __init__(self, master: ctk.CTkBaseClass, **kwargs) -> None:
        kwargs.setdefault("show_time", True)
        super().__init__(master, **kwargs)


class FilePickerRow(ctk.CTkFrame):
    """A row with label, entry, and browse button."""

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        label: str,
        default: str = "",
        browse_command=None,
        placeholder: str = "",
        on_change: Callable | None = None,
        **kwargs,
    ) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self.columnconfigure(1, weight=1)

        # Clean default if it's '.' (pathlib.Path default)
        if default == ".":
            default = ""

        ctk.CTkLabel(
            self,
            text=label,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=13),
            width=130,
            anchor="w",
        ).grid(row=0, column=0, padx=(0, 8), sticky="w")

        # (We avoid textvariable because it often prevents placeholder_text from appearing in CTk)
        self.entry = ctk.CTkEntry(
            self,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
            placeholder_text=placeholder,
        )
        self.entry.grid(row=0, column=1, sticky="ew")

        if default:
            self.entry.insert(0, default)

        self.on_change = on_change
        self.entry.bind("<KeyRelease>", lambda e: self._handle_change())

        def _internal_browse():
            if browse_command:
                browse_command()
                self._handle_change()

        ctk.CTkButton(
            self,
            text=t("btn.browse"),
            width=80,
            command=_internal_browse,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
        ).grid(row=0, column=2, padx=(8, 0))

    def get(self) -> str:
        return self.entry.get()

    def set(self, value: str) -> None:
        if value == ".":
            value = ""
        self.entry.delete(0, tk.END)
        self.entry.insert(0, value)
        self._handle_change()

    def _handle_change(self) -> None:
        if self.on_change:
            self.on_change()
