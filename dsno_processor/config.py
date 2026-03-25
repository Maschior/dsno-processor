"""Centralized configuration loading and validation."""

from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path

from .exceptions import ConfigurationError

_DEFAULT_CONFIG_FILE = "config.txt"


@dataclass
class AppConfig:
    """Typed representation of the application configuration."""

    dsno_directory: Path
    control_sheet: Path
    customer_sheet: Path
    customer_sheet_pre_path: Path

    def validate_paths(self) -> list[str]:
        """Return a list of warnings for paths that do not exist."""
        warnings: list[str] = []
        for field_name in ("dsno_directory", "control_sheet"):
            path = getattr(self, field_name)
            if path != Path() and not path.exists():
                warnings.append(f"Path for '{field_name}' not found: {path}")
        return warnings


def load_config(path: Path | str | None = None) -> AppConfig:
    """Load configuration from an INI-style file.

    Args:
        path: Path to the config file. Defaults to ``config.txt`` in cwd.

    Returns:
        A validated :class:`AppConfig` instance.

    Raises:
        ConfigurationError: If the file cannot be read or the [PATHS] section
            is missing.
    """
    config_path = Path(path) if path else Path(_DEFAULT_CONFIG_FILE)

    if not config_path.exists():
        raise ConfigurationError(f"Configuration file not found: {config_path}")

    parser = configparser.ConfigParser()
    parser.read(str(config_path), encoding="utf-8")

    if "PATHS" not in parser:
        raise ConfigurationError(
            f"Missing [PATHS] section in configuration file: {config_path}"
        )

    paths = parser["PATHS"]

    return AppConfig(
        dsno_directory=Path(paths.get("DSNO_DIRECTORY", "")),
        control_sheet=Path(paths.get("CONTROL_SHEET", "")),
        customer_sheet=Path(paths.get("CUSTOMER_SHEET", "")),
        customer_sheet_pre_path=Path(paths.get("CUSTOMER_SHEET_PRE_PATH", "")),
    )
