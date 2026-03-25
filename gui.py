import os
import threading
import logging
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import configparser
from tkcalendar import DateEntry
from pathlib import Path
from main import process_dsno

class TextHandler(logging.Handler):
    """This class allows you to log to a Tkinter Text or ScrolledText widget"""
    def __init__(self, text):
        logging.Handler.__init__(self)
        self.text = text

    def emit(self, record):
        msg = self.format(record)
        def append():
            self.text.configure(state='normal')
            self.text.insert(tk.END, msg + '\n')
            self.text.configure(state='disabled')
            self.text.yview(tk.END)
        # This is necessary because we can't modify the GUI from other threads
        self.text.after(0, append)

class DSNOApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DSNO Processor")
        self.geometry("700x550")
        
        # Configure grid weight
        self.columnconfigure(1, weight=1)
        
        # Styles
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        
        self.config = configparser.ConfigParser()
        self.config.read("config.txt", encoding="utf-8")
        paths = self.config["PATHS"] if "PATHS" in self.config else {}

        # Default Variables from config.txt or fallback values
        self.customer_sheet_var = tk.StringVar(value=paths.get("CUSTOMER_SHEET", "../../ASN NAVSTAR/03-03-2026/International Motors Shipment track 03.03.2026.xlsx"))
        self.control_sheet_var = tk.StringVar(value=paths.get("CONTROL_SHEET", "../../ASN NAVSTAR/Control ASN Navistar.xlsx"))
        self.dsno_dir_var = tk.StringVar(value=paths.get("DSNO_DIRECTORY", "../DSNO/"))
        self.customer_pre_path = paths.get("CUSTOMER_SHEET_PRE_PATH", "../../ASN NAVSTAR/03-03-2026/")
        
        self.create_widgets()
        self.setup_logging()

    def setup_logging(self):
        # Create text logger to output inside the GUI
        text_handler = TextHandler(self.log_text)
        text_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
        logging.getLogger().addHandler(text_handler)
        logging.getLogger().setLevel(logging.INFO)

    def create_widgets(self):
        padding = {'padx': 10, 'pady': 10}
        
        # Instruction Frame
        info_frame = ttk.Frame(self)
        info_frame.grid(row=0, column=0, columnspan=3, sticky="ew", **padding)
        ttk.Label(info_frame, text="DSNO Processor", font=("Segoe UI", 16, "bold")).pack()
        ttk.Label(info_frame, text="Process and edit DSNO files according to ASN spreadsheets.").pack()

        # Date Range
        ttk.Label(self, text="Date Range:").grid(row=1, column=0, sticky="w", **padding)
        
        date_frame = ttk.Frame(self)
        date_frame.grid(row=1, column=1, sticky="w", **padding)
        
        ttk.Label(date_frame, text="Start:").pack(side=tk.LEFT, padx=(0, 5))
        self.start_date_entry = DateEntry(date_frame, width=12, date_pattern='dd/MM/yyyy')
        self.start_date_entry.pack(side=tk.LEFT, padx=(0, 15))
        
        ttk.Label(date_frame, text="End:").pack(side=tk.LEFT, padx=(0, 5))
        self.end_date_entry = DateEntry(date_frame, width=12, date_pattern='dd/MM/yyyy')
        self.end_date_entry.pack(side=tk.LEFT)

        # Customer Sheet
        ttk.Label(self, text="Customer Sheet:").grid(row=2, column=0, sticky="w", **padding)
        ttk.Entry(self, textvariable=self.customer_sheet_var).grid(row=2, column=1, sticky="ew", **padding)
        ttk.Button(self, text="Browse", command=self.browse_customer).grid(row=2, column=2, **padding)
        
        # Control Sheet
        ttk.Label(self, text="Control Sheet:").grid(row=3, column=0, sticky="w", **padding)
        ttk.Entry(self, textvariable=self.control_sheet_var).grid(row=3, column=1, sticky="ew", **padding)
        ttk.Button(self, text="Browse", command=self.browse_control).grid(row=3, column=2, **padding)
        
        # DSNO Dir
        ttk.Label(self, text="DSNO Directory:").grid(row=4, column=0, sticky="w", **padding)
        ttk.Entry(self, textvariable=self.dsno_dir_var).grid(row=4, column=1, sticky="ew", **padding)
        ttk.Button(self, text="Browse", command=self.browse_dsno_dir).grid(row=4, column=2, **padding)
        
        # Run Button
        self.run_btn = ttk.Button(self, text="Start Processing", command=self.start_processing)
        self.run_btn.grid(row=5, column=0, columnspan=3, pady=15, ipady=5)
        
        # Log Output
        ttk.Label(self, text="Process Output Logs:").grid(row=6, column=0, sticky="w", padx=10)
        self.log_text = tk.Text(self, state='disabled', wrap="word", font=("Consolas", 9), relief="solid", borderwidth=1)
        self.log_text.grid(row=7, column=0, columnspan=3, sticky="nsew", padx=10, pady=5)
        self.rowconfigure(7, weight=1)

    def browse_customer(self):
        initial_dir = self.customer_pre_path if os.path.exists(self.customer_pre_path) else None
        filepath = filedialog.askopenfilename(
            title="Select Customer Sheet", 
            initialdir=initial_dir,
            filetypes=[("Excel Files", "*.xlsx *.xls")]
        )
        if filepath:
            self.customer_sheet_var.set(filepath)
            
    def browse_control(self):
        current_dir = os.path.dirname(self.control_sheet_var.get())
        initial_dir = current_dir if os.path.exists(current_dir) else None
        filepath = filedialog.askopenfilename(
            title="Select Control Sheet",
            initialdir=initial_dir,
            filetypes=[("Excel Files", "*.xlsx *.xls")]
        )
        if filepath:
            self.control_sheet_var.set(filepath)
            
    def browse_dsno_dir(self):
        current_dir = self.dsno_dir_var.get()
        initial_dir = current_dir if os.path.exists(current_dir) else None
        folder = filedialog.askdirectory(
            title="Select DSNO Directory",
            initialdir=initial_dir
        )
        if folder:
            self.dsno_dir_var.set(folder)

    def start_processing(self):
        self.run_btn.config(state="disabled")
        self.log_text.configure(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.configure(state='disabled')
        
        # Start processing in a separate thread so GUI doesn't freeze
        thread = threading.Thread(target=self.process_thread)
        thread.daemon = True
        thread.start()

    def process_thread(self):
        try:
            start_date_str = self.start_date_entry.get()
            end_date_str = self.end_date_entry.get()
            date_range = f"{start_date_str};{end_date_str}"
            
            customer_sheet = self.customer_sheet_var.get()
            control_sheet = self.control_sheet_var.get()
            dsno_dir = self.dsno_dir_var.get()
            
            process_dsno(date_range, customer_sheet, control_sheet, dsno_dir)
            logging.info("Processing finished successfully.")
            messagebox.showinfo("Success", "Processing completed successfully.")
        except Exception as e:
            logging.error(f"Error during processing: {str(e)}")
            messagebox.showerror("Error", str(e))
        finally:
            self.run_btn.config(state="normal")

def start_gui():
    app = DSNOApp()
    app.mainloop()

if __name__ == "__main__":
    start_gui()
