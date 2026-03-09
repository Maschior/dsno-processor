import logging
import pandas as pd
from pathlib import Path
from typing import List, Tuple

log = logging.getLogger(__name__)
DATE_COL = 'CREATION_DATE'
DSNO_COL = 'ARGUMENT2'
INVOICE_COL = 'INVOICE'

def get_invoice_dsno(date_range: str, internal_control_sheet_path: str) -> Tuple[List[int], List[str]]:
    invoices = []
    dsnos = []
    
    try:
        start_date_str, end_date_str = date_range.split(';')
        start_date = pd.to_datetime(start_date_str, format='%d/%m/%Y')
        end_date = pd.to_datetime(end_date_str, format='%d/%m/%Y') + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    except ValueError as e:
        msg = "The date range must be in the format 'DD/MM/YYYY;DD/MM/YYYY'."
        log.error(msg)
        raise ValueError(msg) from e

    path = Path(internal_control_sheet_path)
    if not path.exists():
        msg = f"Control ASN Navistar sheet not found at: {internal_control_sheet_path}"
        log.error(msg)
        raise FileNotFoundError(msg)
    
    df = pd.read_excel(path)
        
    df[DATE_COL] = pd.to_datetime(df[DATE_COL], format='%m/%d/%Y %I:%M:%S %p', errors='coerce')
    
    mask = (df[DATE_COL] >= start_date) & (df[DATE_COL] <= end_date)
    
    df_filtered = df[mask]
    df_filtered = df_filtered.dropna(subset=[INVOICE_COL, DSNO_COL])
    
    invoices = df_filtered[INVOICE_COL].astype('Int64').tolist()
    dsnos = df_filtered[DSNO_COL].astype(str).tolist()
    
    return invoices, dsnos