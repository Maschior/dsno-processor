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
from dsno_processor.config import (
    AppConfig,
    CredentialsConfig,
    EbsColumnsConfig,
    EbsConfig,
    EbsPastasConfig,
    PathsConfig,
    ProcessorConfig,
    load_config,
    save_config,
)
from dsno_processor.ebs_download import DownloadConfig, run_download
from dsno_processor.ebs_upload import UploadConfig, run_upload
from dsno_processor.exceptions import ConfigurationError

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

        header_inner = ctk.CTkFrame(header, fg_color="transparent")
        header_inner.pack(fill="x", padx=12, pady=(10, 0))

        ctk.CTkLabel(
            header_inner,
            text="⚙  DSNO Processor",
            font=ctk.CTkFont(family=_FONT_FAMILY, size=22, weight="bold"),
        ).pack(side="left", expand=True)

        ctk.CTkButton(
            header_inner,
            text="⚙  Configurações",
            width=140,
            height=32,
            corner_radius=8,
            fg_color=("gray70", "gray30"),
            hover_color=("gray60", "gray40"),
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
            command=self._open_settings,
        ).pack(side="right")

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

        # ── EBS Download / Upload buttons ────────────────────────
        ebs_frame = ctk.CTkFrame(self, fg_color="transparent")
        ebs_frame.pack(fill="x", padx=pad, pady=(0, 8))

        ctk.CTkButton(
            ebs_frame,
            text="📥  EBS Download",
            height=36,
            corner_radius=10,
            fg_color=("#2e7d32", "#1b5e20"),
            hover_color=("#388e3c", "#2e7d32"),
            font=ctk.CTkFont(family=_FONT_FAMILY, size=13, weight="bold"),
            command=self._open_download_window,
        ).pack(side="left", expand=True, fill="x", padx=(0, 4))

        ctk.CTkButton(
            ebs_frame,
            text="📤  EBS Upload",
            height=36,
            corner_radius=10,
            fg_color=("#e65100", "#bf360c"),
            hover_color=("#f57c00", "#e65100"),
            font=ctk.CTkFont(family=_FONT_FAMILY, size=13, weight="bold"),
            command=self._open_upload_window,
        ).pack(side="left", expand=True, fill="x", padx=(4, 0))

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

    # ──────────────────────────────────────────────────────────────
    # EBS Windows
    # ──────────────────────────────────────────────────────────────

    def _open_download_window(self) -> None:
        app_config = None
        try:
            app_config = load_config()
        except Exception:
            pass
        DownloadWindow(self, app_config)

    def _open_upload_window(self) -> None:
        app_config = None
        try:
            app_config = load_config()
        except Exception:
            pass
        UploadWindow(self, app_config)

    def _open_settings(self) -> None:
        SettingsWindow(self, on_save=self._reload_config)

    def _reload_config(self) -> None:
        """Reload config from disk and refresh main window defaults."""
        try:
            app_config = load_config()
        except ConfigurationError:
            return
        self.customer_row.set(str(app_config.customer_sheet))
        self.control_row.set(str(app_config.control_sheet))
        self.dsno_row.set(str(app_config.dsno_directory))
        self._customer_pre_path = str(app_config.customer_sheet_pre_path)
        logging.info("Configurações recarregadas com sucesso.")


# ══════════════════════════════════════════════════════════════════════
# EBS Download Window
# ══════════════════════════════════════════════════════════════════════

class _EbsTextboxHandler(logging.Handler):
    """Route log records to a CTkTextbox in a Toplevel window."""

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


