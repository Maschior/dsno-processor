# -*- mode: python ; coding: utf-8 -*-

import os
import customtkinter

# Locate the customtkinter package data (themes, assets, etc.)
ctk_path = os.path.dirname(customtkinter.__file__)

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        # CustomTkinter theme/assets — required at runtime
        (ctk_path, 'customtkinter/'),
        # Project assets (icons, etc.)
        ('assets', 'assets'),
        # Ship default config example so the user can bootstrap
        ('config.toml.example', '.'),
    ],
    hiddenimports=[
        # ── Selenium ──────────────────────────────────────
        'selenium',
        'selenium.webdriver.chrome.options',
        'selenium.webdriver.chrome.service',
        'selenium.webdriver.chrome.webdriver',
        'selenium.webdriver.common.by',
        'selenium.webdriver.common.keys',
        'selenium.webdriver.support.ui',
        'selenium.webdriver.support.expected_conditions',
        'selenium.webdriver.remote.webelement',
        'selenium.webdriver.remote.command',
        # ── Data / IO ────────────────────────────────────
        'pandas',
        'openpyxl',
        'requests',
        'unidecode',
        'pyautogui',
        'pyscreeze',
        'pygetwindow',
        'pymsgbox',
        'pyperclip',
        'pyrect',
        'pytweening',
        'mouseinfo',
        'PIL',
        'PIL.Image',
        'PIL.ImageFilter',
        'PIL.ImageTk',
        # ── Config (TOML) ────────────────────────────────
        'tomllib',
        'tomli_w',
        # ── GUI ──────────────────────────────────────────
        'customtkinter',
        # ── Project modules ──────────────────────────────
        'dsno_processor',
        'dsno_processor.config',
        'dsno_processor.editor',
        'dsno_processor.exceptions',
        'dsno_processor.i18n',
        'dsno_processor.customer_reader',
        'dsno_processor.control_reader',
        'dsno_processor.models',
        'dsno_processor.processor',
        'dsno_processor.status_updater',
        'dsno_processor.ebs_download',
        'dsno_processor.ebs_upload',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DSNO Processor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icons/favicon.ico',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DSNO Processor',
)
