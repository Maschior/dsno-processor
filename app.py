"""Application composition root.

This module is intentionally small: it wires the presentation layer and keeps
startup concerns outside individual widgets, controllers, and services.
"""

from __future__ import annotations

from gui import start_gui


def run() -> None:
    """Start the desktop application."""
    start_gui()
