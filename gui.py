"""DSNO Processor GUI — Tkinter interface for batch DSNO processing."""

import logging
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from tkcalendar import DateEntry

from dsno_processor import process_dsno
from dsno_processor.config import load_config
from dsno_processor.exceptions import ConfigurationError


class TextHandler(logging.Handler):
    """Route log records to a Tkinter Text widget."""

    def __init__(self, text_widget: tk.Text) -> None:
        super().__init__()
        self.text = text_widget

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)

        def _append() -> None:
            self.text.configure(state="normal")
            self.text.insert(tk.END, msg + "\n")
            self.text.configure(state="disabled")
            self.text.yview(tk.END)

        self.text.after(0, _append)


class DSNOApp(tk.Tk):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        self.title("DSNO Processor")
        self.geometry("700x550")
        self.columnconfigure(1, weight=1)

        # Style
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        # Load config with fallback defaults
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

        # Tkinter variables
        self.customer_sheet_var = tk.StringVar(value=default_customer)
        self.control_sheet_var = tk.StringVar(value=default_control)
        self.dsno_dir_var = tk.StringVar(value=default_dsno_dir)

        self._create_widgets()
        self._setup_logging()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_logging(self) -> None:
        handler = TextHandler(self.log_text)
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        root = logging.getLogger()
        root.addHandler(handler)
        root.setLevel(logging.INFO)

    def _create_widgets(self) -> None:
        pad = {"padx": 10, "pady": 10}

        # Header
        info_frame = ttk.Frame(self)
        info_frame.grid(row=0, column=0, columnspan=3, sticky="ew", **pad)
        ttk.Label(
            info_frame, text="DSNO Processor", font=("Segoe UI", 16, "bold")
        ).pack()
        ttk.Label(
            info_frame,
            text="Process and edit DSNO files according to ASN spreadsheets.",
        ).pack()

        # Date Range
        ttk.Label(self, text="Date Range:").grid(row=1, column=0, sticky="w", **pad)
        date_frame = ttk.Frame(self)
        date_frame.grid(row=1, column=1, sticky="w", **pad)

        ttk.Label(date_frame, text="Start:").pack(side=tk.LEFT, padx=(0, 5))
        self.start_date_entry = DateEntry(
            date_frame, width=12, date_pattern="dd/MM/yyyy"
        )
        self.start_date_entry.pack(side=tk.LEFT, padx=(0, 15))

        ttk.Label(date_frame, text="End:").pack(side=tk.LEFT, padx=(0, 5))
        self.end_date_entry = DateEntry(
            date_frame, width=12, date_pattern="dd/MM/yyyy"
        )
        self.end_date_entry.pack(side=tk.LEFT)

        # Customer Sheet
        ttk.Label(self, text="Customer Sheet:").grid(
            row=2, column=0, sticky="w", **pad
        )
        ttk.Entry(self, textvariable=self.customer_sheet_var).grid(
            row=2, column=1, sticky="ew", **pad
        )
        ttk.Button(self, text="Browse", command=self._browse_customer).grid(
            row=2, column=2, **pad
        )

        # Control Sheet
        ttk.Label(self, text="Control Sheet:").grid(
            row=3, column=0, sticky="w", **pad
        )
        ttk.Entry(self, textvariable=self.control_sheet_var).grid(
            row=3, column=1, sticky="ew", **pad
        )
        ttk.Button(self, text="Browse", command=self._browse_control).grid(
            row=3, column=2, **pad
        )

        # DSNO Directory
        ttk.Label(self, text="DSNO Directory:").grid(
            row=4, column=0, sticky="w", **pad
        )
        ttk.Entry(self, textvariable=self.dsno_dir_var).grid(
            row=4, column=1, sticky="ew", **pad
        )
        ttk.Button(self, text="Browse", command=self._browse_dsno_dir).grid(
            row=4, column=2, **pad
        )

        # Run Button
        self.run_btn = ttk.Button(
            self, text="Start Processing", command=self._start_processing
        )
        self.run_btn.grid(row=5, column=0, columnspan=3, pady=15, ipady=5)

        # Log Output
        ttk.Label(self, text="Process Output Logs:").grid(
            row=6, column=0, sticky="w", padx=10
        )
        self.log_text = tk.Text(
            self,
            state="disabled",
            wrap="word",
            font=("Consolas", 9),
            relief="solid",
            borderwidth=1,
        )
        self.log_text.grid(row=7, column=0, columnspan=3, sticky="nsew", padx=10, pady=5)
        self.rowconfigure(7, weight=1)

    # ------------------------------------------------------------------
    # Browse dialogs
    # ------------------------------------------------------------------

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
            self.customer_sheet_var.set(path)

    def _browse_control(self) -> None:
        current_dir = os.path.dirname(self.control_sheet_var.get())
        initial = current_dir if os.path.exists(current_dir) else None
        path = filedialog.askopenfilename(
            title="Select Control Sheet",
            initialdir=initial,
            filetypes=[("Excel Files", "*.xlsx *.xls")],
        )
        if path:
            self.control_sheet_var.set(path)

    def _browse_dsno_dir(self) -> None:
        current = self.dsno_dir_var.get()
        initial = current if os.path.exists(current) else None
        folder = filedialog.askdirectory(
            title="Select DSNO Directory", initialdir=initial
        )
        if folder:
            self.dsno_dir_var.set(folder)

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------

    def _start_processing(self) -> None:
        self.run_btn.config(state="disabled")
        self.log_text.configure(state="normal")
        self.log_text.delete(1.0, tk.END)
        self.log_text.configure(state="disabled")

        thread = threading.Thread(target=self._process_thread, daemon=True)
        thread.start()

    def _process_thread(self) -> None:
        try:
            date_range = (
                f"{self.start_date_entry.get()};{self.end_date_entry.get()}"
            )
            result = process_dsno(
                date_range=date_range,
                customer_sheet=self.customer_sheet_var.get(),
                control_sheet=self.control_sheet_var.get(),
                dsno_dir=self.dsno_dir_var.get(),
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
            self.run_btn.config(state="normal")


def start_gui() -> None:
    """Launch the DSNO Processor GUI."""
    app = DSNOApp()
    app.mainloop()


if __name__ == "__main__":
    start_gui()
