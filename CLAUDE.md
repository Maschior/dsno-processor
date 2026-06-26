# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the app (CustomTkinter GUI by default)
py main.py                        # Windows
python main.py                    # Linux/macOS

# Run the alternative pywebview web UI (React)
py main.py --web                  # loads frontend/dist (run the build first)

# Build the web UI (required before `--web` outside dev mode)
cd frontend && npm install && npm run build
# Web UI dev mode (Vite hot-reload):
cd frontend && npm run dev        # then, in another shell:
DSNO_WEB_DEV=1 py main.py --web    # DSNO_WEB_DEBUG=1 also enables WebView2 DevTools

# Run all tests
pytest tests/

# Run a single test file
pytest tests/test_processor.py

# Build standalone executable (Windows, requires Inno Setup 6)
python scripts/build_all.py

# Build with PyInstaller directly
pyinstaller main.spec --clean --noconfirm
```

Config lives in `config.toml` (copy from `config.toml.example`). Legacy `config.txt` (INI format) is auto-migrated on first load. If no config exists, `load_config()` writes a complete default file instead of raising.

## Architecture

**Two-layer layout:** `dsno_processor/` is the domain/backend package; `gui/` (CustomTkinter) and `frontend/` + `webui/` (pywebview + React) are two interchangeable presentation layers over the same domain. `app.py` is the composition root — it wires the GUI by default, or the web UI when launched with `--web`.

### Domain package (`dsno_processor/`)

| Module | Role |
|---|---|
| `processor.py` | Main public API — `process_dsno()` is the single entry point called by the GUI |
| `config.py` | TOML config loading/saving; `AppConfig` is the typed config dataclass with backward-compat property aliases |
| `models.py` | `FreightMode`, `DateRange`, `DsnoInfo`, `ProcessingResult` |
| `database.py` | SQLite layer (`tb_control`, `tb_shipment_info`). Mirrors the spreadsheet data model and can fully replace it. `insert_control_if_absent()` inserts a control row only if its DSNO is new, preserving the existing status |
| `oracle_source.py` | Step-1 sync: pulls the last `oracle.lookback_months` of pending DSNOs for `oracle.customer_id` from the Oracle EBS DB (`python-oracledb`, thin mode) and inserts the *new* ones into `tb_control`. Existing records are never touched |
| `editor.py` | Mutates DSNO files on disk; `edit_navstar_dsno()` writes booking/container into the file |
| `control_reader.py` | Reads the Control Sheet Excel file; yields `(invoice, dsno_filename, freight_oracle, freight_softway)` tuples |
| `customer_reader.py` | Reads the Customer Sheet Excel file; looks up `DsnoInfo` by invoice number |
| `ebs_download.py` / `ebs_upload.py` | Selenium automation against Oracle EBS |
| `status_updater.py` | Writes "Processed"/"Downloaded" status back to the Control Sheet and DB after a run |
| `i18n.py` | `t(key, **kwargs)` — thin i18n wrapper; language set in config |

**Data source duality:** `config.general.data_source` is either `"spreadsheet"` (default) or `"database"`. The processor and EBS modules branch on this to read from Excel or SQLite respectively. Both paths produce the same tuple shape.

**Oracle source (`config.oracle`):** connection (`user`, `password`, `dsn`, `customer_id`, `lookback_months`) for the upstream Oracle EBS database. This is distinct from `config.credentials` (the EBS *web* login used by the Selenium download/upload) and from the internal SQLite DB. Only `oracle_source.py` and the web UI's "Pendências" step use it.

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

### Web UI package (`frontend/` + `webui/`)

Alternative front end launched with `py main.py --web`. `frontend/` is a React app (Vite, no router — a single `App.jsx`) styled with the Resolva design tokens in `frontend/src/styles.css`. `webui/api.py` (`Api` class) is the web-UI equivalent of `app_presenter.py`: every public method is auto-exposed to JS as `pywebview.api.<name>()`. Heavy operations (process/download/upload) run in daemon threads and stream `(event, data)` progress to JS via `window.__onProgress`; fast data ops (`import_*_to_db`, `sync_status`, `sync_oracle_pending`) are synchronous and return counts straight to the calling promise. No HTTP server, no Node at runtime — the packaged build renders `frontend/dist`.

The tabs are ordered to mirror the real workflow: **1 Pendências** (Oracle step-1 sync) → **2 Download** (+ "mark Downloaded" status sync) → **3 Processar** (data-source-aware: import customer/control sheets to DB in `database` mode) → **4 Upload** (+ reserved "mark Sent"). The CustomTkinter GUI keeps its original tab order and surfaces the same data actions as buttons on the Processor tab; the two front ends share the domain but are not kept pixel-identical.

### Key design constraints

- The file-size-unchanged check after editing (`BYPASS_FILE_SIZE_CHECK`) exists because editing failures are silent — if the file didn't grow, the edit likely did nothing.
- `KEEP_ORIGINAL` copies before editing and moves the original to `Processed/original_files/` on success (vs. the default which moves the file directly).
- `CanceledError` propagates up from the domain when `cancel_event.is_set()` — the GUI catches it and sets the dashboard to a cancelled state.
