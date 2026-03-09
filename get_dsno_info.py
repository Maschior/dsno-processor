import logging
import pandas as pd
from pathlib import Path
from typing import Optional, Dict

log = logging.getLogger(__name__)

def get_dsno_info(invoice: int, customer_sheet_path: str) -> Optional[Dict[str, str]]:
    path = Path(customer_sheet_path)
    if not path.exists():
        msg = f"Error: The file '{customer_sheet_path}' was not found."
        log.error(msg)
        raise FileNotFoundError(msg)
    
    df = pd.read_excel(path, sheet_name='Details')
    
    # normalize headers
    df.columns = (
        df.columns
        .str.strip()
        .str.replace(r"\s+", " ", regex=True)
    )
    
    invoice_col = "Invoice"
    container_col = "Container"
    booking_col = "Booking/HAWB"
    
    required = {invoice_col, container_col, booking_col}
    missing = required - set(df.columns)
    
    if missing:
        msg = f"Missing columns in sheet: {missing}\nWARNING: The column name might have changed. Please check the sheet headers."
        log.error(msg)
        raise KeyError(msg)
    
    # filter
    row = df.loc[df[invoice_col] == invoice, [invoice_col, container_col, booking_col]]
    
    # bypass if not found
    if row.empty:
        msg = f"Invoice {invoice} not found in sheet {customer_sheet_path}. DSNO ignored."
        log.info(msg)       
        return None
    
    row = df.loc[df[invoice_col] == invoice].head(1)
    result = row[[invoice_col, container_col, booking_col]].iloc[0].to_dict()
    result = {k: str(v) for k, v in result.items()}
    
    return result