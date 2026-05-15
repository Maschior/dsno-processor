"""SQLite repository façade for persistence operations."""

from __future__ import annotations

from dsno_processor.database import get_connection, get_db_path, init_db

__all__ = ["get_connection", "get_db_path", "init_db"]
