# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the app
py main.py                        # Windows
python main.py                    # Linux/macOS

# Run all tests
pytest tests/

# Run a single test file
pytest tests/test_processor.py

# Build standalone executable (Windows, requires Inno Setup 6)
python scripts/build_all.py

# Build with PyInstaller directly
pyinstaller main.spec --clean --noconfirm
```

Config lives in `config.toml` (copy from `config.toml.example`). Legacy `config.txt` (INI format) is auto-migrated on first load.

## Architecture

**Two-layer layout:** `dsno_processor/` is the domain/backend package; `gui/` is the presentation layer. `app.py` is the composition root — it only wires the GUI.

### Domain package (`dsno_processor/`)

| Module | Role |
|---|---|
| `processor.py` | Main public API — `process_dsno()` is the single entry point called by the GUI |
| `config.py` | TOML config loading/saving; `AppConfig` is the typed config dataclass with backward-compat property aliases |
| `models.py` | `FreightMode`, `DateRange`, `DsnoInfo`, `ProcessingResult` |
| `database.py` | SQLite layer (`tb_control`, `tb_shipment_info`). Mirrors the spreadsheet data model and can fully replace it |
| `editor.py` | Mutates DSNO files on disk; `edit_navstar_dsno()` writes booking/container into the file |
| `control_reader.py` | Reads the Control Sheet Excel file; yields `(invoice, dsno_filename, freight_oracle, freight_softway)` tuples |
| `customer_reader.py` | Reads the Customer Sheet Excel file; looks up `DsnoInfo` by invoice number |
| `ebs_download.py` / `ebs_upload.py` | Selenium automation against Oracle EBS |
| `status_updater.py` | Writes "Processed"/"Downloaded" status back to the Control Sheet and DB after a run |
| `i18n.py` | `t(key, **kwargs)` — thin i18n wrapper; language set in config |

**Data source duality:** `config.general.data_source` is either `"spreadsheet"` (default) or `"database"`. The processor and EBS modules branch on this to read from Excel or SQLite respectively. Both paths produce the same tuple shape.

**Freight resolution (`_resolve_freight`):** AIR mode prefers Softway freight; SEA mode prefers Softway only when it differs from Oracle. There is a hardcoded typo fix (`MARITMO` → `MARITIMA`) that reflects a data entry error in the source database.

**Processing flow (`process_dsno`):**
1. Read control data (spreadsheet or DB) → `(invoice, dsno_file, freight_oracle, freight_softway)` pairs filtered by date range and optional status
2. For each pair: look up shipment info (DB first, then customer sheet), resolve freight, copy file if `KEEP_ORIGINAL`, call `edit_navstar_dsno()`, validate file size changed
3. Move processed files to `<dsno_dir>/Processed/`
4. Update statuses in both spreadsheet and DB

### GUI package (`gui/`)

Built with **CustomTkinter**. Entry point is `start_gui()` → `DSNOApp` (main window).

`gui/presenters/app_presenter.py` — `AppPresenterMixin` holds all the business logic glue: browse dialogs, thread management, progress callback routing. Long-running operations (processing, EBS download/upload) run in daemon threads; UI updates are marshalled back to the Tk main thread via `_run_on_ui_thread()`.

Progress events flow as `(event_name, data_dict)` from the domain into the GUI `Dashboard` widget, which displays per-file success/error rows in real time.

Three tabs: **Processor** (batch DSNO editing), **EBS Download** (Selenium download from Oracle EBS), **EBS Upload** (Selenium upload to Oracle EBS).

### Key design constraints

- The file-size-unchanged check after editing (`BYPASS_FILE_SIZE_CHECK`) exists because editing failures are silent — if the file didn't grow, the edit likely did nothing.
- `KEEP_ORIGINAL` copies before editing and moves the original to `Processed/original_files/` on success (vs. the default which moves the file directly).
- `CanceledError` propagates up from the domain when `cancel_event.is_set()` — the GUI catches it and sets the dashboard to a cancelled state.
