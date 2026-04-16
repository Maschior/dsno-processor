"""DSNO Processor GUI — CustomTkinter interface for batch DSNO processing."""

import calendar
import logging
import os
import re
import sys
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image

def get_asset_path(relative_path: str) -> str:
    """Resolve paths for both development and PyInstaller production."""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        # In directory mode, this points to the '_internal' folder.
        base_path = sys._MEIPASS
    except AttributeError:
        # Development mode
        base_path = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(base_path, relative_path)

from dsno_processor import process_dsno
from dsno_processor.config import (
    AppConfig,
    ControlSheetColsConfig,
    CustomerSheetColsConfig,
    CredentialsConfig,
    EbsConfig,
    EbsFoldersConfig,
    GeneralConfig,
    PathsConfig,
    load_config,
    save_config,
)
from dsno_processor.ebs_download import DownloadConfig, run_download
from dsno_processor.ebs_upload import UploadConfig, run_upload
from dsno_processor.exceptions import ConfigurationError, CanceledError, LoginError
from dsno_processor.i18n import t, set_language, SUPPORTED_LANGUAGES
from dsno_processor.info_reader import get_status_options

# ── Appearance ────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

_FONT_FAMILY = "Segoe UI"
_DATE_PATTERN = re.compile(r"^\d{2}/\d{2}/\d{4}$")

#  ── Custom functions ────────────────────────────────────────────────────────

def add_placeholder(entry, placeholder_text):
    entry.insert(0, placeholder_text)
    entry.configure(text_color="gray")

    def on_focus_in(event):
        if entry.get() == placeholder_text:
            entry.delete(0, "end")
            entry.configure(text_color=("black", "white"))  # light/dark mode

    def on_focus_out(event):
        if not entry.get():
            entry.insert(0, placeholder_text)
            entry.configure(text_color="gray")

    entry.bind("<FocusIn>", on_focus_in)
    entry.bind("<FocusOut>", on_focus_out)

# ── Logging handler ──────────────────────────────────────────────────
class _DashboardLogHandler(logging.Handler):
    """Route log records to a CTkTextbox inside a ProgressDashboard."""

    def __init__(self, textbox: ctk.CTkTextbox) -> None:
        super().__init__()
        self.textbox = textbox

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)

        def _append() -> None:
            self.textbox.configure(state="normal")
            self.textbox.insert("end", msg + "\n")
            self.textbox.configure(state="disabled")
            self.textbox.see("end")

        try:
            self.textbox.after(0, _append)
        except Exception:
            pass


# ── Calendar popup (unified: date-only or date+time) ─────────────────
_DATETIME_PATTERN = re.compile(r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}$")


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
            time_frame = ctk.CTkFrame(outer, fg_color=("gray85", "gray17"), corner_radius=8)
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
                ctk.CTkLabel(col, text=label,
                    font=ctk.CTkFont(family=_FONT_FAMILY, size=10),
                    text_color=("gray50", "gray60"),
                ).pack()
                ctk.CTkButton(col, text="▲", width=34, height=22, corner_radius=4,
                    fg_color=("gray75", "gray25"), hover_color=("gray65", "gray35"),
                    font=ctk.CTkFont(size=11), command=lambda: delta_fn(1),
                ).pack()
                ctk.CTkEntry(col, textvariable=var, width=38, height=28,
                    justify="center",
                    font=ctk.CTkFont(family=_FONT_FAMILY, size=13, weight="bold"),
                ).pack(pady=2)
                ctk.CTkButton(col, text="▼", width=34, height=22, corner_radius=4,
                    fg_color=("gray75", "gray25"), hover_color=("gray65", "gray35"),
                    font=ctk.CTkFont(size=11), command=lambda: delta_fn(-1),
                ).pack()

            def _upd_h(d):
                self._hour = (self._hour + d) % 24; self._h_var.set(f"{self._hour:02d}")
            def _upd_m(d):
                self._minute = (self._minute + d) % 60; self._m_var.set(f"{self._minute:02d}")
            def _upd_s(d):
                self._second = (self._second + d) % 60; self._s_var.set(f"{self._second:02d}")

            _spinner(spinners, "HH", self._h_var, _upd_h)
            ctk.CTkLabel(spinners, text=":", font=ctk.CTkFont(size=18, weight="bold"),
                text_color=("gray50", "gray60")).pack(side="left", pady=(14, 0))
            _spinner(spinners, "MM", self._m_var, _upd_m)
            ctk.CTkLabel(spinners, text=":", font=ctk.CTkFont(size=18, weight="bold"),
                text_color=("gray50", "gray60")).pack(side="left", pady=(14, 0))
            _spinner(spinners, "SS", self._s_var, _upd_s)

            # Sync manual typing
            def _sync(var, lo, hi, attr):
                try:
                    setattr(self, attr, max(lo, min(hi, int(var.get()))))
                except ValueError:
                    pass
            self._h_var.trace_add("write", lambda *_: _sync(self._h_var, 0, 23, "_hour"))
            self._m_var.trace_add("write", lambda *_: _sync(self._m_var, 0, 59, "_minute"))
            self._s_var.trace_add("write", lambda *_: _sync(self._s_var, 0, 59, "_second"))

            # Apply / Cancel buttons
            btn_row = ctk.CTkFrame(outer, fg_color="transparent")
            btn_row.pack(fill="x", padx=8, pady=(0, 8))
            ctk.CTkButton(btn_row, text=t("btn.cancel"), width=90, height=30, corner_radius=6,
                fg_color=("gray70", "gray30"), hover_color=("gray60", "gray40"),
                font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
                command=self.destroy,
            ).pack(side="left", expand=True, padx=(0, 4))
            ctk.CTkButton(btn_row, text="✔  Apply", width=90, height=30, corner_radius=6,
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
                self._master_input.winfo_toplevel().unbind(
                    "<Button-1>", self._click_id
                )
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
        ctk.CTkButton(nav, text="◀", width=28, height=26, corner_radius=5,
            fg_color="transparent", hover_color=("gray70", "gray30"),
            command=self._prev_month, font=ctk.CTkFont(size=12),
        ).pack(side="left")
        ctk.CTkLabel(nav,
            text=f"{calendar.month_name[self._month]}  {self._year}",
            font=ctk.CTkFont(family=_FONT_FAMILY, size=13, weight="bold"),
        ).pack(side="left", expand=True)
        ctk.CTkButton(nav, text="▶", width=28, height=26, corner_radius=5,
            fg_color="transparent", hover_color=("gray70", "gray30"),
            command=self._next_month, font=ctk.CTkFont(size=12),
        ).pack(side="right")

        # Day grid
        grid = ctk.CTkFrame(self._cal_frame, fg_color="transparent")
        grid.pack(fill="x", pady=(4, 0))
        for col in range(7):
            grid.columnconfigure(col, minsize=cell)
        for col, d in enumerate(self._DAYS):
            ctk.CTkLabel(grid, text=d, width=cell,
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
                    bg = ("#1f6aa5", "#1f6aa5") if selected else (
                        ("gray80", "gray25") if is_today else "transparent"
                    )
                    tc = "white" if selected else (
                        ("#1f6aa5", "#4ba3e3") if is_today else None
                    )
                    hover = ("#2979b5", "#2979b5") if selected else (
                        ("gray70", "gray35") if is_today else ("gray75", "gray30")
                    )
                    ctk.CTkButton(
                        grid, text=str(day), width=cell, height=30,
                        corner_radius=6,
                        font=ctk.CTkFont(family=_FONT_FAMILY, size=12,
                                         weight="bold" if is_today else "normal"),
                        fg_color=bg, hover_color=hover, text_color=tc,
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
            day, self._month, self._year,
            self._hour, self._minute, self._second,
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
            self, now.year, now.month,
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
        **kwargs,
    ) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self.columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self,
            text=label,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=13),
            width=130,
            anchor="w",
        ).grid(row=0, column=0, padx=(0, 8), sticky="w")

        self.var = tk.StringVar(value=default)
        self.entry = ctk.CTkEntry(
            self,
            textvariable=self.var,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
        )
        self.entry.grid(row=0, column=1, sticky="ew")

        ctk.CTkButton(
            self,
            text=t("btn.browse"),
            width=80,
            command=browse_command,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
        ).grid(row=0, column=2, padx=(8, 0))

    def get(self) -> str:
        return self.var.get()

    def set(self, value: str) -> None:
        self.var.set(value)


