"""Centralized configuration loading and validation."""

from __future__ import annotations

import configparser
from dataclasses import dataclass, field
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

    # EBS Download / Upload settings
    ebs_download_url: str = ""
    ebs_upload_url: str = ""
    download_dir: Path = field(default_factory=Path)
    upload_dir: Path = field(default_factory=Path)
    ebs_dsno_col: str = "ARGUMENT2"
    ebs_date_col: str = "CREATION_DATE"
    ebs_status_col: str = "STATUS"
    ebs_pastas_indices: list[int] = field(default_factory=lambda: [92, 95, 101])
    ebs_upload_pasta_indice: int = 92
    ebs_email: str = ""
    ebs_password: str = ""
    processor_valid_statuses: list[str] = field(default_factory=lambda: ["downloaded"])

    def validate_paths(self) -> list[str]:
        """Return a list of warnings for paths that do not exist."""
        warnings: list[str] = []
        for field_name in ("dsno_directory", "control_sheet"):
            path = getattr(self, field_name)
            if path != Path() and not path.exists():
                warnings.append(f"Path for '{field_name}' not found: {path}")
        return warnings


def save_config(config: AppConfig, path: Path | str | None = None) -> None:
    """Persist an :class:`AppConfig` instance back to the INI file.

    Args:
        config: The configuration to save.
        path: Path to the config file.  Defaults to ``config.txt`` in cwd.
    """
    config_path = Path(path) if path else Path(_DEFAULT_CONFIG_FILE)

    parser = configparser.ConfigParser()

    parser["PATHS"] = {
        "DSNO_DIRECTORY": str(config.dsno_directory),
        "CONTROL_SHEET": str(config.control_sheet),
        "CUSTOMER_SHEET": str(config.customer_sheet),
        "CUSTOMER_SHEET_PRE_PATH": str(config.customer_sheet_pre_path),
        "PROCESSOR_VALID_STATUSES": ", ".join(
            s.capitalize() for s in config.processor_valid_statuses
        ),
    }

    parser["EBS"] = {
        "EBS_DOWNLOAD_URL": config.ebs_download_url,
        "EBS_UPLOAD_URL": config.ebs_upload_url,
        "DOWNLOAD_DIR": str(config.download_dir),
        "UPLOAD_DIR": str(config.upload_dir),
        "DSNO_COL": config.ebs_dsno_col,
        "DATE_COL": config.ebs_date_col,
        "STATUS_COL": config.ebs_status_col,
        "PASTAS_INDICES": ",".join(str(i) for i in config.ebs_pastas_indices),
        "UPLOAD_PASTA_INDICE": str(config.ebs_upload_pasta_indice),
        "EMAIL": config.ebs_email,
        "PASSWORD": config.ebs_password,
    }

    with open(config_path, "w", encoding="utf-8") as fh:
        parser.write(fh)


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

    # Parse optional [EBS] section
    ebs = parser["EBS"] if "EBS" in parser else {}

    pastas_raw = ebs.get("PASTAS_INDICES", "92,95,101")
    pastas_indices = [int(x.strip()) for x in pastas_raw.split(",") if x.strip()]

    valid_statuses_raw = paths.get("PROCESSOR_VALID_STATUSES", "Downloaded")
    valid_statuses = [x.strip().lower() for x in valid_statuses_raw.split(",") if x.strip()]

    return AppConfig(
        dsno_directory=Path(paths.get("DSNO_DIRECTORY", "")),
        control_sheet=Path(paths.get("CONTROL_SHEET", "")),
        customer_sheet=Path(paths.get("CUSTOMER_SHEET", "")),
        customer_sheet_pre_path=Path(paths.get("CUSTOMER_SHEET_PRE_PATH", "")),
        ebs_download_url=ebs.get("EBS_DOWNLOAD_URL", ""),
        ebs_upload_url=ebs.get("EBS_UPLOAD_URL", ""),
        download_dir=Path(ebs.get("DOWNLOAD_DIR", "")),
        upload_dir=Path(ebs.get("UPLOAD_DIR", "")),
        ebs_dsno_col=ebs.get("DSNO_COL", "ARGUMENT2"),
        ebs_date_col=ebs.get("DATE_COL", "CREATION_DATE"),
        ebs_status_col=ebs.get("STATUS_COL", "STATUS"),
        ebs_pastas_indices=pastas_indices,
        ebs_upload_pasta_indice=int(ebs.get("UPLOAD_PASTA_INDICE", "92")),
        ebs_email=ebs.get("EMAIL", ""),
        ebs_password=ebs.get("PASSWORD", ""),
        processor_valid_statuses=valid_statuses,
    )
