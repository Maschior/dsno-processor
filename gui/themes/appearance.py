"""CustomTkinter appearance constants and bootstrap helpers."""

from __future__ import annotations

import re

import customtkinter as ctk

FONT_FAMILY = "Segoe UI"
DATE_PATTERN = re.compile(r"^\d{2}/\d{2}/\d{4}$")
DATETIME_PATTERN = re.compile(r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}$")


def configure_appearance() -> None:
    """Apply the default application theme once at startup."""
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
