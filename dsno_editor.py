import os
import re
import logging
from pathlib import Path
from get_dsno_info import get_dsno_info
from unidecode import unidecode

log = logging.getLogger(__name__)

def edit_field(filepath: str, regex_line: str, col_start: int, col_end: int, new_content: str, success_string: str = ""):
    """
    Reads a fixed-format text file, finds lines that match a regex,
    and replaces the content between the specified columns, preserving the line structure.

    Args:
        filepath (str): The path to the input file.
        regex_line (str): The regular expression to find the line(s) to be modified.
        col_start (int): The starting column for the replacement (1-based, inclusive).
        col_end (int): The ending column for the replacement (1-based, inclusive).
        new_content (str): The new text to be inserted.
        success_string (str): Message to log on success.
    """
    # --- Parameter Validation ---
    path = Path(filepath)
    if not path.exists():
        log.error(f"Error: The file '{filepath}' was not found.")
        return False

    if col_start > col_end:
        log.error("Error: The starting column cannot be greater than the ending column.")
        return False
    
    if col_start < 1:
        log.error("Error: The starting column must be 1 or greater.")
        return False

    # --- Preparation for Editing ---
    # Python uses 0-based indices. Column 1 is index 0.
    start_index = col_start - 1
    # Python slicing goes up to, but does not include, the end index.
    # To include col_end, the slice index must be col_end.
    end_index = col_end

    # Calculate the exact length of the field that will be replaced.
    target_length = col_end - col_start + 1

    # **CRUCIAL LOGIC TO MAINTAIN STRUCTURE**
    # Adjust the new content to fit EXACTLY in the defined space.
    # 1. .ljust(): Fills with spaces on the right if the content is short.
    # 2. [:target_length]: Truncates the content if it's long.
    adjusted_content = new_content.ljust(target_length)[:target_length]
    
    modified_lines = []
    occurrences = 0
    
    try:
        with open(filepath, 'r', encoding='latin-1') as f:
            original_lines = f.readlines()
    except UnicodeDecodeError:
        with open(filepath, 'r', encoding='utf-8') as f:
            original_lines = f.readlines()

    # --- File Processing ---
    for i, line in enumerate(original_lines):
        if re.search(regex_line, line):
            occurrences += 1
            clean_original_line = line.rstrip('\n\r')

            # Ensure the line has the minimum length for editing, padding with spaces.
            # This avoids 'index out of range' errors on short lines.
            padded_line = clean_original_line.ljust(end_index)

            # **LINE REASSEMBLY LOGIC**
            # 1. Get the part of the line BEFORE the field to be edited.
            part_before = padded_line[:start_index]
            # 2. Get the part of the line AFTER the field to be edited.
            part_after = padded_line[end_index:]
            
            # 3. Build the new line, ensuring nothing moves.
            new_line = part_before + adjusted_content + part_after
            
            modified_lines.append(new_line + '\n')
        else:
            modified_lines.append(line)

    # --- Saving the Result ---
    if occurrences > 0:
        try:
            with open(filepath, 'w', encoding='latin-1') as f:
                f.writelines(modified_lines)
        except UnicodeEncodeError:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.writelines(modified_lines)
                
        if success_string:
            log.info(success_string)
        return True
    else:
        msg = f"Error: No line matching the regex '{regex_line}' was found in {filepath}."
        log.warning(msg)
        return False

def edit_waybill_number(filepath: str, value: str) -> bool:
    return edit_field(
        filepath=filepath, 
        regex_line="                                                        1000",
        col_start=206,
        col_end=235,
        new_content=value,
        success_string=f"BOOKING inserted: {value}"
    )

def edit_bill_of_lading(filepath: str, value: str) -> bool:
    return edit_field(
        filepath=filepath, 
        regex_line="                                                        1000",
        col_start=236,
        col_end=265,
        new_content=value,
        success_string=f"INVOICE inserted: {value}"
    )
    
def edit_equip_number(filepath: str, value: str) -> bool:
    return edit_field(
        filepath=filepath, 
        regex_line="                                                        1010",
        col_start=111,
        col_end=130,
        new_content=value,
        success_string=f"CONTAINER inserted: {value}"
    )
    
def edit_equip_type_ext1(filepath: str) -> bool:
    return edit_field(
        filepath=filepath, 
        regex_line="                                                        1010",
        col_start=296,
        col_end=297,
        new_content="TL"
    )

def normalize_text(filepath: str) -> bool:
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            for line in f:
                line = unidecode(line)
                f.write(line)
        return True
    except UnicodeEncodeError:
        try:
            with open(filepath, 'w', encoding='latin-1') as f:
                for line in f:
                    line = unidecode(line)
                    f.write(line)
            return True
        except Exception:
            log.error("Error: Could not normalize text (function: normalize_text, document: dsno_editor.py, line: 142)")
            return False

def edit_navstar_dsno(dsno_path: str, booking: str, invoice: str, container: str) -> bool:
    r1 = edit_waybill_number(dsno_path, booking)
    r2 = edit_bill_of_lading(dsno_path, invoice)
    r3 = edit_equip_number(dsno_path, container)
    r4 = edit_equip_type_ext1(dsno_path)
    r5 = normalize_text(dsno_path)
    return any([r1, r2, r3, r4, r5])

def process_single_dsno(invoice: str, dsno_path: str, customer_sheet_path: str) -> bool:
    """
    Main orchestrator for editing a single DSNO file.
    Returns True if successful, False otherwise.
    """
    dsno_info = get_dsno_info(
        invoice=int(invoice),
        customer_sheet_path=customer_sheet_path
    )
    
    if dsno_info:
        container = dsno_info.get("Container")
        booking = dsno_info.get("Booking/HAWB")
        
        if not container or container.strip() == "nan":
            container = 'AIR FREIGHT'
        
        if container and booking and booking.strip() != "nan":
            edit_navstar_dsno(
                dsno_path=dsno_path,
                invoice=invoice,
                container=container,
                booking=booking, 
            )
            
            
            return True
    return False