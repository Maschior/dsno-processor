"""Asset path resolution utilities for source and PyInstaller builds."""

from __future__ import annotations

import os
import sys


def get_asset_path(relative_path: str) -> str:
    """Resolve asset paths in development and PyInstaller production builds."""
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base_path, relative_path)
