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

import tomli_w

from .exceptions import ConfigurationError

_DEFAULT_CONFIG_TOML = "config.toml"
_LEGACY_CONFIG_TXT = "config.txt"


# ── Sub-config dataclasses ───────────────────────────────────────────


@dataclass
class GeneralConfig:
    """General application preferences."""

    language: str = "en"
    data_source: str = "spreadsheet"


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
class ControlSheetColsConfig:
    """Column names used when reading the Control spreadsheet."""

    invoice: str = "INVOICE"
    dsno: str = "ARGUMENT2"
    date: str = "CREATION_DATE"
    status: str = "STATUS"
    freight_oracle: str = "FREIGHT_ORACLE"
    freight_softway: str = "FREIGHT_SOFTWAY"
    description: str = "Obs"


@dataclass
class CustomerSheetColsConfig:
    """Column names used when reading the Customer spreadsheet."""

    invoice: str = "Invoice"
    booking: str = "Booking/HAWB"
    container: str = "Container"


@dataclass
class CustomerSheetPropertiesConfig:
    """Configuration for reading the Customer spreadsheet."""

    sheet_name: str = ""


@dataclass
class EbsFoldersConfig:
    """Folder indices for download / upload."""

    download_indices: list[int] = field(default_factory=lambda: [92, 95, 101])
    upload_index: int = 92


@dataclass
class EbsConfig:
    """Oracle EBS download / upload settings."""

    download_url: str = ""
    upload_url: str = ""
    download_dir: Path = field(default_factory=Path)
    upload_dir: Path = field(default_factory=Path)
    headless: bool = False
    folders: EbsFoldersConfig = field(default_factory=EbsFoldersConfig)


@dataclass
class CredentialsConfig:
    """User credentials for EBS authentication."""

    email: str = ""
    password: str = ""


@dataclass
class ProcessorConfig:
    """Settings that control DSNO processing behaviour."""

    bypass_file_size_check: bool = False
    keep_original: bool = False


# ── Main config ──────────────────────────────────────────────────────


