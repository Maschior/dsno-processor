"""Spreadsheet import dialogs."""

from __future__ import annotations

import threading
from tkinter import filedialog, messagebox

import customtkinter as ctk

from dsno_processor.database import (
    get_connection,
    get_db_path,
    import_customer_sheet as db_import_customer_sheet,
    init_db,
)
from dsno_processor.i18n import t
from gui.themes.appearance import FONT_FAMILY as _FONT_FAMILY


class ImportWizard(ctk.CTkToplevel):
    """Dialog for importing a customer spreadsheet into the local SQLite database."""

    def __init__(self, master, app_config) -> None:
        super().__init__(master)
        self._cfg = app_config
        self.title(t("import.title"))
        self.geometry("560x220")
        self.minsize(480, 200)
        self.resizable(True, False)

        self._build_ui()
        self.after(50, self._bring_to_front)

    def _bring_to_front(self) -> None:
        self.lift()
        self.attributes("-topmost", True)
        self.focus_force()
        self.after(50, lambda: self.attributes("-topmost", False))

    def _build_ui(self) -> None:
        pad = 16

        # ── Header ────────────────────────────────────────────────
        ctk.CTkLabel(
            self,
            text=t("import.title"),
            font=ctk.CTkFont(family=_FONT_FAMILY, size=16, weight="bold"),
        ).pack(padx=pad, pady=(pad, 4))

        ctk.CTkLabel(
            self,
            text=t("import.select_file"),
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
            text_color="gray60",
        ).pack(padx=pad, anchor="w")

        # ── File picker row ───────────────────────────────────────
        row_frame = ctk.CTkFrame(self, fg_color="transparent")
        row_frame.pack(fill="x", padx=pad, pady=(2, 8))
        row_frame.columnconfigure(0, weight=1)

        self._file_entry = ctk.CTkEntry(
            row_frame,
            placeholder_text="C:\\...\\International Motors Shipment track.xlsx",
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
        )
        self._file_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(
            row_frame,
            text=t("btn.browse"),
            width=80,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=11),
            command=self._browse,
        ).grid(row=0, column=1)

        # ── Status label ──────────────────────────────────────────
        self._status_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
            text_color="gray60",
        )
        self._status_label.pack(padx=pad, pady=(0, 4))

        # ── Buttons ───────────────────────────────────────────────
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=pad, pady=(0, pad))

        ctk.CTkButton(
            btn_frame,
            text=t("btn.cancel"),
            height=34,
            corner_radius=8,
            fg_color=("gray70", "gray30"),
            hover_color=("gray60", "gray40"),
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
            command=self.destroy,
        ).pack(side="left", expand=True, fill="x", padx=(0, 4))

        self._import_btn = ctk.CTkButton(
            btn_frame,
            text=t("import.btn_import"),
            height=34,
            corner_radius=8,
            fg_color=("#2e7d32", "#1b5e20"),
            hover_color=("#388e3c", "#2e7d32"),
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12, weight="bold"),
            command=self._start_import,
        )
        self._import_btn.pack(side="left", expand=True, fill="x", padx=(4, 0))

    def _browse(self) -> None:
        path = filedialog.askopenfilename(
            title=t("browse.customer_sheet"),
            filetypes=[("Excel Files", "*.xlsx *.xls")],
        )
        if path:
            self._file_entry.delete(0, "end")
            self._file_entry.insert(0, path)

    def _start_import(self) -> None:
        file_path = self._file_entry.get().strip()
        if not file_path:
            self._status_label.configure(text=t("import.no_file"), text_color="#e53935")
            return

        self._import_btn.configure(state="disabled")
        self._status_label.configure(text=t("import.importing"), text_color="gray60")
        threading.Thread(
            target=self._import_thread, args=(file_path,), daemon=True
        ).start()

    def _import_thread(self, file_path: str) -> None:
        try:
            cfg = self._cfg
            inv_col = cfg.INVOICE_COL if cfg else "Invoice"
            bk_col = cfg.BOOKING_COL if cfg else "Booking/HAWB"
            cnt_col = cfg.CONTAINER_COL if cfg else "Container"
            sheet_name = cfg.CUSTOMER_SHEET_NAME if cfg else None

            db_path = get_db_path()
            conn = get_connection(db_path)
            init_db(conn)

            imported, skipped = db_import_customer_sheet(
                conn,
                file_path,
                invoice_col=inv_col,
                booking_col=bk_col,
                container_col=cnt_col,
                sheet_name=sheet_name or None,
            )
            conn.close()

            msg = t("import.success", imported=imported, skipped=skipped)
            self.after(
                0, lambda: self._status_label.configure(text=msg, text_color="#43a047")
            )
            self.after(0, lambda: messagebox.showinfo(t("import.title"), msg))
        except Exception as exc:
            msg = t("import.error", error=str(exc))
            self.after(
                0, lambda: self._status_label.configure(text=msg, text_color="#e53935")
            )
            self.after(0, lambda: messagebox.showerror(t("import.title"), msg))
        finally:
            self.after(0, lambda: self._import_btn.configure(state="normal"))


