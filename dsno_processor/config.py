"""Centralized configuration loading and validation.

Configuration is stored in TOML format (``config.toml``).  Legacy INI-style
``config.txt`` files are automatically migrated on first load.
"""

from __future__ import annotations

import configparser
import shutil
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import tomli_w

from .exceptions import ConfigurationError

_DEFAULT_CONFIG_TOML = "config.toml"
_LEGACY_CONFIG_TXT = "config.txt"


# ── Sub-config dataclasses ───────────────────────────────────────────


@dataclass
class PathsConfig:
    """File-system paths used by the processor."""

    dsno_directory: Path = field(default_factory=Path)
    control_sheet: Path = field(default_factory=Path)
    customer_sheet: Path = field(default_factory=Path)
    customer_sheet_pre_path: Path = field(default_factory=Path)

    def validate(self) -> list[str]:
        """Return a list of warnings for paths that do not exist."""
        warnings: list[str] = []
        for name in ("dsno_directory", "control_sheet"):
            p = getattr(self, name)
            if p != Path() and not p.exists():
                warnings.append(f"Path for '{name}' not found: {p}")
        return warnings


@dataclass
class ProcessorConfig:
    """Settings that control the DSNO processing behaviour."""

    valid_statuses: list[str] = field(default_factory=lambda: ["downloaded"])


@dataclass
class EbsColumnsConfig:
    """Column names used when reading the EBS spreadsheet."""

    dsno: str = "ARGUMENT2"
    date: str = "CREATION_DATE"
    status: str = "STATUS"


@dataclass
class EbsPastasConfig:
    """Pasta-folder indices for download / upload."""

    download_indices: list[int] = field(default_factory=lambda: [92, 95, 101])
    upload_indice: int = 92


@dataclass
class EbsConfig:
    """Oracle EBS download / upload settings."""

    download_url: str = ""
    upload_url: str = ""
    download_dir: Path = field(default_factory=Path)
    upload_dir: Path = field(default_factory=Path)
    columns: EbsColumnsConfig = field(default_factory=EbsColumnsConfig)
    pastas: EbsPastasConfig = field(default_factory=EbsPastasConfig)


@dataclass
class CredentialsConfig:
    """User credentials for EBS authentication."""

    email: str = ""
    password: str = ""


# ── Main config ──────────────────────────────────────────────────────


@dataclass
class AppConfig:
    """Typed, hierarchical representation of the application configuration.

    Sub-configs are grouped by domain:
    - ``paths``        – file-system paths
    - ``processor``    – processor behaviour
    - ``ebs``          – Oracle EBS URLs, dirs, columns, pastas
    - ``credentials``  – user credentials
    """

    paths: PathsConfig = field(default_factory=PathsConfig)
    processor: ProcessorConfig = field(default_factory=ProcessorConfig)
    ebs: EbsConfig = field(default_factory=EbsConfig)
    credentials: CredentialsConfig = field(default_factory=CredentialsConfig)

    # ── Backward-compatible property aliases ─────────────────────
    # These allow existing code to keep using ``cfg.dsno_directory`` etc.

    @property
    def dsno_directory(self) -> Path:
        return self.paths.dsno_directory

    @property
    def control_sheet(self) -> Path:
        return self.paths.control_sheet

    @property
    def customer_sheet(self) -> Path:
        return self.paths.customer_sheet

    @property
    def customer_sheet_pre_path(self) -> Path:
        return self.paths.customer_sheet_pre_path

    @property
    def processor_valid_statuses(self) -> list[str]:
        return self.processor.valid_statuses

    @property
    def ebs_download_url(self) -> str:
        return self.ebs.download_url

    @property
    def ebs_upload_url(self) -> str:
        return self.ebs.upload_url

    @property
    def download_dir(self) -> Path:
        return self.ebs.download_dir

    @property
    def upload_dir(self) -> Path:
        return self.ebs.upload_dir

    @property
    def ebs_dsno_col(self) -> str:
        return self.ebs.columns.dsno

    @property
    def ebs_date_col(self) -> str:
        return self.ebs.columns.date

    @property
    def ebs_status_col(self) -> str:
        return self.ebs.columns.status

    @property
    def ebs_pastas_indices(self) -> list[int]:
        return self.ebs.pastas.download_indices

    @property
    def ebs_upload_pasta_indice(self) -> int:
        return self.ebs.pastas.upload_indice

    @property
    def ebs_email(self) -> str:
        return self.credentials.email

    @property
    def ebs_password(self) -> str:
        return self.credentials.password

    def validate_paths(self) -> list[str]:
        """Delegate to :class:`PathsConfig`."""
        return self.paths.validate()