class DownloadWindow(ctk.CTkToplevel):
    """Window for EBS file download automation."""

    def __init__(self, master, app_config=None) -> None:
        super().__init__(master)
        self.title("📥 EBS Download")
        self.geometry("820x700")
        self.minsize(700, 550)
        self._app_config = app_config
        self._handler: _EbsTextboxHandler | None = None

        pad = 14

        # ── Header ────────────────────────────────────────────────
        header = ctk.CTkFrame(self, corner_radius=12)
        header.pack(fill="x", padx=pad, pady=(pad, 8))
        ctk.CTkLabel(
            header,
            text="📥  EBS File Download",
            font=ctk.CTkFont(family=_FONT_FAMILY, size=20, weight="bold"),
        ).pack(pady=(12, 2))
        ctk.CTkLabel(
            header,
            text="Baixe arquivos DSNO do Oracle EBS automaticamente.",
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
            text_color="gray60",
        ).pack(pady=(0, 12))

        # ── Form fields ──────────────────────────────────────────
        form = ctk.CTkScrollableFrame(self, corner_radius=8)
        form.pack(fill="x", padx=pad, pady=4)
        form.columnconfigure(1, weight=1)

        row = 0

        def _label(text, r):
            ctk.CTkLabel(
                form, text=text, anchor="w", width=140,
                font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
            ).grid(row=r, column=0, padx=(0, 8), pady=3, sticky="w")

        def _entry(r, default="", width=None):
            var = tk.StringVar(value=default)
            e = ctk.CTkEntry(
                form, textvariable=var,
                font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
            )
            if width:
                e.configure(width=width)
            e.grid(row=r, column=1, sticky="ew", pady=3)
            return var, e

        # Date range
        _label("Date Start:", row)
        self.date_start_var, date_start_entry = _entry(row, "", width=200)
        add_placeholder(date_start_entry, "DD/MM/YYYY HH:MM:SS")
        row += 1
        _label("Date End:", row)
        self.date_end_var, date_end_entry = _entry(row, "", width=200)
        add_placeholder(date_end_entry, "DD/MM/YYYY HH:MM:SS")
        row += 1

        # Status filter
        _label("Status Filter:", row)
        self.status_filter_var, status_filter_entry = _entry(row, "")
        add_placeholder(status_filter_entry, "Processed, Downloaded, <vazio>")
        row += 1

        # Download Dir
        _label("Download Dir:", row)
        self.dir_var, _ = _entry(row, str(app_config.download_dir) if app_config else "")
        ctk.CTkButton(
            form, text="Browse", width=70, command=self._browse_dir,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=11),
        ).grid(row=row, column=2, padx=(4, 0), pady=3)
        row += 1

        # Customer Sheet
        _label("Customer Sheet:", row)
        self.sheet_var, _ = _entry(row, str(app_config.control_sheet) if app_config else "")
        ctk.CTkButton(
            form, text="Browse", width=70, command=self._browse_sheet,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=11),
        ).grid(row=row, column=2, padx=(4, 0), pady=3)
        row += 1
        
        # EBS URL
        _label("EBS URL:", row)
        self.ebs_url_var, _ = _entry(row, app_config.ebs_download_url if app_config else "")
        row += 1

        # Columns
        _label("DSNO Column:", row)
        self.dsno_col_var, _ = _entry(row, app_config.ebs_dsno_col if app_config else "ARGUMENT2")
        row += 1
        _label("Date Column:", row)
        self.date_col_var, _ = _entry(row, app_config.ebs_date_col if app_config else "CREATION_DATE")
        row += 1
        _label("Status Column:", row)
        self.status_col_var, _ = _entry(row, app_config.ebs_status_col if app_config else "STATUS")
        row += 1

        # Pastas indices
        indices_str = ",".join(str(x) for x in (app_config.ebs_pastas_indices if app_config else [92, 95, 101]))
        _label("Pastas Indices:", row)
        self.pastas_var, _ = _entry(row, indices_str)
        row += 1

        # ── Buttons ───────────────────────────────────────────────
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=pad, pady=8)

        self.start_btn = ctk.CTkButton(
            btn_frame,
            text="▶  Iniciar Download",
            height=38,
            corner_radius=10,
            fg_color=("#2e7d32", "#1b5e20"),
            hover_color=("#388e3c", "#2e7d32"),
            font=ctk.CTkFont(family=_FONT_FAMILY, size=13, weight="bold"),
            command=self._start_download,
        )
        self.start_btn.pack(fill="x")

        # ── Log ───────────────────────────────────────────────────
        ctk.CTkLabel(
            self, text="Download Logs:", anchor="w",
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
        ).pack(fill="x", padx=pad)

        self.log_box = ctk.CTkTextbox(
            self, state="disabled", wrap="word",
            font=ctk.CTkFont(family="Consolas", size=11),
            corner_radius=8,
        )
        self.log_box.pack(fill="both", expand=True, padx=pad, pady=(4, pad))

    # ── Browse helpers ────────────────────────────────────────────
    def _browse_sheet(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Customer Sheet",
            filetypes=[("Excel Files", "*.xlsx *.xls")],
        )
        if path:
            self.sheet_var.set(path)

    def _browse_dir(self) -> None:
        folder = filedialog.askdirectory(title="Select Download Directory")
        if folder:
            self.dir_var.set(folder)

    # ── Actions ───────────────────────────────────────────────────
    def _start_download(self) -> None:
        self.start_btn.configure(state="disabled")

        # Clear log
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

        # Setup logging handler
        self._handler = _EbsTextboxHandler(self.log_box)
        self._handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        logging.getLogger("dsno_processor.ebs_download").addHandler(self._handler)

        # Parse pastas indices
        try:
            pastas = [int(x.strip()) for x in self.pastas_var.get().split(",") if x.strip()]
        except ValueError:
            pastas = [92, 95, 101]

        config = DownloadConfig(
            ebs_url=self.ebs_url_var.get(),
            customer_sheet_path=self.sheet_var.get(),
            download_dir=self.dir_var.get(),
            email=self._app_config.ebs_email if self._app_config else "",
            senha=self._app_config.ebs_password if self._app_config else "",
            dsno_col=self.dsno_col_var.get(),
            date_col=self.date_col_var.get(),
            status_col=self.status_col_var.get(),
            date_start=self.date_start_var.get(),
            date_end=self.date_end_var.get(),
            status_filter=self.status_filter_var.get(),
            pastas_indices=pastas,
        )

        thread = threading.Thread(
            target=self._download_thread, args=(config,), daemon=True,
        )
        thread.start()

    def _download_thread(self, config: DownloadConfig) -> None:
        try:
            result = run_download(config)
            total = result["sucesso"] + result["ignorados"] + len(result["falhas"])
            summary = f"Download concluído: {result['sucesso']}/{total} com sucesso."
            logging.getLogger("dsno_processor.ebs_download").info(summary)
            messagebox.showinfo("Download", summary)
        except Exception as exc:
            logging.getLogger("dsno_processor.ebs_download").error("Erro: %s", exc)
            messagebox.showerror("Erro", str(exc))
        finally:
            self.start_btn.configure(state="normal")
            if self._handler:
                logging.getLogger("dsno_processor.ebs_download").removeHandler(self._handler)


