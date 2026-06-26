"""pywebview frontend — alternative UI to the CustomTkinter GUI.

Launched via ``py main.py --web``. Renders the React build (``frontend/dist``)
in a native window and talks to the Python backend in-process through
:class:`webui.api.Api`. No HTTP server, no Node at runtime.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import os
from pathlib import Path

import webview

from .api import Api

# Windows' registry often maps .js → text/plain, which makes the bundled static
# server send the wrong Content-Type and the browser refuses the ES module.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/javascript", ".mjs")

_ROOT = Path(__file__).resolve().parent.parent
_DIST_INDEX = _ROOT / "frontend" / "dist" / "index.html"


class _JsLogHandler(logging.Handler):
    """Stream `logging` records to the web UI's debug panel via window.__onLog.

    Mirrors the CustomTkinter LogWindow handler (`LEVELNAME: message`, INFO+).
    """

    def __init__(self, get_window) -> None:
        super().__init__()
        self._get_window = get_window

    def emit(self, record: logging.LogRecord) -> None:
        window = self._get_window()
        if not window:
            return
        try:
            line = self.format(record)
            window.evaluate_js(f"window.__onLog && window.__onLog({json.dumps(line)})")
        except Exception:  # noqa: BLE001 — never let logging crash the app
            pass


def _resolve_url() -> str:
    """Vite dev server in dev mode, packaged static build otherwise."""
    if os.environ.get("DSNO_WEB_DEV"):
        return "http://localhost:5173"
    if not _DIST_INDEX.exists():
        raise FileNotFoundError(
            f"Frontend build not found: {_DIST_INDEX}. Run 'npm run build' in frontend/."
        )
    return str(_DIST_INDEX)


def start_webui() -> None:
    """Launch the DSNO Processor web UI."""
    api = Api()
    window = webview.create_window(
        "DSNO Processor",
        url=_resolve_url(),
        js_api=api,
        width=1270,
        height=720,
        min_size=(900, 600),
    )
    api._window = window

    # Stream Python logging to the in-app debug panel (toggled by the Debug button).
    handler = _JsLogHandler(lambda: api._window)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    # http_server serves dist/ over a bundled localhost server so Vite's
    # crossorigin ES-module + asset paths load (file:// blocks them). Dev mode
    # already uses the Vite dev server, so only matters for the packaged build.
    # DSNO_WEB_DEBUG=1 additionally enables WebView2 DevTools (right-click → Inspect).
    webview.start(
        http_server=not os.environ.get("DSNO_WEB_DEV"),
        debug=bool(os.environ.get("DSNO_WEB_DEBUG")),
    )
