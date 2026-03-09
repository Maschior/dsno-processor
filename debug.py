from pathlib import Path
import pandas as pd

p = Path(r'../../ASN NAVSTAR/06-02-2026/International Motors Shipment track 04.02.2026.xls')

# 1) Listar sheets
xls = pd.ExcelFile(p, engine="openpyxl")
print("Sheets:", xls.sheet_names)

# 2) Ler cada sheet sem header pra ver se tem qualquer coisa
for sh in xls.sheet_names:
    d = pd.read_excel(p, sheet_name=sh, engine="openpyxl", header=None)
    print(f"{sh}: shape={d.shape}")
    # mostra um pedacinho só pra não poluir
    print(d.head(10))
    print("-" * 60)
