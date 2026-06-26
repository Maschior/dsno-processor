"""Application composition root.

This module is intentionally small: it wires the presentation layer and keeps
startup concerns outside individual widgets and domain modules.
"""

from __future__ import annotations

import sys


def run() -> None:
    """Start the desktop application (pywebview web UI by default, --classic for CustomTkinter)."""
    if "--classic" in sys.argv or "--gui" in sys.argv:
        from gui import start_gui

        start_gui()
    else:
        from webui import start_webui

        start_webui()
