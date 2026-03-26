"""DSNO Processor GUI — CustomTkinter interface for batch DSNO processing."""

import calendar
import logging
import os
import re
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox

import customtkinter as ctk

from dsno_processor import process_dsno
from dsno_processor.config import load_config
from dsno_processor.exceptions import ConfigurationError

# ── Appearance ────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

_FONT_FAMILY = "Segoe UI"
_DATE_PATTERN = re.compile(r"^\d{2}/\d{2}/\d{4}$")


# ── Logging handler ──────────────────────────────────────────────────
class TextboxHandler(logging.Handler):
    """Route log records to a CTkTextbox widget."""

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

        self.textbox.after(0, _append)


# ── Calendar popup ───────────────────────────────────────────────────
class _CalendarPopup(ctk.CTkToplevel):
    """A dark-themed month calendar that floats below a DateInput."""

    _DAYS_PT = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
    _CELL = 38  # px per column

    def __init__(self, master: "DateInput", year: int, month: int) -> None:
        super().__init__(master)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self._master_input = master
        self._year = year
        self._month = month

        self._frame = ctk.CTkFrame(self, corner_radius=10)
        self._frame.pack(padx=2, pady=2)

        self._build()
        self._position()

        # Close when user clicks anywhere OUTSIDE this popup
        self._click_id = self._master_input.winfo_toplevel().bind(
            "<Button-1>", self._on_root_click, add="+"
        )

    def destroy(self) -> None:
        try:
            self._master_input.winfo_toplevel().unbind(
                "<Button-1>", self._click_id
            )
        except Exception:
            pass
        self._master_input._popup = None
        super().destroy()

    def _on_root_click(self, event) -> None:
        """Destroy popup if click lands outside it."""
        try:
            w = event.widget.winfo_containing(event.x_root, event.y_root)
            # Walk up the widget tree; if it's inside us, keep open
            while w is not None:
                if w is self or w is self._frame:
                    return
                w = w.master
        except Exception:
            pass
        self.destroy()

    # ── Layout ────────────────────────────────────────────────────
    def _build(self) -> None:
        for w in self._frame.winfo_children():
            w.destroy()

        cell = self._CELL

        # Navigation row
        nav = ctk.CTkFrame(self._frame, fg_color="transparent")
        nav.pack(fill="x", padx=6, pady=(8, 4))

        ctk.CTkButton(
            nav, text="◀", width=30, fg_color="transparent",
            hover_color=("gray75", "gray30"), command=self._prev_month,
        ).pack(side="left")

        ctk.CTkLabel(
            nav,
            text=f"{calendar.month_name[self._month]}  {self._year}",
            font=ctk.CTkFont(family=_FONT_FAMILY, size=13, weight="bold"),
        ).pack(side="left", expand=True)

        ctk.CTkButton(
            nav, text="▶", width=30, fg_color="transparent",
            hover_color=("gray75", "gray30"), command=self._next_month,
        ).pack(side="right")

        # Day grid container (using grid for guaranteed 7 columns)
        grid = ctk.CTkFrame(self._frame, fg_color="transparent")
        grid.pack(padx=6, pady=(2, 8))

        for col in range(7):
            grid.columnconfigure(col, minsize=cell)

        # Day-of-week headers
        for col, d in enumerate(self._DAYS_PT):
            ctk.CTkLabel(
                grid, text=d, width=cell,
                font=ctk.CTkFont(family=_FONT_FAMILY, size=11),
                text_color="gray55",
            ).grid(row=0, column=col, padx=1, pady=(0, 2))

        # Day buttons
        cal_obj = calendar.Calendar(firstweekday=0)
        weeks = cal_obj.monthdayscalendar(self._year, self._month)
        today = datetime.now()

        for row_i, week in enumerate(weeks, start=1):
            for col, day in enumerate(week):
                if day == 0:
                    ctk.CTkLabel(grid, text="", width=cell).grid(
                        row=row_i, column=col, padx=1, pady=1,
                    )
                else:
                    is_today = (
                        day == today.day
                        and self._month == today.month
                        and self._year == today.year
                    )
                    ctk.CTkButton(
                        grid,
                        text=str(day),
                        width=cell,
                        height=30,
                        corner_radius=6,
                        fg_color=("#3a7ebf", "#1f6aa5") if is_today else "transparent",
                        hover_color=("gray75", "gray30"),
                        text_color="white" if is_today else None,
                        font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
                        command=lambda d=day: self._pick(d),
                    ).grid(row=row_i, column=col, padx=1, pady=1)

    def _position(self) -> None:
        self.update_idletasks()
        entry = self._master_input.entry
        x = entry.winfo_rootx()
        y = entry.winfo_rooty() + entry.winfo_height() + 4
        self.geometry(f"+{x}+{y}")

    # ── Actions ───────────────────────────────────────────────────
    def _prev_month(self) -> None:
        if self._month == 1:
            self._month, self._year = 12, self._year - 1
        else:
            self._month -= 1
        self._build()

    def _next_month(self) -> None:
        if self._month == 12:
            self._month, self._year = 1, self._year + 1
        else:
            self._month += 1
        self._build()

    def _pick(self, day: int) -> None:
        self._master_input._set_date(day, self._month, self._year)
        self.destroy()