# ── Serialization helpers ────────────────────────────────────────────


def _config_to_dict(config: AppConfig) -> dict:
    """Convert an :class:`AppConfig` into a TOML-friendly nested dict."""
    return {
        "paths": {
            "dsno_directory": str(config.paths.dsno_directory),
            "control_sheet": str(config.paths.control_sheet),
            "customer_sheet": str(config.paths.customer_sheet),
            "customer_sheet_pre_path": str(config.paths.customer_sheet_pre_path),
        },
        "processor": {
            "valid_statuses": [
                s.capitalize() for s in config.processor.valid_statuses
            ],
        },
        "ebs": {
            "download_url": config.ebs.download_url,
            "upload_url": config.ebs.upload_url,
            "download_dir": str(config.ebs.download_dir),
            "upload_dir": str(config.ebs.upload_dir),
            "columns": {
                "dsno": config.ebs.columns.dsno,
                "date": config.ebs.columns.date,
                "status": config.ebs.columns.status,
            },
            "pastas": {
                "download_indices": config.ebs.pastas.download_indices,
                "upload_indice": config.ebs.pastas.upload_indice,
            },
        },
        "credentials": {
            "email": config.credentials.email,
            "password": config.credentials.password,
        },
    }


def _dict_to_config(data: dict) -> AppConfig:
    """Build an :class:`AppConfig` from a parsed TOML dict."""
    paths_d = data.get("paths", {})
    proc_d = data.get("processor", {})
    ebs_d = data.get("ebs", {})
    cols_d = ebs_d.get("columns", {})
    pastas_d = ebs_d.get("pastas", {})
    cred_d = data.get("credentials", {})

    valid_raw = proc_d.get("valid_statuses", ["Downloaded"])
    valid_statuses = [s.strip().lower() for s in valid_raw if s.strip()]

    return AppConfig(
        paths=PathsConfig(
            dsno_directory=Path(paths_d.get("dsno_directory", "")),
            control_sheet=Path(paths_d.get("control_sheet", "")),
            customer_sheet=Path(paths_d.get("customer_sheet", "")),
            customer_sheet_pre_path=Path(
                paths_d.get("customer_sheet_pre_path", "")
            ),
        ),
        processor=ProcessorConfig(valid_statuses=valid_statuses),
        ebs=EbsConfig(
            download_url=ebs_d.get("download_url", ""),
            upload_url=ebs_d.get("upload_url", ""),
            download_dir=Path(ebs_d.get("download_dir", "")),
            upload_dir=Path(ebs_d.get("upload_dir", "")),
            columns=EbsColumnsConfig(
                dsno=cols_d.get("dsno", "ARGUMENT2"),
                date=cols_d.get("date", "CREATION_DATE"),
                status=cols_d.get("status", "STATUS"),
            ),
            pastas=EbsPastasConfig(
                download_indices=pastas_d.get(
                    "download_indices", [92, 95, 101]
                ),
                upload_indice=pastas_d.get("upload_indice", 92),
            ),
        ),
        credentials=CredentialsConfig(
            email=cred_d.get("email", ""),
            password=cred_d.get("password", ""),
        ),
    )


# ── Legacy INI migration ────────────────────────────────────────────


