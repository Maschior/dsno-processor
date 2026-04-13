"""EBS File Upload Automation — core module.

Provides reusable, parameterised functions for automating file uploads
to Oracle EBS, driven from the GUI.
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

from .exceptions import ConfigurationError

logger = logging.getLogger(__name__)


# ── Config dataclass ─────────────────────────────────────────────────


@dataclass
class UploadConfig:
    """All parameters needed for an EBS upload run."""

    ebs_url: str
    upload_dir: str
    email: str = ""
    password: str = ""
    folder_index: int = 92
    headless: bool = False


# ── History tracking ─────────────────────────────────────────────────


def _history_path(upload_dir: str) -> Path:
    return Path(upload_dir) / "historico_uploads.json"


def load_history(upload_dir: str) -> dict:
    """Load the upload history from disk."""
    path = _history_path(upload_dir)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.error("Malformed or corrupted history file: %s", e)
            raise ConfigurationError(
                "Malformed or corrupted history file.\n"
                "Delete the file or fix it manually.\n"
                f"File location: {path}"
            )
    return {}


def save_history(history: dict, upload_dir: str) -> None:
    """Persist the upload history to disk."""
    path = _history_path(upload_dir)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def record_success(history: dict, filename: str, upload_dir: str) -> None:
    """Mark a file as successfully uploaded in the history."""
    history[filename] = {
        "status": "success",
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    save_history(history, upload_dir)


def already_uploaded(history: dict, filename: str) -> bool:
    """Check whether a file has already been uploaded."""
    entry = history.get(filename, {})
    return entry.get("status") in ("success", "sucesso")


# ── Local files ──────────────────────────────────────────────────────


def list_local_files(directory: str) -> list[str]:
    """List uploadable files in the given directory."""
    if not os.path.exists(directory):
        raise FileNotFoundError(f"Directory not found: {directory}")

    files = [
        f for f in os.listdir(directory)
        if os.path.isfile(os.path.join(directory, f))
        and not (f.startswith("historico_") and f.endswith(".json"))
    ]

    if not files:
        raise FileNotFoundError(f"No files found in: {directory}")

    logger.info("%d file(s) found in local directory.", len(files))
    return files


# ── Browser ──────────────────────────────────────────────────────────


def start_browser(headless: bool = False) -> webdriver.Chrome:
    """Start a Chrome browser for uploads."""
    options = webdriver.ChromeOptions()
    options.add_experimental_option("detach", True)

    if headless:
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        logger.info("Headless mode enabled — browser running in background.")

    return webdriver.Chrome(options=options)


def open_url(driver: webdriver.Chrome, url: str) -> None:
    """Navigate the browser to the given URL."""
    driver.get(url)
    logger.info("Browser opened.")


def perform_microsoft_login(
    driver: webdriver.Chrome,
    wait: WebDriverWait,
    email: str,
    password: str,
    target_url: str = "",
) -> None:
    """Automate Microsoft SSO login: click sign-in, enter email, enter password."""
    logger.info("Starting automatic Microsoft login...")

    # Step 1: Click on sign-in button
    try:
        sign_in_btn = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, ".middle.ext-middle"))
        )
        sign_in_btn.click()
        logger.info("Clicked sign-in button.")
        time.sleep(3)
    except Exception:
        logger.info("Sign-in button not found — possibly already on login page.")

    # Step 2: Enter email
    try:
        email_input = wait.until(
            EC.element_to_be_clickable((By.ID, "i0116"))
        )
        email_input.clear()
        email_input.send_keys(email)
        logger.info("Email entered.")
        time.sleep(1)
        email_input.send_keys(Keys.RETURN)
        time.sleep(3)
    except Exception as e:
        logger.warning("Error entering email: %s", e)
        raise

    # Step 3: Enter password
    try:
        password_input = wait.until(
            EC.element_to_be_clickable((By.ID, "i0118"))
        )
        password_input.clear()
        password_input.send_keys(password)
        logger.info("Password entered.")
        time.sleep(1)
        password_input.send_keys(Keys.RETURN)
        time.sleep(5)
    except Exception as e:
        logger.warning("Error entering password: %s", e)
        raise

    logger.info("Waiting for EBS redirect...")
    try:
        xxdba_menu = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//div[normalize-space()='XXDBA Utilities']")
            )
        )
        xxdba_menu.click()
        logger.info("Clicked 'XXDBA Utilities' menu.")
        time.sleep(3)
    except Exception:
        logger.info(
            "'XXDBA Utilities' menu not found "
            "(may already be on the correct page or layout differs)."
        )

    if target_url:
        logger.info("Reloading target URL to ensure correct page...")
        driver.get(target_url)
        time.sleep(5)

    logger.info("Automatic login complete.")


def list_folders(driver: webdriver.Chrome, wait: WebDriverWait) -> list[str]:
    """List available folders in the EBS upload path dropdown."""
    try:
        select_el = wait.until(
            EC.presence_of_element_located((By.ID, "pathUpdateble"))
        )
        select = Select(select_el)
        folders = []
        for i, option in enumerate(select.options):
            text = option.text.strip() or "(empty)"
            folders.append(f"[{i}] {text}")
        return folders
    except Exception as e:
        logger.warning("Could not list folders: %s", e)
        return []


# ── Upload ───────────────────────────────────────────────────────────


def _reset_form(driver, url):
    """Reset the EBS form by reloading the page."""
    driver.get(url)
    time.sleep(3)


def perform_upload(
    driver: webdriver.Chrome,
    wait: WebDriverWait,
    file_path: str,
    folder_index: int,
) -> bool:
    """Upload a single file to EBS."""
    try:
        # 1. Select destination folder
        select_el = wait.until(
            EC.presence_of_element_located((By.ID, "pathUpdateble"))
        )
        select = Select(select_el)
        select.select_by_index(folder_index)
        time.sleep(2)

        # 2. Set file path in the file input
        input_file = wait.until(
            EC.presence_of_element_located((By.ID, "FileData_oafileUpload"))
        )
        input_file.send_keys(file_path)
        time.sleep(2)

        # 3. Click Upload button
        button = wait.until(EC.element_to_be_clickable((By.ID, "Upload")))
        button.click()
        time.sleep(4)

        return True
    except Exception as e:
        logger.warning("Error during upload: %s", e)
        return False


# ── Orchestrator ─────────────────────────────────────────────────────


def run_upload(config: UploadConfig, progress_callback=None) -> dict:
    """Run the full upload flow.

    Args:
        config: Upload configuration.
        progress_callback: Optional ``(event, data_dict)`` callable for
            real-time progress updates consumed by the GUI dashboard.

    Returns:
        A summary dict with ``success``, ``skipped``, ``failures`` keys.
    """

    def _cb(event: str, data: dict | None = None) -> None:
        if progress_callback:
            progress_callback(event, data or {})

    # 1. Load history
    _cb("phase", {"text": "Loading history..."})
    history = load_history(config.upload_dir)
    already_done = [k for k, v in history.items() if v["status"] in ("success", "sucesso")]
    if already_done:
        logger.info("History: %d file(s) already uploaded.", len(already_done))

    # 2. List local files
    _cb("phase", {"text": "Listing local files..."})
    all_files = list_local_files(config.upload_dir)

    # 3. Filter already uploaded
    pending = [f for f in all_files if not already_uploaded(history, f)]
    skipped_list = [f for f in all_files if already_uploaded(history, f)]
    skipped_count = len(skipped_list)

    # Report total (including skipped) to dashboard
    _cb("total", {"count": len(all_files)})

    # Report skipped items individually
    for f in skipped_list:
        _cb("skipped", {"name": f, "detail": "Already uploaded"})

    if skipped_count:
        logger.info("%d file(s) skipped (already uploaded).", skipped_count)
    logger.info("%d file(s) to upload.", len(pending))

    if not pending:
        logger.info("All files have already been uploaded!")
        _cb("finished", {})
        return {"success": 0, "skipped": skipped_count, "failures": []}

    # 4. Start browser
    _cb("phase", {"text": "Starting browser..."})
    driver = start_browser(headless=config.headless)
    wait = WebDriverWait(driver, 15)

    # 5. Open URL and auto-login
    _cb("phase", {"text": "Opening EBS..."})
    open_url(driver, config.ebs_url)
    if config.email and config.password:
        _cb("phase", {"text": "Performing automatic login..."})
        perform_microsoft_login(driver, wait, config.email, config.password, config.ebs_url)

    list_folders(driver, wait)

    # 6. Upload each pending file
    logger.info("Starting uploads (%d file(s))...", len(pending))
    success_count = 0
    failure_list: list[str] = []

    for i, filename in enumerate(pending, 1):
        full_path = os.path.join(config.upload_dir, filename)
        _cb("phase", {"text": f"Uploading {filename} ({i}/{len(pending)})..."})
        logger.info("[%d/%d] %s", i, len(pending), filename)

        ok = perform_upload(driver, wait, full_path, config.folder_index)
        if ok:
            record_success(history, filename, config.upload_dir)
            logger.info("Upload successful!")
            success_count += 1
            _cb("success", {"name": filename})
        else:
            logger.warning("Upload failed.")
            failure_list.append(filename)
            _cb("error", {"name": filename, "detail": "Upload failed"})

        # Reset form for the next file
        if i < len(pending):
            _reset_form(driver, config.ebs_url)

    # 7. Report
    logger.info("=" * 55)
    logger.info("  Success:  %d file(s)", success_count)
    logger.info("  Skipped:  %d file(s)", skipped_count)
    logger.info("  Failed:   %d file(s)", len(failure_list))
    if failure_list:
        for f in failure_list:
            logger.info("    - %s", f)

    _cb("finished", {})
    driver.quit()
    return {"success": success_count, "skipped": skipped_count, "failures": failure_list}
