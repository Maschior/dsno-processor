"""Tests for dsno_processor.config."""

from __future__ import annotations

import configparser
from pathlib import Path

import pytest
import tomli_w

from dsno_processor.config import (
    AppConfig,
    ControlSheetColsConfig,
    CredentialsConfig,
    CustomerSheetColsConfig,
    CustomerSheetPropertiesConfig,
    EbsConfig,
    EbsFoldersConfig,
    GeneralConfig,
    PathsConfig,
    _config_to_dict,
    _dict_to_config,
    _migrate_ini_to_toml,
    load_config,
    save_config,
)
from dsno_processor.exceptions import ConfigurationError


# ── Helpers ──────────────────────────────────────────────────────────


def _make_config(**overrides) -> AppConfig:
    """Build an AppConfig with sensible defaults, accepting keyword overrides."""
    cfg = AppConfig()
    for attr, val in overrides.items():
        setattr(cfg, attr, val)
    return cfg


# ── Round-trip tests ─────────────────────────────────────────────────


class TestSaveLoadRoundTrip:
    """save_config → load_config should preserve all values."""

    def test_round_trip(self, tmp_path: Path):
        cfg = AppConfig(
            general=GeneralConfig(language="pt"),
            paths=PathsConfig(
                dsno_directory=Path("C:/data/dsno"),
                control_sheet=Path("C:/data/control.xlsx"),
                customer_sheet=Path("C:/data/customer.xlsx"),
                customer_sheet_pre_path=Path("C:/data"),
            ),
            control_sheet_cols=ControlSheetColsConfig(
                invoice="INV",
                dsno="DSNO_COL",
                date="DT",
                status="ST",
                freight_oracle="FO",
                freight_softway="FS",
            ),
            customer_sheet_cols=CustomerSheetColsConfig(
                invoice="Inv",
                booking="Book",
                container="Cnt",
            ),
            customer_sheet_properties=CustomerSheetPropertiesConfig(
                sheet_name="Sheet2",
            ),
            ebs=EbsConfig(
                download_url="https://dl.example.com",
                upload_url="https://ul.example.com",
                download_dir=Path("C:/dl"),
                upload_dir=Path("C:/ul"),
                headless=True,
                folders=EbsFoldersConfig(
                    download_indices=[10, 20],
                    upload_index=30,
                ),
            ),
            credentials=CredentialsConfig(
                email="user@co.com",
                password="p@ss",
            ),
        )

        toml_path = tmp_path / "config.toml"
        save_config(cfg, toml_path)
        loaded = load_config(toml_path)

        assert loaded.language == "pt"
        assert loaded.dsno_directory == Path("C:/data/dsno")
        assert loaded.control_sheet == Path("C:/data/control.xlsx")
        assert loaded.DSNO_COL == "DSNO_COL"
        assert loaded.CONTROL_INVOICE_COL == "INV"
        assert loaded.DATE_COL == "DT"
        assert loaded.STATUS_COL == "ST"
        assert loaded.FREIGHT_ORACLE_COL == "FO"
        assert loaded.FREIGHT_SOFTWAY_COL == "FS"
        assert loaded.INVOICE_COL == "Inv"
        assert loaded.BOOKING_COL == "Book"
        assert loaded.CONTAINER_COL == "Cnt"
        assert loaded.CUSTOMER_SHEET_NAME == "Sheet2"
        assert loaded.ebs_download_url == "https://dl.example.com"
        assert loaded.ebs_upload_url == "https://ul.example.com"
        assert loaded.ebs_folder_indices == [10, 20]
        assert loaded.ebs_upload_folder_index == 30
        assert loaded.ebs_headless is True
        assert loaded.ebs_email == "user@co.com"
        assert loaded.ebs_password == "p@ss"

    def test_defaults_preserved(self, tmp_path: Path):
        """A default AppConfig should round-trip cleanly."""
        toml_path = tmp_path / "config.toml"
        save_config(AppConfig(), toml_path)
        loaded = load_config(toml_path)
        assert loaded.language == "en"
        assert loaded.DSNO_COL == "ARGUMENT2"
        assert loaded.ebs_folder_indices == [92, 95, 101]


# ── dict conversion tests ───────────────────────────────────────────


class TestDictConversion:
    """Tests for _config_to_dict and _dict_to_config."""

    def test_config_to_dict_structure(self):
        d = _config_to_dict(AppConfig())
        assert "general" in d
        assert "paths" in d
        assert "control_sheet" in d
        assert "customer_sheet" in d
        assert "ebs" in d
        assert "credentials" in d

    def test_dict_to_config_empty_dict(self):
        cfg = _dict_to_config({})
        assert cfg.language == "en"
        assert cfg.DSNO_COL == "ARGUMENT2"
        assert cfg.ebs_folder_indices == [92, 95, 101]

    def test_dict_to_config_partial(self):
        cfg = _dict_to_config({"general": {"language": "pt"}})
        assert cfg.language == "pt"
        # everything else gets defaults
        assert cfg.DSNO_COL == "ARGUMENT2"


