"""EBS File Download Automation — core module.

Absorbs the logic from ``dsno_download_upload/ebs_download.py`` as
reusable, parameterised functions that can be driven from the GUI.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

import openpyxl
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

logger = logging.getLogger(__name__)


# ── Config dataclass ─────────────────────────────────────────────────
@dataclass
class DownloadConfig:
    """All parameters needed for an EBS download run."""

    ebs_url: str
    customer_sheet_path: str
    download_dir: str
    email: str = ""
    senha: str = ""
    dsno_col: str = "ARGUMENT2"
    date_col: str = "CREATION_DATE"
    status_col: str = "STATUS"
    date_start: str = ""
    date_end: str = ""
    status_filter: str = ""
    pastas_indices: list[int] = field(default_factory=lambda: [92, 95, 101])


# ── Histórico ────────────────────────────────────────────────────────

def _historico_path(download_dir: str) -> Path:
    return Path(download_dir) / "historico_downloads.json"


def carregar_historico(download_dir: str) -> dict:
    path = _historico_path(download_dir)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def salvar_historico(historico: dict, download_dir: str) -> None:
    path = _historico_path(download_dir)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(historico, f, ensure_ascii=False, indent=2)


def registrar_sucesso(historico: dict, nome_arquivo: str, download_dir: str) -> None:
    historico[nome_arquivo] = {
        "status": "sucesso",
        "data": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    salvar_historico(historico, download_dir)


def ja_baixado(historico: dict, nome_arquivo: str) -> bool:
    return nome_arquivo in historico and historico[nome_arquivo]["status"] == "sucesso"


# ── Excel ────────────────────────────────────────────────────────────

def ler_arquivos_excel(
    path: str,
    dsno_col: str,
    date_col: str,
    status_col: str,
    date_start: str,
    date_end: str,
    status_filter: str,
) -> list[str]:
    """Read file names from the customer spreadsheet, filtered by date range and status."""
    wb = openpyxl.load_workbook(path)
    ws = wb.active

    headers = [cell.value for cell in ws[1]]
    if dsno_col not in headers:
        raise ValueError(f"Coluna '{dsno_col}' não encontrada. Colunas disponíveis: {headers}")

    dsno_col_idx = headers.index(dsno_col)
    date_col_idx = headers.index(date_col) if date_col in headers else None
    status_col_idx = headers.index(status_col) if status_col in headers else None

    if date_col_idx is None:
        raise ValueError(f"Coluna '{date_col}' não encontrada.")

    start = datetime.strptime(date_start, "%d/%m/%Y %H:%M:%S") if date_start else None
    end = datetime.strptime(date_end, "%d/%m/%Y %H:%M:%S") if date_end else None

    arquivos: list[str] = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        valor = row[dsno_col_idx]
        date = row[date_col_idx]

        if status_col_idx is not None:
            status = str(row[status_col_idx]) if row[status_col_idx] is not None else None
        else:
            status = None

        # Parse the date
        if date is not None and not isinstance(date, datetime):
            if isinstance(date, str):
                date = datetime.strptime(date, "%m-%d-%Y %H:%M:%S")
            elif isinstance(date, (int, float)):
                date = datetime.fromtimestamp(date)
            else:
                continue

        if not valor or date is None:
            continue

        # Apply date filter
        if start and end:
            if not (start <= date <= end):
                continue

        # Apply status filter
        if status_filter:
            if status is None or status.lower().strip() != status_filter.lower().strip():
                continue

        arquivos.append(str(valor).strip())

    logger.info("✅ %d arquivo(s) encontrado(s) na planilha.", len(arquivos))
    return arquivos


# ── Browser ──────────────────────────────────────────────────────────

def iniciar_browser(download_dir: str) -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    }
    options.add_experimental_option("prefs", prefs)
    options.add_experimental_option("detach", True)
    return webdriver.Chrome(options=options)


def abrir_url(driver: webdriver.Chrome, url: str) -> None:
    driver.get(url)
    logger.info("🌐 Navegador aberto.")


def fazer_login_microsoft(
    driver: webdriver.Chrome,
    wait: WebDriverWait,
    email: str,
    senha: str,
) -> None:
    """Automate Microsoft login: click 'Entrar', enter email, enter password."""
    logger.info("🔐 Iniciando login automático Microsoft...")

    # Step 1: Click on "Entrar" button
    try:
        entrar_btn = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, ".middle.ext-middle"))
        )
        entrar_btn.click()
        logger.info("   → Clicou em 'Entrar'.")
        time.sleep(3)
    except Exception:
        logger.info("   → Botão 'Entrar' não encontrado, possivelmente já na tela de login.")

    # Step 2: Enter email
    try:
        email_input = wait.until(
            EC.element_to_be_clickable((By.ID, "i0116"))
        )
        email_input.clear()
        email_input.send_keys(email)
        logger.info("   → Email inserido.")
        time.sleep(1)
        email_input.send_keys(Keys.RETURN)
        time.sleep(3)
    except Exception as e:
        logger.warning("   ⚠️ Erro ao inserir email: %s", e)
        raise

    # Step 3: Enter password
    try:
        senha_input = wait.until(
            EC.element_to_be_clickable((By.ID, "i0118"))
        )
        senha_input.clear()
        senha_input.send_keys(senha)
        logger.info("   → Senha inserida.")
        time.sleep(1)
        senha_input.send_keys(Keys.RETURN)
        time.sleep(5)
    except Exception as e:
        logger.warning("   ⚠️ Erro ao inserir senha: %s", e)
        raise

    logger.info("✅ Login automático concluído.")


def listar_pastas(driver: webdriver.Chrome, wait: WebDriverWait) -> list[str]:
    try:
        select_el = wait.until(EC.presence_of_element_located((By.ID, "FilePath")))
        select = Select(select_el)
        pastas = []
        for i, option in enumerate(select.options):
            texto = option.text.strip() or "(vazio)"
            pastas.append(f"[{i}] {texto}")
        return pastas
    except Exception as e:
        logger.warning("Não foi possível listar as pastas: %s", e)
        return []


# ── Download ─────────────────────────────────────────────────────────

def _selecionar_pasta(driver, wait, indice):
    select_el = wait.until(EC.presence_of_element_located((By.ID, "FilePath")))
    select = Select(select_el)
    select.select_by_index(indice)
    time.sleep(3)


def _arquivo_encontrado(driver):
    try:
        campo = driver.find_element(By.ID, "FileName")
        return campo.is_displayed() and campo.is_enabled()
    except Exception:
        return False


def _tentar_download(driver, wait, nome_arquivo):
    try:
        campo = wait.until(EC.element_to_be_clickable((By.ID, "FileName")))
        campo.clear()
        campo.send_keys(nome_arquivo)
        time.sleep(5)
        campo.send_keys(Keys.TAB)
        time.sleep(1)
        botao = wait.until(EC.element_to_be_clickable((By.ID, "Download")))
        botao.click()
        time.sleep(4)
        return True
    except Exception as e:
        logger.warning("    ⚠️  Erro ao tentar download: %s", e)
        return False


def _resetar_formulario(driver, url):
    driver.get(url)
    time.sleep(3)


def baixar_arquivo(
    driver: webdriver.Chrome,
    wait: WebDriverWait,
    nome_arquivo: str,
    url: str,
    pastas_indices: list[int],
) -> bool:
    for i, indice in enumerate(pastas_indices, 1):
        logger.info("    🔍 Tentando pasta %d/%d (índice %d)...", i, len(pastas_indices), indice)
        try:
            _selecionar_pasta(driver, wait, indice)
        except Exception as e:
            logger.warning("    ⚠️  Não foi possível selecionar a pasta %d: %s", i, e)
            _resetar_formulario(driver, url)
            continue

        if not _arquivo_encontrado(driver):
            logger.info("    ↩️  Campo de arquivo não disponível nessa pasta.")
            _resetar_formulario(driver, url)
            continue

        if _tentar_download(driver, wait, nome_arquivo):
            return True
        _resetar_formulario(driver, url)

    return False


# ── Orchestrator ─────────────────────────────────────────────────────

def run_download(config: DownloadConfig) -> dict:
    """Run the full download flow.

    Args:
        config: Download configuration (includes email/senha for auto-login).

    Returns:
        A summary dict with ``sucesso``, ``ignorados``, ``falhas`` keys.
    """
    # 1. Load history
    historico = carregar_historico(config.download_dir)
    ja_feitos = [k for k, v in historico.items() if v["status"] == "sucesso"]
    if ja_feitos:
        logger.info("📋 Histórico: %d arquivo(s) já baixado(s).", len(ja_feitos))

    # 2. Read spreadsheet
    todos = ler_arquivos_excel(
        config.customer_sheet_path,
        config.dsno_col,
        config.date_col,
        config.status_col,
        config.date_start,
        config.date_end,
        config.status_filter,
    )

    # 3. Filter already downloaded
    pendentes = [a for a in todos if not ja_baixado(historico, a)]
    ignorados = len(todos) - len(pendentes)
    if ignorados:
        logger.info("⏭️  %d arquivo(s) ignorado(s) (já baixados).", ignorados)
    logger.info("📥 %d arquivo(s) para baixar.", len(pendentes))

    if not pendentes:
        logger.info("🎉 Todos os arquivos já foram baixados!")
        return {"sucesso": 0, "ignorados": ignorados, "falhas": []}

    # 4. Start browser
    os.makedirs(config.download_dir, exist_ok=True)
    driver = iniciar_browser(config.download_dir)
    wait = WebDriverWait(driver, 15)

    # 5. Open URL and auto-login
    abrir_url(driver, config.ebs_url)
    if config.email and config.senha:
        fazer_login_microsoft(driver, wait, config.email, config.senha)

    pastas = listar_pastas(driver, wait)
    for p in pastas:
        logger.info("  📂 %s", p)

    # 6. Download files
    logger.info("📥 Iniciando downloads (%d arquivo(s))...", len(pendentes))
    sucesso_count = 0
    falha_lista: list[str] = []

    for i, arquivo in enumerate(pendentes, 1):
        logger.info("[%d/%d] %s", i, len(pendentes), arquivo)
        encontrado = baixar_arquivo(driver, wait, arquivo, config.ebs_url, config.pastas_indices)
        if encontrado:
            registrar_sucesso(historico, arquivo, config.download_dir)
            logger.info("  ✅ Download iniciado!")
            sucesso_count += 1
        else:
            logger.warning("  ❌ Não encontrado em nenhuma das %d pastas.", len(config.pastas_indices))
            falha_lista.append(arquivo)
        time.sleep(1)

    # 7. Report
    logger.info("=" * 55)
    logger.info("  ✅ Sucesso:   %d arquivo(s)", sucesso_count)
    logger.info("  ⏭️  Ignorados: %d arquivo(s)", ignorados)
    logger.info("  ❌ Falha:     %d arquivo(s)", len(falha_lista))
    if falha_lista:
        for f in falha_lista:
            logger.info("    - %s", f)
    logger.info("  📁 Downloads: %s", config.download_dir)

    driver.quit()
    return {"sucesso": sucesso_count, "ignorados": ignorados, "falhas": falha_lista}