# ── Validated date entry ─────────────────────────────────────────────
class DateInput(ctk.CTkFrame):
    """A labelled date-entry field with DD/MM/YYYY validation and calendar popup."""

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        label: str = "Date:",
        **kwargs,
    ) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self._popup: _CalendarPopup | None = None

        ctk.CTkLabel(
            self,
            text=label,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=13),
        ).pack(side="left", padx=(0, 6))

        self.entry = ctk.CTkEntry(
            self,
            width=120,
            placeholder_text="DD/MM/YYYY",
            font=ctk.CTkFont(family=_FONT_FAMILY, size=13),
        )
        self.entry.pack(side="left")

        cal_btn = ctk.CTkButton(
            self,
            text="📅",
            width=32,
            height=28,
            corner_radius=6,
            fg_color="transparent",
            hover_color=("gray75", "gray30"),
            command=self._toggle_calendar,
            font=ctk.CTkFont(size=15),
        )
        cal_btn.pack(side="left", padx=(4, 0))

        # Pre-fill with today
        today = datetime.now().strftime("%d/%m/%Y")
        self.entry.insert(0, today)

        # Open calendar on entry click too
        self.entry.bind("<Button-1>", lambda _: self.after(50, self._toggle_calendar))

        # Validate on focus-out
        self.entry.bind("<FocusOut>", self._validate)

    # ── Public API ────────────────────────────────────────────────
    def get(self) -> str:
        return self.entry.get().strip()

    # ── Internal ──────────────────────────────────────────────────
    def _set_date(self, day: int, month: int, year: int) -> None:
        self.entry.delete(0, "end")
        self.entry.insert(0, f"{day:02d}/{month:02d}/{year}")
        self.entry.configure(
            border_color=ctk.ThemeManager.theme["CTkEntry"]["border_color"]
        )

    def _toggle_calendar(self) -> None:
        # Close existing popup
        if self._popup is not None and self._popup.winfo_exists():
            self._popup.destroy()
            self._popup = None
            return

        # Determine starting month from current value
        now = datetime.now()
        value = self.get()
        if _DATE_PATTERN.match(value):
            try:
                dt = datetime.strptime(value, "%d/%m/%Y")
                now = dt
            except ValueError:
                pass

        self._popup = _CalendarPopup(self, now.year, now.month)

    def _validate(self, _event=None) -> None:
        value = self.get()
        if not value:
            return
        if not _DATE_PATTERN.match(value):
            self.entry.configure(border_color="#e74c3c")
            return
        try:
            datetime.strptime(value, "%d/%m/%Y")
            self.entry.configure(border_color=ctk.ThemeManager.theme["CTkEntry"]["border_color"])
        except ValueError:
            self.entry.configure(border_color="#e74c3c")


# ── File picker row ──────────────────────────────────────────────────
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
            text="Browse",
            width=80,
            command=browse_command,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
        ).grid(row=0, column=2, padx=(8, 0))

    def get(self) -> str:
        return self.var.get()

    def set(self, value: str) -> None:
        self.var.set(value)


