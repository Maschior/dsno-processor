"""Update the STATUS column in the internal control sheet."""

from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path

import openpyxl

log = logging.getLogger(__name__)

def update_control_sheet_status(
    control_sheet_path: Path | str,
    processed_dir: Path | str,
) -> int:
    """Read the control sheet and update STATUS to 'Processed'.

    Checks if the DSNO (from the ARGUMENT2 column) is physically present
    in the `processed_dir`. If so, updates its STATUS column.

    Args:
        control_sheet_path: Path to the Excel control sheet.
        processed_dir: Path to the Processed directory.

    Returns:
        The number of rows updated.
    """
    cs_path = Path(control_sheet_path)
    pd_path = Path(processed_dir)

    if not cs_path.exists():
        log.error("Control sheet not found for status update at %s", cs_path)
        return 0

    if not pd_path.exists():
        log.error("Processed directory not found at %s", pd_path)
        return 0

    processed_files = {f.name for f in pd_path.iterdir() if f.is_file()}
    if not processed_files:
        log.info("No files in Processed directory. Skipping status update.")
        return 0

    log.info("Updating STATUS column in control sheet: %s", cs_path.name)
    
    try:
        backup_dir = cs_path.parent / "control_sheet_backups"
        backup_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"{cs_path.stem}_{timestamp}{cs_path.suffix}"
        backup_path = backup_dir / backup_filename
        shutil.copy2(cs_path, backup_path)
        log.info("Created backup of control sheet at %s", backup_path)
    except Exception as exc:
        log.error("Failed to create control sheet backup: %s", exc)
        return 0

    try:
        wb = openpyxl.load_workbook(cs_path)
        ws = wb.active

        header_row = 1
        dsno_col_idx = None
        status_col_idx = None

        # Find columns
        for col_idx in range(1, ws.max_column + 1):
            cell_val = ws.cell(row=header_row, column=col_idx).value
            if cell_val is not None:
                col_name = str(cell_val).strip().upper()
                if col_name == "ARGUMENT2":
                    dsno_col_idx = col_idx
                elif col_name == "STATUS":
                    status_col_idx = col_idx

        if dsno_col_idx is None:
            log.error("Column 'ARGUMENT2' (DSNO) not found in control sheet.")
            return 0

        if status_col_idx is None:
            # Add STATUS column if missing
            status_col_idx = ws.max_column + 1
            ws.cell(row=header_row, column=status_col_idx, value="STATUS")
            log.info("Added 'STATUS' column to control sheet.")

        updates_made = 0
        for row_idx in range(2, ws.max_row + 1):
            dsno_val = ws.cell(row=row_idx, column=dsno_col_idx).value
            if dsno_val:
                dsno_name = str(dsno_val).strip()
                if dsno_name in processed_files:
                    current_status = ws.cell(row=row_idx, column=status_col_idx).value
                    if current_status != "Processed":
                        ws.cell(row=row_idx, column=status_col_idx, value="Processed")
                        updates_made += 1

        if updates_made > 0:
            wb.save(cs_path)
            log.info("Updated STATUS to 'Processed' for %d rows.", updates_made)
        else:
            log.info("No new rows required STATUS update.")

        return updates_made
    except PermissionError as exc:
        log.error("Permission error while updating control sheet: %s", exc)
        log.error("Please close the control sheet if it is open and try again.")
        return 0
    except Exception as exc:
        log.exception("Failed to update status in control sheet: %s", exc)
        return 0