# ── Progress Dashboard ───────────────────────────────────────────────
class ProgressDashboard(ctk.CTkFrame):
    """Modern visual progress dashboard replacing raw log output.

    Provides phase indicator, progress bar, stat badges,
    per-item status cards, and a collapsible raw log.
    """

    _SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    _CARD_BG = {
        "success": ("#d7f5dd", "#17301a"),
        "error":   ("#fdd", "#301717"),
        "skipped": ("#fff4d6", "#302a17"),
    }
    _CARD_ICON = {
        "success": "✅", "error": "❌", "skipped": "⏭", "pending": "⏳",
    }
    _BADGE_FG = {
        "success": ("#2e7d32", "#66bb6a"),
        "error":   ("#c62828", "#ef5350"),
        "skipped": ("#e65100", "#ffb74d"),
        "pending": ("#455a64", "#90a4ae"),
    }

    def __init__(self, master, cancel_command=None, **kwargs) -> None:
        self.cancel_command = cancel_command
        super().__init__(master, fg_color="transparent", **kwargs)
        self._total = 0
        self._done = 0
        self._success_count = 0
        self._error_count = 0
        self._skipped_count = 0
        self._running = False
        self._spinner_idx = 0
        self._spinner_job = None
        self._cancelled = False
        
        self._idle_idx = 0
        self._idle_job = None
        
        try:
            from PIL import Image
            self._empty_img = ctk.CTkImage(light_image=Image.new("RGBA", (1, 1), (0,0,0,0)), size=(1, 1))
            self._hourglass_imgs = [
                ctk.CTkImage(
                    light_image=Image.open(get_asset_path(f"assets/icons/hourglass/hourglass-{p}_light.png")),
                    dark_image=Image.open(get_asset_path(f"assets/icons/hourglass/hourglass-{p}_dark.png")),
                    size=(20, 20)
                ) for p in ["high", "medium", "low"]
            ]
        except Exception as e:
            import logging
            logging.error(f"Could not load hourglass images: {e}")
            self._hourglass_imgs = []
            self._empty_img = None

        self._build_ui()
        if self._hourglass_imgs:
            self._tick_idle()

    # ── UI construction ──────────────────────────────────────────
    def _build_ui(self) -> None:
        # Phase indicator
        phase_frame = ctk.CTkFrame(self, corner_radius=10)
        phase_frame.pack(fill="x", pady=(0, 6))
        phase_inner = ctk.CTkFrame(phase_frame, fg_color="transparent")
        phase_inner.pack(fill="x", padx=12, pady=8)

        # Using grid for precise alignment: [Emoji (30px)] [Centered Text (Weight 1)] [Symmetry Spacer (30px)]
        phase_inner.grid_columnconfigure(0, weight=0)
        phase_inner.grid_columnconfigure(1, weight=1)
        phase_inner.grid_columnconfigure(2, weight=0)

        self._spinner_label = ctk.CTkLabel(
            phase_inner, text="", width=30,
            font=ctk.CTkFont(size=14),
        )
        self._spinner_label.grid(row=0, column=0, sticky="w")

        self._phase_label = ctk.CTkLabel(
            phase_inner,
            text=t("dash.waiting"),
            font=ctk.CTkFont(family=_FONT_FAMILY, size=13, weight="bold"),
            text_color=("gray40", "gray60"),
            image=self._hourglass_imgs[0] if getattr(self, "_hourglass_imgs", []) else None,
            compound="left",
            padx=8
        )
        self._phase_label.grid(row=0, column=1, sticky="nsew")

        # Hidden spacer to balance the emoji on the left for perfect text centering
        self._symmetry_spacer = ctk.CTkLabel(phase_inner, text="", width=30)
        self._symmetry_spacer.grid(row=0, column=2, sticky="e")

        # Progress bar
        prog_frame = ctk.CTkFrame(self, fg_color="transparent")
        prog_frame.pack(fill="x", pady=(0, 6))
        self._progress_bar = ctk.CTkProgressBar(
            prog_frame, height=10, corner_radius=5,
            progress_color=("#1f6aa5", "#1f6aa5"),
        )
        self._progress_bar.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self._progress_bar.set(0)

        if getattr(self, "cancel_command", None):
            try:
                from PIL import Image
                self.cancel_btn = ctk.CTkButton(
                    prog_frame,
                    image=ctk.CTkImage(
                        light_image=Image.open(get_asset_path("assets/icons/cancel_light.png")),
                        dark_image=Image.open(get_asset_path("assets/icons/cancel_dark.png"))
                    ),
                    text="",
                    height=24, width=24,
                    corner_radius=4, fg_color="transparent", hover_color="#b71c1c",
                    state="disabled",
                    command=self.cancel_command
                )
                self.cancel_btn.pack(side="right", padx=(8, 0))
            except Exception as e:
                import logging
                logging.error(f"Could not load cancel icons for progress board: {e}")

        self._progress_label = ctk.CTkLabel(
            prog_frame, text="0 / 0",
            font=ctk.CTkFont(family=_FONT_FAMILY, size=11), width=50,
        )
        self._progress_label.pack(side="right")

        # Stats badges
        stats_frame = ctk.CTkFrame(self, fg_color="transparent")
        stats_frame.pack(fill="x", pady=(0, 6))
        self._stat_labels: dict[str, ctk.CTkLabel] = {}
        for key, icon, text in [
            ("success", "✅", t("dash.success")), ("error", "❌", t("dash.errors")),
            ("skipped", "⏭", t("dash.skipped")), ("pending", "⏳", t("dash.pending")),
        ]:
            badge = ctk.CTkFrame(stats_frame, corner_radius=8, fg_color=("gray88", "gray20"))
            badge.pack(side="left", expand=True, fill="x", padx=2)
            inner = ctk.CTkFrame(badge, fg_color="transparent")
            inner.pack(padx=8, pady=4)
            ctk.CTkLabel(inner, text=icon, width=16, font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 3))
            lbl = ctk.CTkLabel(
                inner, text="0",
                font=ctk.CTkFont(family=_FONT_FAMILY, size=12, weight="bold"),
                text_color=self._BADGE_FG[key],
            )
            lbl.pack(side="left", padx=(0, 3))
            ctk.CTkLabel(inner, text=text, font=ctk.CTkFont(family=_FONT_FAMILY, size=10), text_color=("gray50", "gray55")).pack(side="left")
            self._stat_labels[key] = lbl

        # Item cards
        self._cards_frame = ctk.CTkScrollableFrame(self, corner_radius=8, fg_color=("gray92", "gray14"))
        self._cards_frame.pack(fill="both", expand=True, pady=(0, 6))
        self._empty_label = ctk.CTkLabel(
            self._cards_frame, text=t("dash.no_items"),
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12), text_color=("gray50", "gray50"),
        )
        self._empty_label.pack(pady=20)

    # ── Public API (thread-safe via .after) ───────────────────────
    def reset(self, total: int) -> None:
        def _do():
            self._total = total
            self._done = self._success_count = self._error_count = self._skipped_count = 0
            self._cancelled = False
            self._running = True
            for w in self._cards_frame.winfo_children():
                w.destroy()
            if total == 0:
                self._empty_label = ctk.CTkLabel(
                    self._cards_frame, text=t("dash.no_items_found"),
                    font=ctk.CTkFont(family=_FONT_FAMILY, size=12), text_color=("gray50", "gray50"),
                )
                self._empty_label.pack(pady=20)
            self._progress_bar.set(0)
            self._progress_label.configure(text=f"0 / {total}")
            for k in self._stat_labels:
                self._stat_labels[k].configure(text="0")
            self._stat_labels["pending"].configure(text=str(total))
            self._phase_label.configure(text=t("dash.starting"), text_color=("#1565c0", "#64b5f6"), image=self._empty_img)
            self._start_spinner()
        self.after(0, _do)

    def set_phase(self, text: str) -> None:
        self.after(0, lambda: self._phase_label.configure(text=text, text_color=("#1565c0", "#64b5f6")))

    def mark_success(self, name: str, detail: str = "") -> None:
        def _do():
            self._success_count += 1
            self._done += 1
            self._add_card(name, "success", detail or t("dash.processed"))
            self._refresh()
        self.after(0, _do)

    def mark_error(self, name: str, detail: str) -> None:
        def _do():
            self._error_count += 1
            self._done += 1
            self._add_card(name, "error", detail)
            self._refresh()
        self.after(0, _do)

    def mark_skipped(self, name: str, detail: str = "") -> None:
        def _do():
            self._skipped_count += 1
            self._done += 1
            self._add_card(name, "skipped", detail or t("dash.skipped"))
            self._refresh()
        self.after(0, _do)

    def finish(self) -> None:
        def _do():
            self._running = False
            self._stop_spinner()
            self._phase_label.configure(image=self._empty_img)
            if self._cancelled:
                self._phase_label.configure(text=f"Cancelled", text_color=("#c62828", "#ef5350"))
                self._spinner_label.configure(text="⚠️")
            elif self._error_count > 0:
                self._phase_label.configure(text=f"Completed with {self._error_count} error(s)", text_color=("#c62828", "#ef5350"))
                self._spinner_label.configure(text="⚠️")
            else:
                self._phase_label.configure(text=t("dash.completed_success"), text_color=("#2e7d32", "#66bb6a"))
                self._spinner_label.configure(text="✅")
            self._progress_bar.set(1)
        self.after(0, _do)

    def _tick_idle(self) -> None:
        if self._running:
            return
        if getattr(self, "_hourglass_imgs", []) and self._phase_label.cget("text") == t("dash.waiting"):
            img = self._hourglass_imgs[self._idle_idx % len(self._hourglass_imgs)]
            self._phase_label.configure(image=img)
            self._idle_idx += 1
            self._idle_job = self.after(200, self._tick_idle)
        else:
            self._idle_job = self.after(200, self._tick_idle)

    # ── Internal ──────────────────────────────────────────────────
    def _add_card(self, name: str, status: str, detail: str = "") -> None:
        try:
            if hasattr(self, "_empty_label") and self._empty_label.winfo_exists():
                self._empty_label.destroy()
        except Exception:
            pass
        bg = self._CARD_BG.get(status, ("gray90", "gray17"))
        card = ctk.CTkFrame(self._cards_frame, fg_color=bg, corner_radius=6, height=30)
        card.pack(fill="x", pady=1)
        card.pack_propagate(False)
        ctk.CTkLabel(card, text=self._CARD_ICON.get(status, "⏳"), width=22, font=ctk.CTkFont(size=12)).pack(side="left", padx=(8, 4))
        ctk.CTkLabel(card, text=name, anchor="w", font=ctk.CTkFont(family=_FONT_FAMILY, size=11, weight="bold")).pack(side="left", padx=(0, 8))
        if detail:
            ctk.CTkLabel(card, text=detail, anchor="e", font=ctk.CTkFont(family=_FONT_FAMILY, size=10), text_color=("gray45", "gray55")).pack(side="right", padx=(4, 8), fill="x", expand=True)
        self.after(10, lambda: self._cards_frame._parent_canvas.yview_moveto(1.0))

    def _refresh(self) -> None:
        if self._total > 0:
            pct = self._done / self._total
            self._progress_bar.set(pct)
            self._progress_label.configure(text=f"{self._done} / {self._total}  ({int(pct * 100)}%)")
        pending = max(0, self._total - self._done)
        self._stat_labels["success"].configure(text=str(self._success_count))
        self._stat_labels["error"].configure(text=str(self._error_count))
        self._stat_labels["skipped"].configure(text=str(self._skipped_count))
        self._stat_labels["pending"].configure(text=str(pending))

    def _start_spinner(self) -> None:
        self._spinner_idx = 0
        self._tick_spinner()

    def _stop_spinner(self) -> None:
        if self._spinner_job:
            self.after_cancel(self._spinner_job)
            self._spinner_job = None

    def _tick_spinner(self) -> None:
        if not self._running:
            return
        self._spinner_label.configure(text=self._SPINNER[self._spinner_idx % len(self._SPINNER)])
        self._spinner_idx += 1
        self._spinner_job = self.after(100, self._tick_spinner)