# ── Main application ─────────────────────────────────────────────────
class DSNOApp(ctk.CTk):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        self.title("DSNO Processor")
        self.geometry("780x600")
        self.minsize(640, 500)

        # ── Load config ──────────────────────────────────────────
        try:
            app_config = load_config()
        except ConfigurationError:
            app_config = None

        default_customer = str(app_config.customer_sheet) if app_config else ""
        default_control = str(app_config.control_sheet) if app_config else ""
        default_dsno_dir = str(app_config.dsno_directory) if app_config else ""
        self._customer_pre_path = (
            str(app_config.customer_sheet_pre_path) if app_config else ""
        )

        # ── Build UI ─────────────────────────────────────────────
        self._create_widgets(default_customer, default_control, default_dsno_dir)
        self._setup_logging()

    # ──────────────────────────────────────────────────────────────
    # Setup
    # ──────────────────────────────────────────────────────────────

    def _setup_logging(self) -> None:
        handler = TextboxHandler(self.log_box)
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)

    def _create_widgets(
        self,
        default_customer: str,
        default_control: str,
        default_dsno_dir: str,
    ) -> None:
        pad = 16

        # ── Header ───────────────────────────────────────────────
        header = ctk.CTkFrame(self, corner_radius=12)
        header.pack(fill="x", padx=pad, pady=(pad, 8))

        ctk.CTkLabel(
            header,
            text="⚙  DSNO Processor",
            font=ctk.CTkFont(family=_FONT_FAMILY, size=22, weight="bold"),
        ).pack(pady=(14, 2))
        ctk.CTkLabel(
            header,
            text="Process and edit DSNO files according to ASN spreadsheets.",
            font=ctk.CTkFont(family=_FONT_FAMILY, size=13),
            text_color="gray60",
        ).pack(pady=(0, 14))

        # ── Date range ───────────────────────────────────────────
        date_frame = ctk.CTkFrame(self, fg_color="transparent")
        date_frame.pack(fill="x", padx=pad, pady=4)

        ctk.CTkLabel(
            date_frame,
            text="Date Range:",
            font=ctk.CTkFont(family=_FONT_FAMILY, size=13),
            width=130,
            anchor="w",
        ).pack(side="left")

        self.start_date = DateInput(date_frame, label="Start:")
        self.start_date.pack(side="left", padx=(0, 20))

        self.end_date = DateInput(date_frame, label="End:")
        self.end_date.pack(side="left")

        # ── File pickers ─────────────────────────────────────────
        self.customer_row = FilePickerRow(
            self,
            label="Customer Sheet:",
            default=default_customer,
            browse_command=self._browse_customer,
        )
        self.customer_row.pack(fill="x", padx=pad, pady=4)

        self.control_row = FilePickerRow(
            self,
            label="Control Sheet:",
            default=default_control,
            browse_command=self._browse_control,
        )
        self.control_row.pack(fill="x", padx=pad, pady=4)

        self.dsno_row = FilePickerRow(
            self,
            label="DSNO Directory:",
            default=default_dsno_dir,
            browse_command=self._browse_dsno_dir,
        )
        self.dsno_row.pack(fill="x", padx=pad, pady=4)

        # ── Run button ───────────────────────────────────────────
        self.run_btn = ctk.CTkButton(
            self,
            text="▶  Start Processing",
            height=40,
            corner_radius=10,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=14, weight="bold"),
            command=self._start_processing,
        )
        self.run_btn.pack(pady=14)

        # ── Log output ───────────────────────────────────────────
        ctk.CTkLabel(
            self,
            text="Process Output Logs:",
            font=ctk.CTkFont(family=_FONT_FAMILY, size=13),
            anchor="w",
        ).pack(fill="x", padx=pad)

        self.log_box = ctk.CTkTextbox(
            self,
            state="disabled",
            wrap="word",
            font=ctk.CTkFont(family="Consolas", size=12),
            corner_radius=8,
        )
        self.log_box.pack(fill="both", expand=True, padx=pad, pady=(4, pad))

    # ──────────────────────────────────────────────────────────────
    # Browse dialogs
    # ──────────────────────────────────────────────────────────────

    def _browse_customer(self) -> None:
        initial = (
            self._customer_pre_path
            if os.path.exists(self._customer_pre_path)
            else None
        )
        path = filedialog.askopenfilename(
            title="Select Customer Sheet",
            initialdir=initial,
            filetypes=[("Excel Files", "*.xlsx *.xls")],
        )
        if path:
            self.customer_row.set(path)

    def _browse_control(self) -> None:
        current_dir = os.path.dirname(self.control_row.get())
        initial = current_dir if os.path.exists(current_dir) else None
        path = filedialog.askopenfilename(
            title="Select Control Sheet",
            initialdir=initial,
            filetypes=[("Excel Files", "*.xlsx *.xls")],
        )
        if path:
            self.control_row.set(path)

    def _browse_dsno_dir(self) -> None:
        current = self.dsno_row.get()
        initial = current if os.path.exists(current) else None
        folder = filedialog.askdirectory(
            title="Select DSNO Directory", initialdir=initial
        )
        if folder:
            self.dsno_row.set(folder)

    # ──────────────────────────────────────────────────────────────
    # Processing
    # ──────────────────────────────────────────────────────────────

    def _start_processing(self) -> None:
        self.run_btn.configure(state="disabled")
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

        thread = threading.Thread(target=self._process_thread, daemon=True)
        thread.start()

    def _process_thread(self) -> None:
        try:
            date_range = f"{self.start_date.get()};{self.end_date.get()}"
            result = process_dsno(
                date_range=date_range,
                customer_sheet=self.customer_row.get(),
                control_sheet=self.control_row.get(),
                dsno_dir=self.dsno_row.get(),
            )

            summary = (
                f"Processing completed: {result.success}/{result.total} successful."
            )
            logging.info(summary)
            messagebox.showinfo("Success", summary)
        except Exception as exc:
            logging.error("Error during processing: %s", exc)
            messagebox.showerror("Error", str(exc))
        finally:
            self.run_btn.configure(state="normal")


def start_gui() -> None:
    """Launch the DSNO Processor GUI."""
    app = DSNOApp()
    app.mainloop()


if __name__ == "__main__":
    start_gui()