# ══════════════════════════════════════════════════════════════════════
# EBS Upload Window
# ══════════════════════════════════════════════════════════════════════

class UploadWindow(ctk.CTkToplevel):
    """Window for EBS file upload automation."""

    def __init__(self, master, app_config=None) -> None:
        super().__init__(master)
        self.title("📤 EBS Upload")
        self.geometry("720x550")
        self.minsize(600, 450)
        self._app_config = app_config
        self._handler: _EbsTextboxHandler | None = None

        pad = 14

        # ── Header ────────────────────────────────────────────────
        header = ctk.CTkFrame(self, corner_radius=12)
        header.pack(fill="x", padx=pad, pady=(pad, 8))
        ctk.CTkLabel(
            header,
            text="📤  EBS File Upload",
            font=ctk.CTkFont(family=_FONT_FAMILY, size=20, weight="bold"),
        ).pack(pady=(12, 2))
        ctk.CTkLabel(
            header,
            text="Envie arquivos DSNO processados ao Oracle EBS.",
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
            text_color="gray60",
        ).pack(pady=(0, 12))

        # ── Form fields ──────────────────────────────────────────
        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(fill="x", padx=pad, pady=4)
        form.columnconfigure(1, weight=1)

        row = 0

        def _label(text, r):
            ctk.CTkLabel(
                form, text=text, anchor="w", width=140,
                font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
            ).grid(row=r, column=0, padx=(0, 8), pady=3, sticky="w")

        def _entry(r, default=""):
            var = tk.StringVar(value=default)
            ctk.CTkEntry(
                form, textvariable=var,
                font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
            ).grid(row=r, column=1, sticky="ew", pady=3)
            return var

        # EBS URL
        _label("EBS URL:", row)
        self.ebs_url_var = _entry(row, app_config.ebs_upload_url if app_config else "")
        row += 1

        # Upload Dir
        _label("Upload Dir:", row)
        self.dir_var = _entry(row, str(app_config.upload_dir) if app_config else "")
        ctk.CTkButton(
            form, text="Browse", width=70, command=self._browse_dir,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=11),
        ).grid(row=row, column=2, padx=(4, 0), pady=3)
        row += 1

        # Pasta indice
        _label("Pasta Indice:", row)
        self.pasta_var = _entry(row, str(app_config.ebs_upload_pasta_indice) if app_config else "92")
        row += 1

        # ── Buttons ───────────────────────────────────────────────
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=pad, pady=8)

        self.start_btn = ctk.CTkButton(
            btn_frame,
            text="▶  Iniciar Upload",
            height=38,
            corner_radius=10,
            fg_color=("#e65100", "#bf360c"),
            hover_color=("#f57c00", "#e65100"),
            font=ctk.CTkFont(family=_FONT_FAMILY, size=13, weight="bold"),
            command=self._start_upload,
        )
        self.start_btn.pack(fill="x")

        # ── Log ───────────────────────────────────────────────────
        ctk.CTkLabel(
            self, text="Upload Logs:", anchor="w",
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
        ).pack(fill="x", padx=pad)

        self.log_box = ctk.CTkTextbox(
            self, state="disabled", wrap="word",
            font=ctk.CTkFont(family="Consolas", size=11),
            corner_radius=8,
        )
        self.log_box.pack(fill="both", expand=True, padx=pad, pady=(4, pad))

    # ── Browse ────────────────────────────────────────────────────
    def _browse_dir(self) -> None:
        folder = filedialog.askdirectory(title="Select Upload Directory")
        if folder:
            self.dir_var.set(folder)

    # ── Actions ───────────────────────────────────────────────────
    def _start_upload(self) -> None:
        self.start_btn.configure(state="disabled")

        # Clear log
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

        # Setup logging handler
        self._handler = _EbsTextboxHandler(self.log_box)
        self._handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        logging.getLogger("dsno_processor.ebs_upload").addHandler(self._handler)

        try:
            pasta_idx = int(self.pasta_var.get())
        except ValueError:
            pasta_idx = 92

        config = UploadConfig(
            ebs_url=self.ebs_url_var.get(),
            upload_dir=self.dir_var.get(),
            email=self._app_config.ebs_email if self._app_config else "",
            senha=self._app_config.ebs_password if self._app_config else "",
            pasta_indice=pasta_idx,
        )

        thread = threading.Thread(
            target=self._upload_thread, args=(config,), daemon=True,
        )
        thread.start()

    def _upload_thread(self, config: UploadConfig) -> None:
        try:
            result = run_upload(config)
            total = result["sucesso"] + result["ignorados"] + len(result["falhas"])
            summary = f"Upload concluído: {result['sucesso']}/{total} com sucesso."
            logging.getLogger("dsno_processor.ebs_upload").info(summary)
            messagebox.showinfo("Upload", summary)
        except Exception as exc:
            logging.getLogger("dsno_processor.ebs_upload").error("Erro: %s", exc)
            messagebox.showerror("Erro", str(exc))
        finally:
            self.start_btn.configure(state="normal")
            if self._handler:
                logging.getLogger("dsno_processor.ebs_upload").removeHandler(self._handler)