class BlockingOverlay(ctk.CTkFrame):
    """Full-screen overlay with blurred background to block UI during loading."""

    def __init__(self, master, hourglass_imgs, **kwargs) -> None:
        super().__init__(master, fg_color="transparent", corner_radius=0, **kwargs)
        self._hourglass_imgs = [
            ctk.CTkImage(
                light_image=img._light_image,
                dark_image=img._dark_image,
                size=(64, 64)
            ) for img in hourglass_imgs
        ] if hourglass_imgs else []
        self._idx = 0
        self._job = None
        self._bg_photo = None
        self._icon_photos = [] # Store PhotoImages for canvas use

        # Use a Canvas for true transparency over the background image
        self._canvas = tk.Canvas(self, bd=0, highlightthickness=0, bg="black")
        self._canvas.place(x=0, y=0, relwidth=1, relheight=1)

        self._bg_id = None
        self._icon_id = None
        self._text_id = None

    def capture_blur(self) -> None:
        """Take a screenshot, blur it, and set as canvas background."""
        try:
            import pyautogui
            from PIL import ImageFilter, ImageTk, Image as PilImage

            master = self.master
            master.update_idletasks()

            x = master.winfo_rootx()
            y = master.winfo_rooty()
            w = master.winfo_width()
            h = master.winfo_height()

            if w < 2 or h < 2:
                return

            screenshot = pyautogui.screenshot(region=(x, y, w, h))
            blurred = screenshot.filter(ImageFilter.GaussianBlur(radius=14))
            dim = PilImage.new("RGBA", blurred.size, (0, 0, 0, 160)) # slightly darker
            blurred = blurred.convert("RGBA")
            final_bg = PilImage.alpha_composite(blurred, dim).convert("RGB")

            self._bg_photo = ImageTk.PhotoImage(final_bg)
            
            # Clear existing canvas items
            self._canvas.delete("all")
            
            # Draw background
            self._bg_id = self._canvas.create_image(0, 0, image=self._bg_photo, anchor="nw")
            
            # Prepare icon PhotoImages if not done (Canvas needs PhotoImage, not CTkImage)
            if not self._icon_photos and self._hourglass_imgs:
                mode = ctk.get_appearance_mode().lower()
                for img in self._hourglass_imgs:
                    pil_img = img._dark_image if mode == "dark" else img._light_image
                    pil_img = pil_img.resize((64, 64), PilImage.Resampling.LANCZOS)
                    self._icon_photos.append(ImageTk.PhotoImage(pil_img))

            cx, cy = w // 2, h // 2
            
            # Draw Icon
            if self._icon_photos:
                self._icon_id = self._canvas.create_image(cx, cy - 30, image=self._icon_photos[0])
            
            # Draw Text
            self._text_id = self._canvas.create_text(
                cx, cy + 40,
                text=t("msg.cancelling", default="Cancelling..."),
                fill="white",
                font=(_FONT_FAMILY, 13, "normal"),
                justify="center"
            )

        except Exception as e:
            logging.warning(f"BlockingOverlay: canvas setup failed ({e})")
            self._canvas.configure(bg="#1a1a1a")

    def start_animation(self) -> None:
        if not self._icon_photos or self._icon_id is None:
            return
        self._idx = (self._idx + 1) % len(self._icon_photos)
        self._canvas.itemconfig(self._icon_id, image=self._icon_photos[self._idx])
        self._job = self.after(250, self.start_animation)

    def stop_animation(self) -> None:
        if self._job:
            self.after_cancel(self._job)
            self._job = None