# ── Property aliases ─────────────────────────────────────────────────


class TestPropertyAliases:
    """Verify backward-compatible property aliases on AppConfig."""

    def test_language_getter_setter(self):
        cfg = AppConfig()
        assert cfg.language == "en"
        cfg.language = "pt"
        assert cfg.language == "pt"
        assert cfg.general.language == "pt"

    def test_path_aliases(self):
        cfg = AppConfig(
            paths=PathsConfig(
                dsno_directory=Path("/a"),
                control_sheet=Path("/b"),
                customer_sheet=Path("/c"),
                customer_sheet_pre_path=Path("/d"),
            )
        )
        assert cfg.dsno_directory == Path("/a")
        assert cfg.control_sheet == Path("/b")
        assert cfg.customer_sheet == Path("/c")
        assert cfg.customer_sheet_pre_path == Path("/d")

    def test_ebs_aliases(self):
        cfg = AppConfig(
            ebs=EbsConfig(
                download_url="dl",
                upload_url="ul",
                download_dir=Path("/dl"),
                upload_dir=Path("/ul"),
                headless=True,
                folders=EbsFoldersConfig(
                    download_indices=[1],
                    upload_index=2,
                ),
            ),
            credentials=CredentialsConfig(email="e", password="p"),
        )
        assert cfg.ebs_download_url == "dl"
        assert cfg.ebs_upload_url == "ul"
        assert cfg.download_dir == Path("/dl")
        assert cfg.upload_dir == Path("/ul")
        assert cfg.ebs_headless is True
        assert cfg.ebs_folder_indices == [1]
        assert cfg.ebs_upload_folder_index == 2
        assert cfg.ebs_email == "e"
        assert cfg.ebs_password == "p"


# ── Validate paths ──────────────────────────────────────────────────


class TestValidatePaths:
    """Tests for PathsConfig.validate."""

    def test_no_warnings_for_defaults(self):
        cfg = AppConfig()
        assert cfg.validate_paths() == []

    def test_warns_for_nonexistent_paths(self, tmp_path: Path):
        cfg = AppConfig(
            paths=PathsConfig(
                dsno_directory=tmp_path / "nonexistent",
                control_sheet=tmp_path / "missing.xlsx",
            )
        )
        warnings = cfg.validate_paths()
        assert len(warnings) == 2


# ── load_config error path ──────────────────────────────────────────


class TestLoadConfigErrors:
    """Tests for load_config error cases."""

    def test_file_not_found(self, tmp_path: Path):
        with pytest.raises(ConfigurationError, match="not found"):
            load_config(tmp_path / "nope.toml")


# ── Legacy INI migration ────────────────────────────────────────────


class TestIniMigration:
    """Tests for _migrate_ini_to_toml."""

    def test_migration_creates_toml(self, tmp_path: Path):
        ini_path = tmp_path / "config.txt"
        ini = configparser.ConfigParser()
        ini["GENERAL"] = {"LANGUAGE": "pt"}
        ini["PATHS"] = {
            "DSNO_DIRECTORY": "C:/dsno",
            "CONTROL_SHEET": "C:/ctrl.xlsx",
            "CUSTOMER_SHEET": "C:/cust.xlsx",
            "CUSTOMER_SHEET_PRE_PATH": "C:/pre",
        }
        ini["EBS"] = {
            "EBS_DOWNLOAD_URL": "https://dl",
            "EBS_UPLOAD_URL": "https://ul",
            "DOWNLOAD_DIR": "C:/dl",
            "UPLOAD_DIR": "C:/ul",
            "DSNO_COL": "MY_DSNO",
            "DATE_COL": "MY_DATE",
            "STATUS_COL": "MY_STATUS",
            "EMAIL": "me@co.com",
            "PASSWORD": "pw",
            "PASTAS_INDICES": "10,20,30",
            "UPLOAD_PASTA_INDICE": "10",
        }
        with open(ini_path, "w", encoding="utf-8") as f:
            ini.write(f)

        toml_path = tmp_path / "config.toml"
        cfg = _migrate_ini_to_toml(ini_path, toml_path)

        assert toml_path.exists()
        assert cfg.language == "pt"
        assert cfg.ebs_download_url == "https://dl"
        assert cfg.ebs_folder_indices == [10, 20, 30]

        # Backup created
        backup = ini_path.with_suffix(".txt.bak")
        assert backup.exists()

    def test_load_config_auto_migrates(self, tmp_path: Path, monkeypatch):
        """load_config should auto-migrate if config.txt exists but config.toml doesn't."""
        ini_path = tmp_path / "config.txt"
        ini = configparser.ConfigParser()
        ini["GENERAL"] = {"LANGUAGE": "en"}
        ini["PATHS"] = {}
        ini["EBS"] = {}
        with open(ini_path, "w", encoding="utf-8") as f:
            ini.write(f)

        monkeypatch.chdir(tmp_path)
        cfg = load_config()
        assert cfg.language == "en"
        assert (tmp_path / "config.toml").exists()
