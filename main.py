from datetime import datetime
from pathlib import Path
import logging


from dsno_editor import process_single_dsno
from get_invoice_dsno import get_invoice_dsno

def setup_logger_file() -> logging.Logger:
    current_datetime = datetime.now().strftime("%d%m%Y_%H%M")
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_filename = log_dir / f"log_{current_datetime}.txt"
    
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    formatter = logging.Formatter("%(levelname)s: %(message)s")
    file_handler.setFormatter(formatter)
    
    # Get root logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    
    return logging.getLogger(__name__)

def process_dsno(date_range: str, customer_sheet: str, control_sheet: str, dsno_dir: str):
    """
    Main business orchestration logic.
    """
    log = setup_logger_file()
    log.info("Starting processing...")
    log.info(f"Customer Sheet: {customer_sheet}")
    log.info(f"Control Sheet: {control_sheet}")
    log.info(f"Date Range: {date_range}")
    log.info(f"DSNO Target Directory: {dsno_dir}")
    
    invoice, dsnos = get_invoice_dsno(
        date_range=date_range, 
        internal_control_sheet_path=control_sheet
    )
    
    base_dir = Path(dsno_dir)
    dsno_paths = [str(base_dir / dsno) for dsno in dsnos]
    
    count = 0
    for inv, dsno_path in zip(invoice, dsno_paths):
        filename = Path(dsno_path).name
        log.info(f"---- Processing DSNO: {filename} ----")         
        if process_single_dsno(str(inv), dsno_path, customer_sheet):
            count += 1
            
    log.info(f"Processed {count} invoices.")
    return count

if __name__ == "__main__":
    import gui
    gui.start_gui()