class LogWindow(ctk.CTkToplevel):
    def __init__(self, master) -> None:
        super().__init__(master)
        self.title("Application Log")
        self.geometry("600x400")

        self.textbox = ctk.CTkTextbox(
            self, state="disabled", wrap="word",
            font=ctk.CTkFont(family="Consolas", size=11),
            corner_radius=8
        )
        self.textbox.pack(fill="both", expand=True, padx=4, pady=4)
        
        self.protocol("WM_DELETE_WINDOW", self.hide)
        self.withdraw()
    
    def hide(self) -> None:
        self.withdraw()
        
    def show(self) -> None:
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self.focus_force()
        self.after(50, lambda: self.attributes("-topmost", False))

# ── Main application ─────────────────────────────────────────────────
class DSNOApp(ctk.CTk):
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

    # ──────────────────────────────────────────────────────────────
    # Tab: Processor
    # ──────────────────────────────────────────────────────────────

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
        self.start_date = DateInput(date_frame, label=t("proc.start"), prefill_today=True)
        self.start_date.pack(side="left", padx=(0, 20))
        self.end_date = DateInput(date_frame, label=t("proc.end"), prefill_today=True)
        self.end_date.pack(side="left")

        # File pickers
        self.customer_row = FilePickerRow(
            tab,
            label=t("proc.customer_sheet"),
            default=default_customer,
            browse_command=self._browse_customer,
        )
        self.customer_row.pack(fill="x", pady=4)

        self.control_row = FilePickerRow(
            tab,
            label=t("proc.control_sheet"),
            default=default_control,
            browse_command=self._browse_control,
        )
        self.control_row.pack(fill="x", pady=4)

        self.dsno_row = FilePickerRow(
            tab,
            label=t("proc.dsno_directory"),
            default=default_dsno_dir,
            browse_command=self._browse_dsno_dir,
        )
        self.dsno_row.pack(fill="x", pady=4)

        # Status filter
        status_frame = ctk.CTkFrame(tab, fg_color="transparent")
        status_frame.pack(fill="x", pady=(8, 4))
        ctk.CTkLabel(
            status_frame,
            text=t("proc.status"),
            font=ctk.CTkFont(family=_FONT_FAMILY, size=13),
            width=130,
            anchor="w",
        ).pack(side="left")
        self.filter_by_status = ctk.CTkComboBox(
            status_frame,
            values=["All"] + get_status_options(self.control_row.get()),
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
        )
        self.filter_by_status.pack(padx=(0, 4))

        # Run buttons container
        btn_frame = ctk.CTkFrame(tab, fg_color="transparent")
        btn_frame.pack(fill="x", pady=12)

        self.run_btn = ctk.CTkButton(
            btn_frame,
            text=t("proc.start_btn"),
            height=40,
            corner_radius=10,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=14, weight="bold"),
            command=self._start_processing,
        )
        self.run_btn.pack(padx=(0, 4))

        # Progress dashboard
        self.dashboard = ProgressDashboard(
            tab,
            cancel_command=lambda: (self._show_blocking_overlay(), getattr(self, "_processor_cancel_event").set()) if hasattr(self, "_processor_cancel_event") else None
        )
        self.dashboard.pack(fill="both", expand=True, pady=(0, 4))

    # ──────────────────────────────────────────────────────────────
    # Tab: EBS Download
    # ──────────────────────────────────────────────────────────────

    _DL_TAB_CONFIG   = t("tab.configuration")
    _DL_TAB_PROGRESS = t("tab.progress")

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
                form, text=text, anchor="w", width=150,
                font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
            ).grid(row=r, column=0, padx=(6, 8), pady=4, sticky="w")

        def _ent(r, default="", width=None):
            var = tk.StringVar(value=default)
            e = ctk.CTkEntry(form, textvariable=var,
                             font=ctk.CTkFont(family=_FONT_FAMILY, size=12))
            if width:
                e.configure(width=width)
            e.grid(row=r, column=1, sticky="ew", pady=4, padx=(0, 6))
            return var, e

        # Period
        ctk.CTkLabel(form, text=t("dl.section_period"), anchor="w",
            font=ctk.CTkFont(family=_FONT_FAMILY, size=11, weight="bold"),
            text_color=("gray40", "gray55"),
        ).grid(row=row, column=0, columnspan=3, sticky="w", padx=6, pady=(8, 2))
        row += 1
        _lbl(t("dl.start_date"), row)
        self.dl_date_start = DateTimeInput(form)
        self.dl_date_start.grid(row=row, column=1, columnspan=2, sticky="w", pady=4, padx=(0, 6))
        row += 1
        _lbl(t("dl.end_date"), row)
        self.dl_date_end = DateTimeInput(form)
        self.dl_date_end.grid(row=row, column=1, columnspan=2, sticky="w", pady=4, padx=(0, 6))
        row += 1
        _lbl(t("dl.status_filter"), row)
        self.dl_status_filter_var, _e = _ent(row, "")
        add_placeholder(_e, "Processed, Downloaded, <empty>"); row += 1

        # Files
        ctk.CTkLabel(form, text=t("dl.section_files"), anchor="w",
            font=ctk.CTkFont(family=_FONT_FAMILY, size=11, weight="bold"),
            text_color=("gray40", "gray55"),
        ).grid(row=row, column=0, columnspan=3, sticky="w", padx=6, pady=(10, 2))
        row += 1
        _lbl(t("dl.download_dir"), row)
        self.dl_dir_var, _ = _ent(row, str(cfg.download_dir) if cfg else "")
        ctk.CTkButton(form, text=t("btn.browse"), width=70,
            command=self._browse_dl_dir,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=11),
        ).grid(row=row, column=2, padx=(4, 6), pady=4); row += 1
        _lbl(t("proc.customer_sheet"), row)
        self.dl_sheet_var, _ = _ent(row, str(cfg.control_sheet) if cfg else "")
        ctk.CTkButton(form, text=t("btn.browse"), width=70,
            command=self._browse_dl_sheet,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=11),
        ).grid(row=row, column=2, padx=(4, 6), pady=4); row += 1

        # Connection
        ctk.CTkLabel(form, text=t("dl.section_connection"), anchor="w",
            font=ctk.CTkFont(family=_FONT_FAMILY, size=11, weight="bold"),
            text_color=("gray40", "gray55"),
        ).grid(row=row, column=0, columnspan=3, sticky="w", padx=6, pady=(10, 2))
        row += 1
        _lbl(t("dl.ebs_url"), row)
        self.dl_url_var, _ = _ent(row, cfg.ebs_download_url if cfg else ""); row += 1

        # Columns
        ctk.CTkLabel(form, text=t("dl.section_columns"), anchor="w",
            font=ctk.CTkFont(family=_FONT_FAMILY, size=11, weight="bold"),
            text_color=("gray40", "gray55"),
        ).grid(row=row, column=0, columnspan=3, sticky="w", padx=6, pady=(10, 2))
        row += 1
        _lbl(t("dl.dsno_column"), row)
        self.dl_dsno_col_var, _ = _ent(row, cfg.ebs_dsno_col if cfg else "ARGUMENT2"); row += 1
        _lbl(t("dl.date_column"), row)
        self.dl_date_col_var, _ = _ent(row, cfg.ebs_date_col if cfg else "CREATION_DATE"); row += 1
        _lbl(t("dl.status_column"), row)
        self.dl_status_col_var, _ = _ent(row, cfg.ebs_status_col if cfg else "STATUS"); row += 1

        # Folders
        ctk.CTkLabel(form, text=t("dl.section_folders"), anchor="w",
            font=ctk.CTkFont(family=_FONT_FAMILY, size=11, weight="bold"),
            text_color=("gray40", "gray55"),
        ).grid(row=row, column=0, columnspan=3, sticky="w", padx=6, pady=(10, 2))
        row += 1
        indices_str = ",".join(str(x) for x in (cfg.ebs_folder_indices if cfg else [92, 95, 101]))
        _lbl(t("dl.folder_indices"), row)
        self.dl_folders_var, _ = _ent(row, indices_str); row += 1

        # Start button
        self.dl_start_btn = ctk.CTkButton(
            tab,
            text=t("dl.start_btn"),
            height=40, corner_radius=10,
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
            cancel_command=lambda: (self._show_blocking_overlay(), getattr(self,("_dl_cancel_event")).set()) if hasattr(self, "_dl_cancel_event") else None
        )
        self.dl_dashboard.pack(fill="both", expand=True, pady=4)

    # ──────────────────────────────────────────────────────────────
    # Tab: EBS Upload
    # ──────────────────────────────────────────────────────────────

    _UL_TAB_CONFIG   = t("tab.configuration")
    _UL_TAB_PROGRESS = t("tab.progress")

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

        def _ent(r, default=""):
            var = tk.StringVar(value=default)
            ctk.CTkEntry(form, textvariable=var,
                font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
            ).grid(row=r, column=1, sticky="ew", pady=5, padx=(0, 6))
            return var

        # Connection
        ctk.CTkLabel(form, text=t("dl.section_connection"), anchor="w",
            font=ctk.CTkFont(family=_FONT_FAMILY, size=11, weight="bold"),
            text_color=("gray40", "gray55"),
        ).grid(row=row, column=0, columnspan=3, sticky="w", padx=6, pady=(8, 2))
        row += 1
        _lbl(t("dl.ebs_url"), row)
        self.ul_url_var = _ent(row, cfg.ebs_upload_url if cfg else ""); row += 1

        # Files
        ctk.CTkLabel(form, text=t("dl.section_files"), anchor="w",
            font=ctk.CTkFont(family=_FONT_FAMILY, size=11, weight="bold"),
            text_color=("gray40", "gray55"),
        ).grid(row=row, column=0, columnspan=3, sticky="w", padx=6, pady=(10, 2))
        row += 1
        _lbl(t("ul.upload_dir"), row)
        self.ul_dir_var = _ent(row, str(cfg.upload_dir) if cfg else "")
        ctk.CTkButton(form, text=t("btn.browse"), width=70,
            command=self._browse_ul_dir,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=11),
        ).grid(row=row, column=2, padx=(4, 6), pady=5); row += 1

        # Folders
        ctk.CTkLabel(form, text=t("dl.section_folders"), anchor="w",
            font=ctk.CTkFont(family=_FONT_FAMILY, size=11, weight="bold"),
            text_color=("gray40", "gray55"),
        ).grid(row=row, column=0, columnspan=3, sticky="w", padx=6, pady=(10, 2))
        row += 1
        _lbl(t("ul.folder_index"), row)
        self.ul_folder_var = _ent(row, str(cfg.ebs_upload_folder_index) if cfg else "92"); row += 1

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

    # ──────────────────────────────────────────────────────────────
    # Browse dialogs — Processor
    # ──────────────────────────────────────────────────────────────

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
            result = process_dsno(
                date_range=date_range,
                customer_sheet=self.customer_row.get(),
                control_sheet=self.control_row.get(),
                dsno_dir=self.dsno_row.get(),
                progress_callback=self._make_progress_callback(),
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
            self.run_btn.configure(state="normal")
            self.dashboard.cancel_btn.configure(state="disabled")

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
            self.dl_start_btn.configure(state="normal")
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
            self.ul_start_btn.configure(state="normal")
            self.ul_dashboard.cancel_btn.configure(state="disabled")

    # ──────────────────────────────────────────────────────────────
    # Settings
    # ──────────────────────────────────────────────────────────────

    def _open_settings(self) -> None:
        SettingsWindow(self, on_save=self._reload_config)

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


# ══════════════════════════════════════════════════════════════════════
# Settings Window — Tabbed interface
# ══════════════════════════════════════════════════════════════════════

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
            t("tab.processor"),
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
            image=ctk.CTkImage(light_image=Image.open(get_asset_path("assets/icons/cancel_light.png")), dark_image=Image.open(get_asset_path("assets/icons/cancel_dark.png"))),
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
            image=ctk.CTkImage(light_image=Image.open(get_asset_path("assets/icons/save_light.png")), dark_image=Image.open(get_asset_path("assets/icons/save_dark.png"))),
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

        self._tab_hint(
            form, t("settings.general.hint")
        )

        row = 1
        ctk.CTkLabel(
            form, text=t("settings.general.language"), anchor="w", width=150,
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
            row+1,
        )

    def _build_tab_paths(self, cfg) -> None:
        tab = self._tabview.tab(t("settings.tab.paths"))
        form = self._make_form(tab)

        self._tab_hint(
            form, t("settings.paths.hint")
        )

        self._add_path_field(
            form, 1, t("proc.dsno_directory"), "dsno_directory",
            str(cfg.paths.dsno_directory) if cfg else "",
            mode="dir",
            hint=t("settings.paths.dsno_directory_hint"),
        )
        self._add_path_field(
            form, 3, t("proc.control_sheet"), "control_sheet",
            str(cfg.paths.control_sheet) if cfg else "",
            mode="file",
            filetypes=[("Excel", "*.xlsx *.xls")],
            hint=t("settings.paths.control_sheet_hint"),
        )
        self._add_path_field(
            form, 5, t("proc.customer_sheet"), "customer_sheet",
            str(cfg.paths.customer_sheet) if cfg else "",
            mode="file",
            filetypes=[("Excel", "*.xlsx *.xls")],
            hint=t("settings.paths.customer_sheet_hint"),
        )
        self._add_path_field(
            form, 7, t("settings.paths.customer_pre_path"), "customer_sheet_pre_path",
            str(cfg.paths.customer_sheet_pre_path) if cfg else "",
            mode="dir",
            hint=t("settings.paths.customer_pre_path_hint"),
        )

    def _build_tab_processor(self, cfg) -> None:
        tab = self._tabview.tab(t("tab.processor"))
        form = self._make_form(tab)

        self._tab_hint(
            form,
            t("settings.processor.hint"),
        )


    def _build_tab_ebs(self, cfg) -> None:
        tab = self._tabview.tab(t("settings.tab.ebs"))
        form = self._make_form(tab)

        self._tab_hint(
            form, t("settings.ebs.hint")
        )

        self._add_text_field(
            form, 1, t("settings.ebs.download_url"), "ebs_download_url",
            cfg.ebs.download_url if cfg else "",
            hint=t("settings.ebs.download_url_hint"),
        )
        self._add_text_field(
            form, 3, t("settings.ebs.upload_url"), "ebs_upload_url",
            cfg.ebs.upload_url if cfg else "",
            hint=t("settings.ebs.upload_url_hint"),
        )
        self._add_path_field(
            form, 5, t("dl.download_dir"), "download_dir",
            str(cfg.ebs.download_dir) if cfg else "",
            mode="dir",
            hint=t("settings.ebs.download_dir_hint"),
        )
        self._add_path_field(
            form, 7, t("ul.upload_dir"), "upload_dir",
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
            form, text=t("settings.ebs.headless"), anchor="w", width=150,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
        ).grid(row=row, column=0, padx=(0, 8), pady=3, sticky="w")

        self._headless_var = tk.BooleanVar(
            value=cfg.ebs.headless if cfg else False
        )
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

        self._tab_hint(
            form,
            t("settings.columns.hint"),
        )

        self._add_text_field(
            form, 1, t("dl.dsno_column"), "ebs_col_dsno",
            cfg.ebs.columns.dsno if cfg else "ARGUMENT2",
            hint=t("settings.columns.dsno_hint"),
        )
        self._add_text_field(
            form, 3, t("dl.date_column"), "ebs_col_date",
            cfg.ebs.columns.date if cfg else "CREATION_DATE",
            hint=t("settings.columns.date_hint"),
        )
        self._add_text_field(
            form, 5, t("dl.status_column"), "ebs_col_status",
            cfg.ebs.columns.status if cfg else "STATUS",
            hint=t("settings.columns.status_hint"),
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
            form, 1, t("settings.folders.download_indices"), "ebs_folders_download",
            indices,
            hint=t("settings.folders.download_indices_hint"),
        )
        self._add_text_field(
            form, 3, t("settings.folders.upload_index"), "ebs_folder_upload",
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
            form, 1, t("settings.credentials.email"), "cred_email",
            cfg.credentials.email if cfg else "",
            hint=t("settings.credentials.email_hint"),
        )

        # Password with toggle
        row = 3
        self._hint_label(form, t("settings.credentials.password_hint"), row)
        row += 1

        ctk.CTkLabel(
            form, text=t("settings.credentials.password"), anchor="w", width=150,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
        ).grid(row=row, column=0, padx=(0, 8), pady=3, sticky="w")

        var = tk.StringVar(
            value=cfg.credentials.password if cfg else ""
        )
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
        self, parent, row: int, label: str, key: str,
        default: str = "", show: str | None = None,
        hint: str | None = None,
    ) -> int:
        if hint:
            self._hint_label(parent, hint, row)
            row += 1

        ctk.CTkLabel(
            parent, text=label, anchor="w", width=150,
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
            row=row, column=1, sticky="ew", pady=3, columnspan=2,
        )

        self._vars[key] = var
        return row + 1

    def _add_path_field(
        self, parent, row: int, label: str, key: str,
        default: str = "", mode: str = "dir", filetypes=None,
        hint: str | None = None,
    ) -> int:
        if hint:
            self._hint_label(parent, hint, row)
            row += 1

        ctk.CTkLabel(
            parent, text=label, anchor="w", width=150,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
        ).grid(row=row, column=0, padx=(0, 8), pady=3, sticky="w")

        var = tk.StringVar(value=default)
        ctk.CTkEntry(
            parent, textvariable=var,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
        ).grid(row=row, column=1, sticky="ew", pady=3)

        # Path validity indicator + browse button frame
        btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        btn_frame.grid(row=row, column=2, padx=(4, 0), pady=3)

        # Validity indicator
        indicator = ctk.CTkLabel(
            btn_frame, text="", width=20,
            font=ctk.CTkFont(size=13),
        )
        indicator.pack(side="left", padx=(0, 2))
        self._path_indicators[key] = indicator

        def _browse():
            if mode == "dir":
                result = filedialog.askdirectory(
                    title=f"Select {label.rstrip(':')}"
                )
            else:
                result = filedialog.askopenfilename(
                    title=f"Select {label.rstrip(':')}",
                    filetypes=filetypes or [],
                )
            if result:
                var.set(result)
                self._update_indicator(key, result, mode)

        ctk.CTkButton(
            btn_frame, text=t("btn.browse"), width=70, command=_browse,
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


        selected_display = getattr(self, "language_var", tk.StringVar(value="English")).get()
        selected_code = "en"
        for code, disp in SUPPORTED_LANGUAGES.items():
            if disp == selected_display:
                selected_code = code
                break

        new_config = AppConfig(
            general=GeneralConfig(language=selected_code),
            paths=PathsConfig(
                dsno_directory=_Path(self._vars["dsno_directory"].get()),
                control_sheet=_Path(self._vars["control_sheet"].get()),
                customer_sheet=_Path(self._vars["customer_sheet"].get()),
                customer_sheet_pre_path=_Path(
                    self._vars["customer_sheet_pre_path"].get()
                ),
            ),
            control_sheet_cols=ControlSheetColsConfig(
                invoice=self._vars["ebs_col_invoice"].get(),
                dsno=self._vars["ebs_col_dsno"].get(),
                date=self._vars["ebs_col_date"].get(),
                status=self._vars["ebs_col_status"].get(),
            ),
            customer_sheet_cols=CustomerSheetColsConfig(
                invoice=self._vars.get("cust_col_invoice", tk.StringVar(value="Invoice")).get(),
                booking=self._vars.get("cust_col_booking", tk.StringVar(value="Booking/HAWB")).get(),
                container=self._vars.get("cust_col_container", tk.StringVar(value="Container")).get(),
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



# ──────────────────────────────────────────────────────────────
# Language Popup Menu
# ──────────────────────────────────────────────────────────────

class LanguageMenu(ctk.CTkToplevel):
    """Small popup window for language selection."""
    def __init__(self, master, lang_btn, on_select) -> None:
        super().__init__(master)
        self.overrideredirect(True) # Remove title bar
        self.attributes("-topmost", True)
        self.on_select = on_select

        # Position below the button
        self.update_idletasks() # Ensure dimensions are calculated
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
            border_color=("gray80", "gray20")
        )
        inner.pack(padx=2, pady=2, fill="both", expand=False)

        from dsno_processor.i18n import SUPPORTED_LANGUAGES, get_language
        current_lang = get_language()

        try:
            from PIL import Image
            check_icon = ctk.CTkImage(
                light_image=Image.open(get_asset_path("assets/icons/check_light.png")),
                dark_image=Image.open(get_asset_path("assets/icons/check_dark.png")),
                size=(14, 14)
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
                command=lambda c=code: self._select(c)
            )
            btn.pack(fill="x", padx=margin_x, pady=(p_top, p_bottom))

        # Dynamic height calculation
        total_h = (len(SUPPORTED_LANGUAGES) * 28) + (2 * margin_y) + ((len(SUPPORTED_LANGUAGES) - 1) * spacing) + 10
        self.geometry(f"140x{total_h}+{btn_x - 100}+{btn_y + btn_h + 5}")

        # Close on focus out
        self.bind("<FocusOut>", lambda e: self.destroy())
        self.focus_set()

    def _select(self, code: str) -> None:
        self.on_select(code)
        self.destroy()

def start_gui() -> None:
    """Launch the DSNO Processor GUI."""
    app = DSNOApp()
    app.mainloop()


if __name__ == "__main__":
    start_gui()