@dataclass
class AppConfig:
    """Typed, hierarchical representation of the application configuration.

    Sub-configs are grouped by domain:
    - ``paths``        – file-system paths
    - ``processor``    – processor behaviour
    - ``ebs``          – Oracle EBS URLs, dirs, columns, folders
    - ``credentials``  – user credentials
    """

    general: GeneralConfig = field(default_factory=GeneralConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    processor: ProcessorConfig = field(default_factory=ProcessorConfig)
    control_sheet_cols: ControlSheetColsConfig = field(
        default_factory=ControlSheetColsConfig
    )
    customer_sheet_cols: CustomerSheetColsConfig = field(
        default_factory=CustomerSheetColsConfig
    )
    customer_sheet_properties: CustomerSheetPropertiesConfig = field(
        default_factory=CustomerSheetPropertiesConfig
    )
    ebs: EbsConfig = field(default_factory=EbsConfig)
    credentials: CredentialsConfig = field(default_factory=CredentialsConfig)

    # ── Backward-compatible property aliases ─────────────────────
    # These allow existing code to keep using ``cfg.dsno_directory`` etc.

    @property
    def language(self) -> str:
        return self.general.language

    @language.setter
    def language(self, value: str) -> None:
        self.general.language = value

    @property
    def data_source(self) -> str:
        return self.general.data_source

    @data_source.setter
    def data_source(self, value: str) -> None:
        self.general.data_source = value

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
    def CUSTOMER_SHEET_NAME(self) -> str:
        return self.customer_sheet_properties.sheet_name

    @property
    def BYPASS_FILE_SIZE_CHECK(self) -> bool:
        """If True, do not fail when DSNO file size is unchanged after processing."""
        return bool(self.processor.bypass_file_size_check)

    @property
    def KEEP_ORIGINAL(self) -> bool:
        """If True, retain/keep the original DSNO file in the source directory after processing."""
        return bool(self.processor.keep_original)

    @property
    def customer_sheet_pre_path(self) -> Path:
        return self.paths.customer_sheet_pre_path

    @property
    def INVOICE_COL(self) -> str:
        """Column name for invoice number in the customer sheet."""
        return self.customer_sheet_cols.invoice

    @property
    def BOOKING_COL(self) -> str:
        """Column name for booking/HAWB in the customer sheet."""
        return self.customer_sheet_cols.booking

    @property
    def CONTAINER_COL(self) -> str:
        """Column name for container in the customer sheet."""
        return self.customer_sheet_cols.container

    @property
    def CONTROL_INVOICE_COL(self) -> str:
        """Column name for invoice number in the control sheet."""
        return self.control_sheet_cols.invoice

    @property
    def DSNO_COL(self) -> str:
        """Column name for DSNO in the control sheet."""
        return self.control_sheet_cols.dsno

    @property
    def DATE_COL(self) -> str:
        """Column name for date in the control sheet."""
        return self.control_sheet_cols.date

    @property
    def STATUS_COL(self) -> str:
        """Column name for status in the control sheet."""
        return self.control_sheet_cols.status

    @property
    def FREIGHT_ORACLE_COL(self) -> str:
        """Column name for freight_oracle in the control sheet."""
        return self.control_sheet_cols.freight_oracle

    @property
    def FREIGHT_SOFTWAY_COL(self) -> str:
        """Column name for freight_softway in the control sheet."""
        return self.control_sheet_cols.freight_softway

    @property
    def DESCRIPTION_COL(self) -> str:
        """Column name for description in the control sheet."""
        return self.control_sheet_cols.description

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

    # Aliases used by ebs_download.py / ebs_upload.py / gui.py
    @property
    def ebs_dsno_col(self) -> str:
        return self.control_sheet_cols.dsno

    @property
    def ebs_date_col(self) -> str:
        return self.control_sheet_cols.date

    @property
    def ebs_status_col(self) -> str:
        return self.control_sheet_cols.status

    @property
    def ebs_folder_indices(self) -> list[int]:
        return self.ebs.folders.download_indices

    @property
    def ebs_upload_folder_index(self) -> int:
        return self.ebs.folders.upload_index

    @property
    def ebs_headless(self) -> bool:
        return self.ebs.headless

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
        "general": {
            "language": config.general.language,
            "data_source": config.general.data_source,
        },
        "paths": {
            "dsno_directory": str(config.paths.dsno_directory),
            "control_sheet": str(config.paths.control_sheet),
            "customer_sheet": str(config.paths.customer_sheet),
            "customer_sheet_pre_path": str(config.paths.customer_sheet_pre_path),
        },
        "processor": {
            "bypass_file_size_check": bool(config.processor.bypass_file_size_check),
            "keep_original": bool(config.processor.keep_original),
        },
        "customer_sheet": {
            "cols": {
                "invoice": config.customer_sheet_cols.invoice,
                "booking": config.customer_sheet_cols.booking,
                "container": config.customer_sheet_cols.container,
            },
            "config": {
                "sheet_name": config.customer_sheet_properties.sheet_name,
            },
        },
        "control_sheet": {
            "cols": {
                "invoice": config.control_sheet_cols.invoice,
                "dsno": config.control_sheet_cols.dsno,
                "date": config.control_sheet_cols.date,
                "status": config.control_sheet_cols.status,
                "freight_oracle": config.control_sheet_cols.freight_oracle,
                "freight_softway": config.control_sheet_cols.freight_softway,
                "description": config.control_sheet_cols.description,
            },
        },
        "ebs": {
            "download_url": config.ebs.download_url,
            "upload_url": config.ebs.upload_url,
            "download_dir": str(config.ebs.download_dir),
            "upload_dir": str(config.ebs.upload_dir),
            "headless": config.ebs.headless,
            "folders": {
                "download_indices": config.ebs.folders.download_indices,
                "upload_index": config.ebs.folders.upload_index,
            },
        },
        "credentials": {
            "email": config.credentials.email,
            "password": config.credentials.password,
        },
    }


