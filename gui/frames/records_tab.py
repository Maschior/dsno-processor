"""Records tab: read-only viewer over the internal SQLite tables."""

from __future__ import annotations

import logging
from tkinter import ttk

import customtkinter as ctk

from dsno_processor.database import (
    get_connection,
    get_db_path,
    init_db,
    list_control,
    list_shipments,
)
from dsno_processor.i18n import t

log = logging.getLogger(__name__)


class RecordsTabMixin:
    """Build the Records tab (control + customer/shipment viewer)."""

    def _build_tab_records(self) -> None:
        outer = self._tabview.tab(self._TAB_RECORDS)

        bar = ctk.CTkFrame(outer, fg_color="transparent")
        bar.pack(fill="x", pady=(4, 6))

        # Segmented button display text → internal kind.
        self._records_kind = ctk.StringVar(value=t("records.control"))
        ctk.CTkSegmentedButton(
            bar,
            values=[t("records.control"), t("records.shipment")],
            variable=self._records_kind,
            command=lambda _=None: self._reload_records(),
        ).pack(side="left")

        ctk.CTkButton(
            bar, text=t("records.refresh"), width=110, command=self._reload_records
        ).pack(side="left", padx=8)

        self._records_count = ctk.CTkLabel(bar, text="")
        self._records_count.pack(side="left", padx=4)

        # Native table widget — ttk.Treeview, no extra dependency.
        self._records_tree = ttk.Treeview(outer, show="headings", selectmode="browse")
        vsb = ttk.Scrollbar(outer, orient="vertical", command=self._records_tree.yview)
        hsb = ttk.Scrollbar(outer, orient="horizontal", command=self._records_tree.xview)
        self._records_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self._records_tree.pack(fill="both", expand=True)

        self._reload_records()

    def _reload_records(self) -> None:
        kind = "shipment" if self._records_kind.get() == t("records.shipment") else "control"
        try:
            conn = get_connection(get_db_path())
            init_db(conn)
            try:
                columns, rows = list_shipments(conn) if kind == "shipment" else list_control(conn)
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001 — viewer must never crash the app
            log.warning("Could not read records: %s", exc)
            columns, rows = [], []

        tree = self._records_tree
        tree.delete(*tree.get_children())
        tree["columns"] = columns
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=120, stretch=False, anchor="w")
        for row in rows:
            tree.insert("", "end", values=row)
        self._records_count.configure(text=t("records.count", count=len(rows)))
