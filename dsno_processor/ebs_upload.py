"""EBS File Upload Automation — core module.

Absorbs the logic from ``dsno_download_upload/ebs_upload.py`` as
reusable, parameterised functions that can be driven from the GUI.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable


from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

logger = logging.getLogger(__name__)


# ── Config dataclass ─────────────────────────────────────────────────
@dataclass
class UploadConfig:
    """All parameters needed for an EBS upload run."""

    ebs_url: str
    upload_dir: str
    email: str = ""
    senha: str = ""
    pasta_indice: int = 92


# ── Histórico ────────────────────────────────────────────────────────

def _historico_path(upload_dir: str) -> Path:
    return Path(upload_dir) / "historico_uploads.json"


def carregar_historico(upload_dir: str) -> dict:
    path = _historico_path(upload_dir)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def salvar_historico(historico: dict, upload_dir: str) -> None:
    path = _historico_path(upload_dir)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(historico, f, ensure_ascii=False, indent=2)


def registrar_sucesso(historico: dict, nome_arquivo: str, upload_dir: str) -> None:
    historico[nome_arquivo] = {
        "status": "sucesso",
        "data": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    salvar_historico(historico, upload_dir)


def ja_enviado(historico: dict, nome_arquivo: str) -> bool:
    return nome_arquivo in historico and historico[nome_arquivo]["status"] == "sucesso"


# ── Arquivos locais ──────────────────────────────────────────────────

def listar_arquivos_locais(pasta: str) -> list[str]:
    if not os.path.exists(pasta):
        raise FileNotFoundError(f"Pasta não encontrada: {pasta}")

    arquivos = [
        f for f in os.listdir(pasta)
        if os.path.isfile(os.path.join(pasta, f)) 
        and not (f.startswith("historico_") and f.endswith(".json"))
    ]

    if not arquivos:
        raise FileNotFoundError(f"Nenhum arquivo encontrado em: {pasta}")

    logger.info("✅ %d arquivo(s) encontrado(s) na pasta local.", len(arquivos))
    return arquivos


# ── Browser ──────────────────────────────────────────────────────────

def iniciar_browser() -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
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
        select_el = wait.until(EC.presence_of_element_located((By.ID, "pathUpdateble")))
        select = Select(select_el)
        pastas = []
        for i, option in enumerate(select.options):
            texto = option.text.strip() or "(vazio)"
            pastas.append(f"[{i}] {texto}")
        return pastas
    except Exception as e:
        logger.warning("Não foi possível listar as pastas: %s", e)
        return []


# ── Upload ───────────────────────────────────────────────────────────

def _resetar_formulario(driver, url):
    driver.get(url)
    time.sleep(3)


def fazer_upload(
    driver: webdriver.Chrome,
    wait: WebDriverWait,
    caminho_completo: str,
    pasta_indice: int,
) -> bool:
    try:
        # 1. Select destination folder
        select_el = wait.until(EC.presence_of_element_located((By.ID, "pathUpdateble")))
        select = Select(select_el)
        select.select_by_index(pasta_indice)
        time.sleep(2)

        # 2. Set file path in the file input
        input_file = wait.until(EC.presence_of_element_located((By.ID, "FileData_oafileUpload")))
        input_file.send_keys(caminho_completo)
        time.sleep(2)

        # 3. Click Upload button
        botao = wait.until(EC.element_to_be_clickable((By.ID, "Upload")))
        botao.click()
        time.sleep(4)

        return True
    except Exception as e:
        logger.warning("    ⚠️  Erro durante o upload: %s", e)
        return False


# ── Orchestrator ─────────────────────────────────────────────────────

def run_upload(config: UploadConfig) -> dict:
    """Run the full upload flow.

    Args:
        config: Upload configuration (includes email/senha for auto-login).

    Returns:
        A summary dict with ``sucesso``, ``ignorados``, ``falhas`` keys.
    """
    # 1. Load history
    historico = carregar_historico(config.upload_dir)
    ja_feitos = [k for k, v in historico.items() if v["status"] == "sucesso"]
    if ja_feitos:
        logger.info("📋 Histórico: %d arquivo(s) já enviado(s).", len(ja_feitos))

    # 2. List local files
    todos = listar_arquivos_locais(config.upload_dir)

    # 3. Filter already uploaded
    pendentes = [a for a in todos if not ja_enviado(historico, a)]
    ignorados = len(todos) - len(pendentes)
    if ignorados:
        logger.info("⏭️  %d arquivo(s) ignorado(s) (já enviados).", ignorados)
    logger.info("📤 %d arquivo(s) para enviar.", len(pendentes))

    if not pendentes:
        logger.info("🎉 Todos os arquivos já foram enviados!")
        return {"sucesso": 0, "ignorados": ignorados, "falhas": []}

    # 4. Start browser
    driver = iniciar_browser()
    wait = WebDriverWait(driver, 15)

    # 5. Open URL and auto-login
    abrir_url(driver, config.ebs_url)
    if config.email and config.senha:
        fazer_login_microsoft(driver, wait, config.email, config.senha)

    pastas = listar_pastas(driver, wait)
    # for p in pastas:
    #     logger.info("  📂 %s", p)

    # 6. Upload each pending file
    logger.info("📤 Iniciando uploads (%d arquivo(s))...", len(pendentes))
    sucesso_count = 0
    falha_lista: list[str] = []

    for i, arquivo in enumerate(pendentes, 1):
        caminho_completo = os.path.join(config.upload_dir, arquivo)
        logger.info("[%d/%d] %s", i, len(pendentes), arquivo)

        sucesso = fazer_upload(driver, wait, caminho_completo, config.pasta_indice)
        if sucesso:
            registrar_sucesso(historico, arquivo, config.upload_dir)
            logger.info("  ✅ Upload realizado!")
            sucesso_count += 1
        else:
            logger.warning("  ❌ Falha no upload.")
            falha_lista.append(arquivo)

        # Reset form for the next file
        if i < len(pendentes):
            _resetar_formulario(driver, config.ebs_url)

    # 7. Report
    logger.info("=" * 55)
    logger.info("  ✅ Sucesso:   %d arquivo(s)", sucesso_count)
    logger.info("  ⏭️  Ignorados: %d arquivo(s)", ignorados)
    logger.info("  ❌ Falha:     %d arquivo(s)", len(falha_lista))
    if falha_lista:
        for f in falha_lista:
            logger.info("    - %s", f)

    driver.quit()
    return {"sucesso": sucesso_count, "ignorados": ignorados, "falhas": falha_lista}
