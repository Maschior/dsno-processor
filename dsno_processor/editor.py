"""DSNO file editor — reads/writes fixed-format text files."""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

from unidecode import unidecode

from .exceptions import DsnoFileError
from .models import DsnoInfo

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Low-level field editing
# ---------------------------------------------------------------------------

_ENCODING_FALLBACK = ("latin-1", "utf-8")


def _read_lines(filepath: Path) -> list[str]:
    """Read all lines from *filepath*, trying multiple encodings."""
    for enc in _ENCODING_FALLBACK:
        try:
            return filepath.read_text(encoding=enc).splitlines(keepends=True)
        except UnicodeDecodeError:
            continue
    raise DsnoFileError(f"Unable to decode file with any encoding: {filepath}")


def _write_lines(filepath: Path, lines: list[str]) -> None:
    """Write *lines* back to *filepath*, trying multiple encodings."""
    text = "".join(lines)
    for enc in _ENCODING_FALLBACK:
        try:
            filepath.write_text(text, encoding=enc)
            return
        except UnicodeEncodeError:
            continue
    raise DsnoFileError(f"Unable to encode file with any encoding: {filepath}")


def edit_field(
    filepath: Path,
    regex_line: str,
    col_start: int,
    col_end: int,
    new_content: str,
    success_message: str = "",
) -> bool:
    """Replace a fixed-width field on every line matching *regex_line*.

    Args:
        filepath: Path to the fixed-format text file.
        regex_line: Regex pattern to identify target lines.
        col_start: Starting column (1-based, inclusive).
        col_end: Ending column (1-based, inclusive).
        new_content: Replacement text (padded/truncated to fit).
        success_message: Optional message logged on success.

    Returns:
        ``True`` if at least one line was modified.

    Raises:
        DsnoFileError: If the file does not exist.
    """
    if not filepath.exists():
        raise DsnoFileError(f"File not found: {filepath}")

    if col_start > col_end or col_start < 1:
        raise ValueError(
            f"Invalid column range: col_start={col_start}, col_end={col_end}"
        )

    start_idx = col_start - 1
    end_idx = col_end
    target_length = col_end - col_start + 1
    adjusted_content = new_content.ljust(target_length)[:target_length]

    original_lines = _read_lines(filepath)
    modified_lines: list[str] = []
    occurrences = 0

    for line in original_lines:
        if re.search(regex_line, line):
            occurrences += 1
            clean_line = line.rstrip("\n\r").ljust(end_idx)
            new_line = clean_line[:start_idx] + adjusted_content + clean_line[end_idx:]
            modified_lines.append(new_line + "\n")
        else:
            modified_lines.append(line)

    if occurrences == 0:
        log.warning("No line matching regex '%s' in %s", regex_line, filepath.name)
        return False

    _write_lines(filepath, modified_lines)
    if success_message:
        log.info(success_message)
    return True


# ---------------------------------------------------------------------------
# High-level DSNO field editors
# ---------------------------------------------------------------------------

_REGEX_1000 = "                                                        1000"
_REGEX_1010 = "                                                        1010"


def edit_waybill_number(filepath: Path, value: str) -> bool:
    return edit_field(
        filepath, _REGEX_1000, 206, 235, value,
        success_message=f"BOOKING inserted: {value}",
    )


def edit_bill_of_lading(filepath: Path, value: str) -> bool:
    return edit_field(
        filepath, _REGEX_1000, 236, 265, value,
        success_message=f"INVOICE inserted: {value}",
    )


def edit_equip_number(filepath: Path, value: str) -> bool:
    return edit_field(
        filepath, _REGEX_1010, 111, 130, value,
        success_message=f"CONTAINER inserted: {value}",
    )


def edit_equip_type_ext1(filepath: Path) -> bool:
    return edit_field(filepath, _REGEX_1010, 296, 297, "TL")


# ---------------------------------------------------------------------------
# Composite operations
# ---------------------------------------------------------------------------


def edit_navstar_dsno(dsno_path: Path, info: DsnoInfo) -> bool:
    """Apply all required edits to a single DSNO file.

    Returns ``True`` if any field was modified.
    """
    results = [
        edit_waybill_number(dsno_path, info.booking),
        edit_bill_of_lading(dsno_path, info.invoice),
        edit_equip_number(dsno_path, info.container),
        edit_equip_type_ext1(dsno_path),
        normalize_file(dsno_path),
    ]
    return any(results)


def normalize_file(filepath: Path) -> bool:
    """Replace accented characters with their ASCII equivalents."""
    if not filepath.exists():
        raise DsnoFileError(f"File not found for normalization: {filepath}")

    try:
        lines = filepath.read_text(encoding="utf-8").splitlines(keepends=True)
        normalized = [unidecode(line) for line in lines]
        filepath.write_text("".join(normalized), encoding="utf-8")
        return True
    except (UnicodeDecodeError, UnicodeEncodeError) as exc:
        log.error("Normalization failed for %s: %s", filepath.name, exc)
        return False


def move_to_processed(filepath: Path, processed_dir: Path) -> bool:
    """Move a processed DSNO file to the *processed_dir* folder.

    Uses :func:`shutil.move` for an atomic operation instead of the
    previous read→write→delete pattern.

    Returns ``True`` on success.
    """
    if not filepath.exists():
        raise DsnoFileError(f"File not found for moving: {filepath}")

    processed_dir.mkdir(parents=True, exist_ok=True)
    destination = processed_dir / filepath.name

    try:
        shutil.move(str(filepath), str(destination))
        log.info("Processed DSNO moved to: %s", destination)
        return True
    except OSError as exc:
        log.error("Failed to move DSNO file %s: %s", filepath.name, exc)
        return False