def _dict_to_config(data: dict) -> AppConfig:
    """Build an :class:`AppConfig` from a parsed TOML dict."""
    gen_d = data.get("general", {})
    paths_d = data.get("paths", {})
    proc_d = data.get("processor", {})
    cust_sheet_d = data.get("customer_sheet", {})
    cust_cols_d = cust_sheet_d.get("cols", {})
    ctrl_sheet_d = data.get("control_sheet", {})
    ctrl_cols_d = ctrl_sheet_d.get("cols", {})
    ebs_d = data.get("ebs", {})

    folders_d = ebs_d.get("folders", ebs_d.get("pastas", {}))
    cred_d = data.get("credentials", {})

    return AppConfig(
        general=GeneralConfig(
            language=gen_d.get("language", "en"),
            data_source=gen_d.get("data_source", "spreadsheet"),
        ),
        paths=PathsConfig(
            dsno_directory=Path(paths_d.get("dsno_directory", "")),
            control_sheet=Path(paths_d.get("control_sheet", "")),
            customer_sheet=Path(paths_d.get("customer_sheet", "")),
            customer_sheet_pre_path=Path(paths_d.get("customer_sheet_pre_path", "")),
        ),
        processor=ProcessorConfig(
            bypass_file_size_check=bool(proc_d.get("bypass_file_size_check", False)),
            keep_original=bool(proc_d.get("keep_original", False)),
        ),
        control_sheet_cols=ControlSheetColsConfig(
            invoice=ctrl_cols_d.get("invoice", "INVOICE"),
            dsno=ctrl_cols_d.get("dsno", "ARGUMENT2"),
            date=ctrl_cols_d.get("date", "CREATION_DATE"),
            status=ctrl_cols_d.get("status", "STATUS"),
            freight_oracle=ctrl_cols_d.get("freight_oracle", "FREIGHT_ORACLE"),
            freight_softway=ctrl_cols_d.get("freight_softway", "FREIGHT_SOFTWAY"),
            description=ctrl_cols_d.get("description", "Obs"),
        ),
        customer_sheet_cols=CustomerSheetColsConfig(
            invoice=cust_cols_d.get("invoice", "Invoice"),
            booking=cust_cols_d.get("booking", "Booking/HAWB"),
            container=cust_cols_d.get("container", "Container"),
        ),
        customer_sheet_properties=CustomerSheetPropertiesConfig(
            sheet_name=cust_sheet_d.get("config", {}).get("sheet_name", ""),
        ),
        ebs=EbsConfig(
            download_url=ebs_d.get("download_url", ""),
            upload_url=ebs_d.get("upload_url", ""),
            download_dir=Path(ebs_d.get("download_dir", "")),
            upload_dir=Path(ebs_d.get("upload_dir", "")),
            headless=ebs_d.get("headless", False),
            folders=EbsFoldersConfig(
                download_indices=folders_d.get("download_indices", [92, 95, 101]),
                upload_index=folders_d.get(
                    "upload_index",
                    folders_d.get("upload_indice", 92),
                ),
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

    general_sec = parser["GENERAL"] if "GENERAL" in parser else {}
    paths_sec = parser["PATHS"] if "PATHS" in parser else {}
    ebs_sec = parser["EBS"] if "EBS" in parser else {}

    folder_indices_raw = ebs_sec.get("PASTAS_INDICES", "92,95,101")
    folder_indices = [
        int(x.strip()) for x in folder_indices_raw.split(",") if x.strip()
    ]

    config = AppConfig(
        general=GeneralConfig(
            language=general_sec.get("LANGUAGE", "en"),
            data_source="spreadsheet",
        ),
        paths=PathsConfig(
            dsno_directory=Path(paths_sec.get("DSNO_DIRECTORY", "")),
            control_sheet=Path(paths_sec.get("CONTROL_SHEET", "")),
            customer_sheet=Path(paths_sec.get("CUSTOMER_SHEET", "")),
            customer_sheet_pre_path=Path(paths_sec.get("CUSTOMER_SHEET_PRE_PATH", "")),
        ),
        processor=ProcessorConfig(
            bypass_file_size_check=False,
        ),
        control_sheet_cols=ControlSheetColsConfig(
            invoice="INVOICE",
            dsno=ebs_sec.get("DSNO_COL", "ARGUMENT2"),
            date=ebs_sec.get("DATE_COL", "CREATION_DATE"),
            status=ebs_sec.get("STATUS_COL", "STATUS"),
            description="Obs",
        ),
        customer_sheet_cols=CustomerSheetColsConfig(
            invoice="Invoice",
            booking="Booking/HAWB",
            container="Container",
        ),
        ebs=EbsConfig(
            download_url=ebs_sec.get("EBS_DOWNLOAD_URL", ""),
            upload_url=ebs_sec.get("EBS_UPLOAD_URL", ""),
            download_dir=Path(ebs_sec.get("DOWNLOAD_DIR", "")),
            upload_dir=Path(ebs_sec.get("UPLOAD_DIR", "")),
            folders=EbsFoldersConfig(
                download_indices=folder_indices,
                upload_index=int(ebs_sec.get("UPLOAD_PASTA_INDICE", "92")),
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

        raise ConfigurationError(f"Configuration file not found: {config_path}")

    # ── Read TOML ────────────────────────────────────────────────
    with open(config_path, "rb") as fh:
        data = tomllib.load(fh)

    return _dict_to_config(data)
