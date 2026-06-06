"""Shared fixtures for the DSNO Processor test suite."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pandas as pd
import pytest
import tomli_w


# ── Minimal config.toml content ─────────────────────────────────────


_MINIMAL_CONFIG: dict = {
    "general": {"language": "en"},
    "paths": {
        "dsno_directory": ".",
        "control_sheet": ".",
        "customer_sheet": ".",
        "customer_sheet_pre_path": ".",
    },
    "customer_sheet": {
        "cols": {
            "invoice": "Invoice",
            "booking": "Booking/HAWB",
            "container": "Container",
        },
        "config": {"sheet_name": ""},
    },
    "control_sheet": {
        "cols": {
            "invoice": "INVOICE",
            "dsno": "ARGUMENT2",
            "date": "CREATION_DATE",
            "status": "STATUS",
            "freight_oracle": "FREIGHT_ORACLE",
            "freight_softway": "FREIGHT_SOFTWAY",
        },
    },
    "ebs": {
        "download_url": "https://example.com/download",
        "upload_url": "https://example.com/upload",
        "download_dir": ".",
        "upload_dir": ".",
        "headless": False,
        "folders": {
            "download_indices": [92, 95, 101],
            "upload_index": 92,
        },
    },
    "credentials": {
        "email": "test@example.com",
        "password": "secret",
    },
}


@pytest.fixture()
def config_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Write a minimal ``config.toml`` and ``chdir`` into *tmp_path*.

    Modules that call ``load_config()`` at import-time will pick up this
    file when they are (re-)imported inside a test.
    """
    toml_path = tmp_path / "config.toml"
    with open(toml_path, "wb") as fh:
        tomli_w.dump(_MINIMAL_CONFIG, fh)
    monkeypatch.chdir(tmp_path)
    return toml_path


# ── DSNO file fixture ───────────────────────────────────────────────


_DSNO_SAMPLE = textwrap.dedent("""\
HEADER LINE 1 — some metadata
                                                        1000XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXOLD_booking_value_padded_old_invoice_padded____________
                                                        1010XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXOLD_container_pad____________________________________________________________________________________________________________________________________________________________________________________________XX
TRAILER LINE — end of file
""")


@pytest.fixture()
def dsno_file(tmp_path: Path) -> Path:
    """Create a sample DSNO fixed-format file."""
    path = tmp_path / "DSNO_SAMPLE.txt"
    path.write_text(_DSNO_SAMPLE, encoding="utf-8")
    return path


# ── DataFrame fixtures ──────────────────────────────────────────────


@pytest.fixture()
def control_sheet_df() -> pd.DataFrame:
    """Pre-built DataFrame mimicking the control spreadsheet."""
    return pd.DataFrame(
        {
            "INVOICE": [100001, 100002, 100003],
            "ARGUMENT2": [
                "DSNO_FILE_001.txt",
                "DSNO_FILE_002.txt",
                "DSNO_FILE_003.txt",
            ],
            "CREATION_DATE": [
                "01/15/2026 10:00:00 AM",
                "01/16/2026 11:30:00 AM",
                "02/01/2026 09:00:00 AM",
            ],
            "STATUS": ["Open", "Processed", "Open"],
            "FREIGHT_ORACLE": [100.0, 200.0, 300.0],
            "FREIGHT_SOFTWAY": [110.0, 200.0, None],
        }
    )


@pytest.fixture()
def customer_sheet_df() -> pd.DataFrame:
    """Pre-built DataFrame mimicking the customer spreadsheet."""
    return pd.DataFrame(
        {
            "INVOICE": [100001, 100002, 100003],
            "BOOKING/HAWB": ["BK-001", "BK-002", "BK-003"],
            "CONTAINER": ["CNT-001", "CNT-002", "CNT-003"],
        }
    )
