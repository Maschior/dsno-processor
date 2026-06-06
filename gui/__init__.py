"""GUI package public API."""

from gui.themes.appearance import configure_appearance

configure_appearance()

from gui.windows.main_window import DSNOApp, start_gui  # noqa: E402

__all__ = ["DSNOApp", "start_gui"]