# ══════════════════════════════════════════════════════════════════════
# Settings Window — Tabbed interface
# ══════════════════════════════════════════════════════════════════════

class SettingsWindow(ctk.CTkToplevel):
    """Window to view and edit the persistent config.toml settings.

    Uses a tabbed layout so each config domain (Paths, Processor, EBS,
    Columns, Pastas, Credentials) gets its own focused view.
    """

    _TAB_NAMES = [
        "📂 Caminhos",
        "⚙ Processador",
        "🌐 EBS",
        "📊 Colunas",
        "📁 Pastas",
        "🔑 Credenciais",
    ]

    def __init__(self, master, on_save=None) -> None:
        super().__init__(master)
        self.title("⚙  Configurações")
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
            text="⚙  Configurações do Programa",
            font=ctk.CTkFont(family=_FONT_FAMILY, size=20, weight="bold"),
        ).pack(pady=(12, 2))
        ctk.CTkLabel(
            header,
            text="Edite as configurações permanentes salvas em config.toml.",
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

        self._build_tab_paths(cfg)
        self._build_tab_processor(cfg)
        self._build_tab_ebs(cfg)
        self._build_tab_columns(cfg)
        self._build_tab_pastas(cfg)
        self._build_tab_credentials(cfg)

        # ── Buttons ───────────────────────────────────────────────
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=pad, pady=(8, pad))

        ctk.CTkButton(
            btn_frame,
            text="✖  Cancelar",
            height=38,
            corner_radius=10,
            fg_color=("gray70", "gray30"),
            hover_color=("gray60", "gray40"),
            font=ctk.CTkFont(family=_FONT_FAMILY, size=13),
            command=self.destroy,
        ).pack(side="left", expand=True, fill="x", padx=(0, 4))

        ctk.CTkButton(
            btn_frame,
            text="💾  Salvar",
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

    def _build_tab_paths(self, cfg) -> None:
        tab = self._tabview.tab("📂 Caminhos")
        form = self._make_form(tab)

        self._tab_hint(
            form, "Diretórios e arquivos utilizados pelo processador DSNO."
        )

        self._add_path_field(
            form, 1, "Diretório DSNO:", "dsno_directory",
            str(cfg.paths.dsno_directory) if cfg else "",
            mode="dir",
            hint="Pasta com os arquivos .txt de DSNO.",
        )
        self._add_path_field(
            form, 3, "Control Sheet:", "control_sheet",
            str(cfg.paths.control_sheet) if cfg else "",
            mode="file",
            filetypes=[("Excel", "*.xlsx *.xls")],
            hint="Planilha Control ASN Navistar.",
        )
        self._add_path_field(
            form, 5, "Customer Sheet:", "customer_sheet",
            str(cfg.paths.customer_sheet) if cfg else "",
            mode="file",
            filetypes=[("Excel", "*.xlsx *.xls")],
            hint="Planilha do cliente (opcional).",
        )
        self._add_path_field(
            form, 7, "Customer Pre-Path:", "customer_sheet_pre_path",
            str(cfg.paths.customer_sheet_pre_path) if cfg else "",
            mode="dir",
            hint="Pasta padrão para busca da Customer Sheet.",
        )

    def _build_tab_processor(self, cfg) -> None:
        tab = self._tabview.tab("⚙ Processador")
        form = self._make_form(tab)

        self._tab_hint(
            form,
            "Configurações que controlam o comportamento do processamento.",
        )

        self._add_text_field(
            form, 1, "Status Válidos:", "processor_valid_statuses",
            ", ".join(
                s.capitalize()
                for s in cfg.processor.valid_statuses
            )
            if cfg
            else "Downloaded",
            hint="Separe múltiplos valores por vírgula (ex: Downloaded, New).",
        )

    def _build_tab_ebs(self, cfg) -> None:
        tab = self._tabview.tab("🌐 EBS")
        form = self._make_form(tab)

        self._tab_hint(
            form, "URLs e diretórios do Oracle EBS para download e upload."
        )

        self._add_text_field(
            form, 1, "Download URL:", "ebs_download_url",
            cfg.ebs.download_url if cfg else "",
            hint="URL completa da página de download do EBS.",
        )
        self._add_text_field(
            form, 3, "Upload URL:", "ebs_upload_url",
            cfg.ebs.upload_url if cfg else "",
            hint="URL completa da página de upload do EBS.",
        )
        self._add_path_field(
            form, 5, "Download Dir:", "download_dir",
            str(cfg.ebs.download_dir) if cfg else "",
            mode="dir",
            hint="Pasta onde os arquivos baixados serão salvos.",
        )
        self._add_path_field(
            form, 7, "Upload Dir:", "upload_dir",
            str(cfg.ebs.upload_dir) if cfg else "",
            mode="dir",
            hint="Pasta com os arquivos processados para upload.",
        )

    def _build_tab_columns(self, cfg) -> None:
        tab = self._tabview.tab("📊 Colunas")
        form = self._make_form(tab)

        self._tab_hint(
            form,
            "Nomes das colunas usadas nas planilhas do EBS.",
        )

        self._add_text_field(
            form, 1, "Coluna DSNO:", "ebs_col_dsno",
            cfg.ebs.columns.dsno if cfg else "ARGUMENT2",
            hint="Nome da coluna que contém o identificador DSNO.",
        )
        self._add_text_field(
            form, 3, "Coluna Data:", "ebs_col_date",
            cfg.ebs.columns.date if cfg else "CREATION_DATE",
            hint="Nome da coluna de data de criação.",
        )
        self._add_text_field(
            form, 5, "Coluna Status:", "ebs_col_status",
            cfg.ebs.columns.status if cfg else "STATUS",
            hint="Nome da coluna de status.",
        )

    def _build_tab_pastas(self, cfg) -> None:
        tab = self._tabview.tab("📁 Pastas")
        form = self._make_form(tab)

        self._tab_hint(
            form,
            "Índices de pastas usados pelo EBS para download e upload.",
        )

        indices = (
            ", ".join(str(x) for x in cfg.ebs.pastas.download_indices)
            if cfg
            else "92, 95, 101"
        )
        self._add_text_field(
            form, 1, "Índices Download:", "ebs_pastas_download",
            indices,
            hint="Índices separados por vírgula (ex: 92, 95, 101).",
        )
        self._add_text_field(
            form, 3, "Índice Upload:", "ebs_pasta_upload",
            str(cfg.ebs.pastas.upload_indice) if cfg else "92",
            hint="Índice da pasta de upload.",
        )

    def _build_tab_credentials(self, cfg) -> None:
        tab = self._tabview.tab("🔑 Credenciais")
        form = self._make_form(tab)

        self._tab_hint(
            form,
            "Credenciais usadas para login automático no Microsoft / EBS.",
        )

        self._add_text_field(
            form, 1, "Email:", "cred_email",
            cfg.credentials.email if cfg else "",
            hint="Endereço de e-mail corporativo.",
        )

        # Password with toggle
        row = 3
        self._hint_label(form, "Senha utilizada no login automático.", row)
        row += 1

        ctk.CTkLabel(
            form, text="Senha:", anchor="w", width=150,
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
                    title=f"Selecionar {label.rstrip(':')}"
                )
            else:
                result = filedialog.askopenfilename(
                    title=f"Selecionar {label.rstrip(':')}",
                    filetypes=filetypes or [],
                )
            if result:
                var.set(result)
                self._update_indicator(key, result, mode)

        ctk.CTkButton(
            btn_frame, text="Browse", width=70, command=_browse,
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
            pastas = [
                int(x.strip())
                for x in self._vars["ebs_pastas_download"].get().split(",")
                if x.strip()
            ]
        except ValueError:
            pastas = [92, 95, 101]

        try:
            upload_pasta = int(self._vars["ebs_pasta_upload"].get())
        except ValueError:
            upload_pasta = 92

        valid_raw = self._vars["processor_valid_statuses"].get()
        valid_statuses = [
            s.strip().lower() for s in valid_raw.split(",") if s.strip()
        ]

        new_config = AppConfig(
            paths=PathsConfig(
                dsno_directory=_Path(self._vars["dsno_directory"].get()),
                control_sheet=_Path(self._vars["control_sheet"].get()),
                customer_sheet=_Path(self._vars["customer_sheet"].get()),
                customer_sheet_pre_path=_Path(
                    self._vars["customer_sheet_pre_path"].get()
                ),
            ),
            processor=ProcessorConfig(valid_statuses=valid_statuses),
            ebs=EbsConfig(
                download_url=self._vars["ebs_download_url"].get(),
                upload_url=self._vars["ebs_upload_url"].get(),
                download_dir=_Path(self._vars["download_dir"].get()),
                upload_dir=_Path(self._vars["upload_dir"].get()),
                columns=EbsColumnsConfig(
                    dsno=self._vars["ebs_col_dsno"].get(),
                    date=self._vars["ebs_col_date"].get(),
                    status=self._vars["ebs_col_status"].get(),
                ),
                pastas=EbsPastasConfig(
                    download_indices=pastas,
                    upload_indice=upload_pasta,
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
                "Configurações",
                "Configurações salvas com sucesso!\n"
                "As alterações já estão em vigor.",
            )
            if self._on_save:
                self._on_save()
            self.destroy()
        except Exception as exc:
            messagebox.showerror(
                "Erro", f"Erro ao salvar configurações:\n{exc}"
            )



def start_gui() -> None:
    """Launch the DSNO Processor GUI."""
    app = DSNOApp()
    app.mainloop()


if __name__ == "__main__":
    start_gui()
