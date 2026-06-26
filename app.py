"""Application composition root.

This module is intentionally small: it wires the presentation layer and keeps
startup concerns outside individual widgets and domain modules.
"""

from __future__ import annotations

import sys


def run() -> None:
    """Start the desktop application (CustomTkinter by default, --web for pywebview)."""
    if "--web" in sys.argv:
        from webui import start_webui

        start_webui()
    else:
        from gui import start_gui

        start_gui()