class ImportControlWizard(ctk.CTkToplevel):
    """Wizard to import control sheet data into the database."""

    def __init__(self, master, config) -> None:
        super().__init__(master)
        self.title(t("import_control.title"))
        self.geometry("480x200")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        self._cfg = config

        self._build_ui()

        # Center on screen
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (w // 2)
        y = (self.winfo_screenheight() // 2) - (h // 2)
        self.geometry(f"+{x}+{y}")

    def _build_ui(self) -> None:
        pad = 16

        # ── Input row ─────────────────────────────────────────────
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=pad, pady=(pad, 8))

        ctk.CTkLabel(
            row,
            text=t("import_control.select_file"),
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12, weight="bold"),
        ).pack(side="left", padx=(0, 8))

        self._file_entry = ctk.CTkEntry(
            row, font=ctk.CTkFont(family=_FONT_FAMILY, size=12)
        )
        self._file_entry.pack(side="left", expand=True, fill="x", padx=(0, 8))

        # Default to configured path if exists
        if self._cfg and self._cfg.control_sheet:
            self._file_entry.insert(0, str(self._cfg.control_sheet))

        ctk.CTkButton(
            row,
            text=t("import_control.btn_browse"),
            width=70,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
            command=self._browse,
        ).pack(side="left")

        # ── Status label ──────────────────────────────────────────
        self._status_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
            text_color="gray60",
        )
        self._status_label.pack(padx=pad, pady=(0, 4))

        # ── Buttons ───────────────────────────────────────────────
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=pad, pady=(0, pad))

        ctk.CTkButton(
            btn_frame,
            text=t("btn.cancel"),
            height=34,
            corner_radius=8,
            fg_color=("gray70", "gray30"),
            hover_color=("gray60", "gray40"),
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12),
            command=self.destroy,
        ).pack(side="left", expand=True, fill="x", padx=(0, 4))

        self._import_btn = ctk.CTkButton(
            btn_frame,
            text=t("import_control.btn_import"),
            height=34,
            corner_radius=8,
            fg_color=("#2e7d32", "#1b5e20"),
            hover_color=("#388e3c", "#2e7d32"),
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12, weight="bold"),
            command=self._start_import,
        )
        self._import_btn.pack(side="left", expand=True, fill="x", padx=(4, 0))

    def _browse(self) -> None:
        path = filedialog.askopenfilename(
            title=t("browse.control_sheet"),
            filetypes=[("Excel Files", "*.xlsx *.xls")],
        )
        if path:
            self._file_entry.delete(0, "end")
            self._file_entry.insert(0, path)

    def _start_import(self) -> None:
        file_path = self._file_entry.get().strip()
        if not file_path:
            self._status_label.configure(
                text=t("import_control.no_file"), text_color="#e53935"
            )
            return

        self._import_btn.configure(state="disabled")
        self._status_label.configure(
            text=t("import_control.importing"), text_color="gray60"
        )
        threading.Thread(
            target=self._import_thread, args=(file_path,), daemon=True
        ).start()

    def _import_thread(self, file_path: str) -> None:
        try:
            cfg = self._cfg
            inv_col = cfg.CONTROL_INVOICE_COL if cfg else None
            dsno_col = cfg.DSNO_COL if cfg else None
            date_col = cfg.DATE_COL if cfg else None
            status_col = cfg.STATUS_COL if cfg else None
            oracle_freight_col = cfg.FREIGHT_ORACLE_COL if cfg else None
            softway_freight_col = cfg.FREIGHT_SOFTWAY_COL if cfg else None
            description_col = cfg.DESCRIPTION_COL if cfg else None

            from dsno_processor.database import get_db_path, get_connection, init_db
            from dsno_processor.database import (
                import_control_sheet as db_import_control_sheet,
            )

            db_path = get_db_path()
            conn = get_connection(db_path)
            init_db(conn)

            imported, skipped = db_import_control_sheet(
                conn,
                file_path,
                invoice_col=inv_col,
                dsno_col=dsno_col,
                date_col=date_col,
                status_col=status_col,
                oracle_freight_col=oracle_freight_col,
                softway_freight_col=softway_freight_col,
                description_col=description_col,
            )
            conn.close()

            msg = t("import_control.success", imported=imported, skipped=skipped)
            self.after(
                0, lambda: self._status_label.configure(text=msg, text_color="#43a047")
            )
            self.after(0, lambda: messagebox.showinfo(t("import_control.title"), msg))
        except Exception as exc:
            msg = t("import_control.error", error=str(exc))
            self.after(
                0, lambda: self._status_label.configure(text=msg, text_color="#e53935")
            )
            self.after(0, lambda: messagebox.showerror(t("import_control.title"), msg))
        finally:
            self.after(0, lambda: self._import_btn.configure(state="normal"))