def _migrate_ini_to_toml(
    ini_path: Path,
    toml_path: Path,
) -> AppConfig:
    """Read a legacy ``config.txt`` (INI) and write ``config.toml``.

    Creates a ``.bak`` backup of the original INI file.

    Returns:
        The loaded :class:`AppConfig`.
    """
    parser = configparser.ConfigParser()
    parser.read(str(ini_path), encoding="utf-8")

    paths_sec = parser["PATHS"] if "PATHS" in parser else {}
    ebs_sec = parser["EBS"] if "EBS" in parser else {}

    pastas_raw = ebs_sec.get("PASTAS_INDICES", "92,95,101")
    pastas_indices = [
        int(x.strip()) for x in pastas_raw.split(",") if x.strip()
    ]

    valid_raw = paths_sec.get("PROCESSOR_VALID_STATUSES", "Downloaded")
    valid_statuses = [
        x.strip().lower() for x in valid_raw.split(",") if x.strip()
    ]

    config = AppConfig(
        paths=PathsConfig(
            dsno_directory=Path(paths_sec.get("DSNO_DIRECTORY", "")),
            control_sheet=Path(paths_sec.get("CONTROL_SHEET", "")),
            customer_sheet=Path(paths_sec.get("CUSTOMER_SHEET", "")),
            customer_sheet_pre_path=Path(
                paths_sec.get("CUSTOMER_SHEET_PRE_PATH", "")
            ),
        ),
        processor=ProcessorConfig(valid_statuses=valid_statuses),
        ebs=EbsConfig(
            download_url=ebs_sec.get("EBS_DOWNLOAD_URL", ""),
            upload_url=ebs_sec.get("EBS_UPLOAD_URL", ""),
            download_dir=Path(ebs_sec.get("DOWNLOAD_DIR", "")),
            upload_dir=Path(ebs_sec.get("UPLOAD_DIR", "")),
            columns=EbsColumnsConfig(
                dsno=ebs_sec.get("DSNO_COL", "ARGUMENT2"),
                date=ebs_sec.get("DATE_COL", "CREATION_DATE"),
                status=ebs_sec.get("STATUS_COL", "STATUS"),
            ),
            pastas=EbsPastasConfig(
                download_indices=pastas_indices,
                upload_indice=int(
                    ebs_sec.get("UPLOAD_PASTA_INDICE", "92")
                ),
            ),
        ),
        credentials=CredentialsConfig(
            email=ebs_sec.get("EMAIL", ""),
            password=ebs_sec.get("PASSWORD", ""),
        ),
    )

    # Write the new TOML file
    save_config(config, toml_path)

    # Backup the old INI
    backup = ini_path.with_suffix(".txt.bak")
    shutil.copy2(ini_path, backup)

    return config


# ── Public API ───────────────────────────────────────────────────────


def save_config(config: AppConfig, path: Path | str | None = None) -> None:
    """Persist an :class:`AppConfig` instance to a TOML file.

    Args:
        config: The configuration to save.
        path: Path to the config file.  Defaults to ``config.toml`` in cwd.
    """
    config_path = Path(path) if path else Path(_DEFAULT_CONFIG_TOML)
    data = _config_to_dict(config)

    with open(config_path, "wb") as fh:
        tomli_w.dump(data, fh)


def load_config(path: Path | str | None = None) -> AppConfig:
    """Load configuration from a TOML file.

    If the TOML file does not exist but a legacy ``config.txt`` does, the
    INI file is automatically migrated.

    Args:
        path: Path to the config file. Defaults to ``config.toml`` in cwd.

    Returns:
        A validated :class:`AppConfig` instance.

    Raises:
        ConfigurationError: If neither the TOML nor legacy INI file exists.
    """
    config_path = Path(path) if path else Path(_DEFAULT_CONFIG_TOML)

    # ── Auto-migrate legacy INI ──────────────────────────────────
    if not config_path.exists():
        legacy = config_path.parent / _LEGACY_CONFIG_TXT
        if legacy.exists():
            return _migrate_ini_to_toml(legacy, config_path)

        raise ConfigurationError(
            f"Configuration file not found: {config_path}"
        )

    # ── Read TOML ────────────────────────────────────────────────
    with open(config_path, "rb") as fh:
        data = tomllib.load(fh)

    return _dict_to_config(data)
