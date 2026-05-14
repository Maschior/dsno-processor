"""Internationalization (i18n) module for the DSNO Processor.

Provides a simple key-based translation system with support for
English (``en``) and Portuguese (``pt``).

Usage::

    from dsno_processor.i18n import t, set_language

    set_language("pt")
    print(t("app.title"))  # → "DSNO Processor"

How to add translations
-----------------------

1. Find the ``_TRANSLATIONS`` dictionary below.
2. Each top-level key is a language code (``"en"``, ``"pt"``).
3. Inside each language dict, keys are dot-separated identifiers
   (e.g. ``"tab.processor"``, ``"btn.save"``).
4. To add a new translatable string:
   a. Pick a descriptive key, e.g. ``"settings.hint.new_field"``.
   b. Add the key to **both** ``"en"`` and ``"pt"`` dicts.
   c. Use ``t("settings.hint.new_field")`` in your code.
5. To add an entirely new language (e.g. Spanish):
   a. Add ``"es": { ... }`` with the same keys as ``"en"``.
   b. Add ``"es"`` to ``SUPPORTED_LANGUAGES``.
"""

from __future__ import annotations

# ── Supported languages ──────────────────────────────────────────────

SUPPORTED_LANGUAGES: dict[str, str] = {
    "en": "English",
    "pt": "Português (BR)",
}

# ── Module state ─────────────────────────────────────────────────────

_current_language: str = "en"

# ── Translation table ────────────────────────────────────────────────

_TRANSLATIONS: dict[str, dict[str, str]] = {
    # ══════════════════════════════════════════════════════════════
    # ENGLISH
    # ══════════════════════════════════════════════════════════════
    "en": {
        # ── App ─────────────────────────────────────────────────
        "app.title": "DSNO Processor",
        "app.subtitle": "Process and edit DSNO files according to ASN spreadsheets.",

        # ── Header / global buttons ─────────────────────────────
        "btn.settings": "Settings",
        "btn.browse": "Browse",
        "btn.save": "Save",
        "btn.cancel": "Cancel",

        # ── Main tabs ───────────────────────────────────────────
        "tab.processor": "Processor",
        "tab.download": "EBS Download",
        "tab.upload": "EBS Upload",

        # ── Sub-tabs ────────────────────────────────────────────
        "tab.configuration": "Configuration",
        "tab.progress": "Progress",

        # ── Processor tab ───────────────────────────────────────
        "proc.date_range": "Date Range:",
        "proc.start": "Start:",
        "proc.end": "End:",
        "proc.customer_sheet": "Customer Sheet:",
        "proc.control_sheet": "Control Sheet:",
        "proc.dsno_directory": "DSNO Directory:",
        "proc.start_btn": "Start Processing",
        "proc.status": "Filter by Status:",
        "proc.freight_mode": "Freight Mode:",
        "proc.freight_mode_hint": "SEA/ROAD = prefer Softway when different. AIR = use Oracle.",
        "proc.air": "AIR",
        "proc.sea": "SEA/ROAD",

        # ── Download tab ────────────────────────────────────────
        "dl.section_period": "Period",
        "dl.start_date": "Start Date:",
        "dl.end_date": "End Date:",
        "dl.status_filter": "Status Filter:",
        "dl.section_files": "Files",
        "dl.download_dir": "Download Dir:",
        "dl.customer_sheet": "Customer Sheet:",
        "dl.section_connection": "Connection",
        "dl.ebs_url": "EBS URL:",
        "dl.section_columns": "Columns",
        "dl.invoice_column": "Invoice Column:",
        "dl.dsno_column": "DSNO Column:",
        "dl.date_column": "Date Column:",
        "dl.status_column": "Status Column:",
        "dl.section_folders": "Folders",
        "dl.folder_indices": "Folder Indices:",
        "dl.start_btn": "Start Download",

        # ── Upload tab ──────────────────────────────────────────
        "ul.section_connection": "Connection",
        "ul.ebs_url": "EBS URL:",
        "ul.section_files": "Files",
        "ul.upload_dir": "Upload Dir:",
        "ul.section_folders": "Folders",
        "ul.folder_index": "Folder Index:",
        "ul.start_btn": "Start Upload",

        # ── Browse dialog titles ────────────────────────────────
        "browse.customer_sheet": "Select Customer Sheet",
        "browse.control_sheet": "Select Control Sheet",
        "browse.dsno_directory": "Select DSNO Directory",
        "browse.download_dir": "Select Download Directory",
        "browse.upload_dir": "Select Upload Directory",

        # ── Progress dashboard ──────────────────────────────────
        "dash.waiting": "Waiting to start...",
        "dash.starting": "Starting...",
        "dash.no_items": "No items processed yet.",
        "dash.no_items_found": "No items found.",
        "dash.success": "Success",
        "dash.errors": "Errors",
        "dash.skipped": "Skipped",
        "dash.pending": "Pending",
        "dash.processed": "Processed",
        "dash.downloaded": "Downloaded",
        "dash.show_logs": "Show Logs",
        "dash.hide_logs": "Hide Logs",
        "dash.cancelled": "Cancelled",
        "dash.completed_success": "Completed successfully!",
        "dash.completed_errors": "Completed with {count} error(s)",

        # ── Calendar ────────────────────────────────────────────
        "cal.time": "Time",
        "cal.apply": "Apply",
        "cal.cancel": "Cancel",
        "cal.days": "Mon,Tue,Wed,Thu,Fri,Sat,Sun",

        # ── Settings window ─────────────────────────────────────
        "settings.title": "Settings",
        "settings.header": "Application Settings",
        "settings.subtitle": "Edit the persistent settings saved in config.toml.",

        # ── Settings tabs ───────────────────────────────────────
        "settings.tab.general": "General",
        "settings.tab.paths": "Paths",
        "settings.tab.processor": "Processor",
        "settings.tab.ebs": "EBS",
        "settings.tab.columns": "Columns",
        "settings.tab.folders": "Folders",
        "settings.tab.credentials": "Credentials",

        # ── Settings: General ───────────────────────────────────
        "settings.general.hint": "General application preferences.",
        "settings.general.language": "Language:",
        "settings.general.language_hint": "Changes the interface language. Requires a restart.",
        "settings.general.restart_msg": "Language changed. Please restart the application for the change to take effect.",
        "settings.general.data_source": "Data Source:",
        "settings.general.data_source_hint": "Select where to read/write DSNO data: directly from spreadsheets or via the local database.",
        "settings.data_source.spreadsheet": "Spreadsheet",
        "settings.data_source.database": "Database",

        # ── Settings: Paths ─────────────────────────────────────
        "settings.paths.hint": "Directories and files used by the DSNO processor.",
        "settings.paths.dsno_directory": "DSNO Directory:",
        "settings.paths.dsno_directory_hint": "Folder containing the DSNO .txt files.",
        "settings.paths.control_sheet": "Control Sheet:",
        "settings.paths.control_sheet_hint": "Control ASN Navistar spreadsheet.",
        "settings.paths.customer_sheet": "Customer Sheet:",
        "settings.paths.customer_sheet_hint": "Customer spreadsheet (optional).",
        "settings.paths.customer_pre_path": "Customer Pre-Path:",
        "settings.paths.customer_pre_path_hint": "Default folder for browsing customer sheets.",

        # ── Settings: Processor ─────────────────────────────────
        "settings.processor.hint": "Settings that control the processing behaviour.",
        "settings.processor.bypass_file_size_check": "Bypass file size verification:",
        "settings.processor.bypass_file_size_check_hint": "If enabled, processing will not fail when the output file size is unchanged (useful for tests).",

        # ── Settings: EBS ───────────────────────────────────────
        "settings.ebs.hint": "Oracle EBS URLs and directories for download and upload.",
        "settings.ebs.download_url": "Download URL:",
        "settings.ebs.download_url_hint": "Full URL of the EBS download page.",
        "settings.ebs.upload_url": "Upload URL:",
        "settings.ebs.upload_url_hint": "Full URL of the EBS upload page.",
        "settings.ebs.download_dir": "Download Dir:",
        "settings.ebs.download_dir_hint": "Folder where downloaded files will be saved.",
        "settings.ebs.upload_dir": "Upload Dir:",
        "settings.ebs.upload_dir_hint": "Folder containing processed files for upload.",
        "settings.ebs.headless_hint": "When enabled, the browser runs in the background (invisible).",
        "settings.ebs.headless": "Headless Mode:",
        "settings.ebs.headless_switch": "Browser in background",

        # ── Settings: Columns ───────────────────────────────────
        "settings.columns.hint": "Column names used in the EBS spreadsheets.",
        "settings.columns.invoice_hint": "Name of the column containing the invoice number in the control sheet.",
        "settings.columns.dsno": "DSNO Column:",
        "settings.columns.dsno_hint": "Name of the column containing the DSNO identifier.",
        "settings.columns.date": "Date Column:",
        "settings.columns.date_hint": "Name of the creation date column.",
        "settings.columns.status": "Status Column:",
        "settings.columns.status_hint": "Name of the status column.",
        "settings.columns.control_columns_section": "Control Sheet Columns",
        "settings.columns.customer_columns_section": "Customer Sheet Columns",
        "settings.columns.customer_config_section": "Customer Sheet Configuration",
        "settings.columns.cust_invoice": "Invoice:",
        "settings.columns.cust_booking": "Booking/HAWB:",
        "settings.columns.cust_container": "Container:",
        "settings.columns.cust_sheet_name": "Sheet Name:",
        "settings.columns.cust_sheet_name_hint": "Leave empty to use the first sheet. (NOTE: This is not the file name, but the sheet name.)",

        # ── Settings: Folders ───────────────────────────────────
        "settings.folders.hint": "Folder indices used by EBS for download and upload.",
        "settings.folders.download_indices": "Download Indices:",
        "settings.folders.download_indices_hint": "Comma-separated indices (e.g. 92, 95, 101).",
        "settings.folders.upload_index": "Upload Index:",
        "settings.folders.upload_index_hint": "Folder index for uploading.",

        # ── Settings: Credentials ───────────────────────────────
        "settings.credentials.hint": "Credentials used for automatic Microsoft / EBS login.",
        "settings.credentials.email": "Email:",
        "settings.credentials.email_hint": "Corporate email address.",
        "settings.credentials.password": "Password:",
        "settings.credentials.password_hint": "Password used for automatic login.",

        # ── Settings: Save messages ─────────────────────────────
        "settings.saved_title": "Settings",
        "settings.saved_msg": "Settings saved successfully!\nChanges are now in effect.",
        "settings.save_error_title": "Error",
        "settings.save_error_msg": "Error saving settings:\n{error}",

        # ── Processing messages ─────────────────────────────────
        "msg.complete_title": "Complete",
        "msg.success_title": "Success",
        "msg.error_title": "Error",
        "msg.download_title": "Download",
        "msg.upload_title": "Upload",
        "msg.processing_complete": "Processing complete: {success}/{total} successful.",
        "msg.processing_errors": "{summary}\n{failed} error(s).",
        "msg.download_complete": "Download complete: {success}/{total} successful.",
        "msg.upload_complete": "Upload complete: {success}/{total} successful.",
        "msg.cancelling": "Cancelling...\nPlease wait.",

        # ── Import wizard ──────────────────────────────────────
        "import.title": "Import Customer Sheet",
        "import.select_file": "Select File:",
        "import.btn_import": "Import",
        "import.importing": "Importing...",
        "import.success": "Import complete: {imported} record(s) imported, {skipped} skipped.",
        "import.error": "Import failed: {error}",
        "import.no_file": "Please select a file first.",
        "import.btn_label": "Import Customer Sheet to DB",
        
        "import_control.title": "Import Control Sheet",
        "import_control.select_file": "Select File:",
        "import_control.btn_import": "Import",
        "import_control.importing": "Importing...",
        "import_control.success": "Import complete: {imported} record(s) imported, {skipped} skipped.",
        "import_control.error": "Import failed: {error}",
        "import_control.no_file": "Please select a file first.",
        "import_control.btn_label": "Import Control Sheet to DB",
    },

    # ══════════════════════════════════════════════════════════════
    # PORTUGUESE
    # ══════════════════════════════════════════════════════════════
    "pt": {
        # ── App ─────────────────────────────────────────────────
        "app.title": "DSNO Processor",
        "app.subtitle": "Processar e editar arquivos DSNO conforme planilhas ASN.",

        # ── Header / global buttons ─────────────────────────────
        "btn.settings": "Configurações",
        "btn.browse": "Procurar",
        "btn.save": "Salvar",
        "btn.cancel": "Cancelar",

        # ── Main tabs ───────────────────────────────────────────
        "tab.processor": "Processador",
        "tab.download": "EBS Download",
        "tab.upload": "EBS Upload",

        # ── Sub-tabs ────────────────────────────────────────────
        "tab.configuration": "Configuração",
        "tab.progress": "Progresso",

        # ── Processor tab ───────────────────────────────────────
        "proc.date_range": "Período:",
        "proc.start": "Início:",
        "proc.end": "Fim:",
        "proc.customer_sheet": "Planilha do Cliente:",
        "proc.control_sheet": "Planilha de Controle:",
        "proc.dsno_directory": "Diretório DSNO:",
        "proc.start_btn": "Iniciar Processamento",
        "proc.status": "Filtrar por Status:",
        "proc.freight_mode": "Modo de Frete:",
        "proc.freight_mode_hint": "MARÍTIMO/RODOVIÁRIO = prefere Softway quando diferente. AÉREO = usa Softway.",
        "proc.air": "AÉREO",
        "proc.sea": "MARÍTIMO/RODOVIÁRIO",

        # ── Download tab ────────────────────────────────────────
        "dl.section_period": "Período",
        "dl.start_date": "Data Início:",
        "dl.end_date": "Data Fim:",
        "dl.status_filter": "Filtro de Status:",
        "dl.section_files": "Arquivos",
        "dl.download_dir": "Diretório Download:",
        "dl.customer_sheet": "Planilha do Cliente:",
        "dl.section_connection": "Conexão",
        "dl.ebs_url": "URL EBS:",
        "dl.section_columns": "Colunas",
        "dl.invoice_column": "Coluna Invoice:",
        "dl.dsno_column": "Coluna DSNO:",
        "dl.date_column": "Coluna Data:",
        "dl.status_column": "Coluna Status:",
        "dl.section_folders": "Pastas",
        "dl.folder_indices": "Índices de Pastas:",
        "dl.start_btn": "Iniciar Download",

        # ── Upload tab ──────────────────────────────────────────
        "ul.section_connection": "Conexão",
        "ul.ebs_url": "URL EBS:",
        "ul.section_files": "Arquivos",
        "ul.upload_dir": "Diretório Upload:",
        "ul.section_folders": "Pastas",
        "ul.folder_index": "Índice da Pasta:",
        "ul.start_btn": "Iniciar Upload",

        # ── Browse dialog titles ────────────────────────────────
        "browse.customer_sheet": "Selecionar Planilha do Cliente",
        "browse.control_sheet": "Selecionar Planilha de Controle",
        "browse.dsno_directory": "Selecionar Diretório DSNO",
        "browse.download_dir": "Selecionar Diretório de Download",
        "browse.upload_dir": "Selecionar Diretório de Upload",

        # ── Progress dashboard ──────────────────────────────────
        "dash.waiting": "Aguardando início...",
        "dash.starting": "Iniciando...",
        "dash.no_items": "Nenhum item processado ainda.",
        "dash.no_items_found": "Nenhum item encontrado.",
        "dash.success": "Sucesso",
        "dash.errors": "Erros",
        "dash.skipped": "Ignorados",
        "dash.pending": "Pendentes",
        "dash.processed": "Processado",
        "dash.downloaded": "Baixado",
        "dash.show_logs": "Mostrar Logs",
        "dash.hide_logs": "Ocultar Logs",
        "dash.cancelled": "Cancelado",
        "dash.completed_success": "Concluído com sucesso!",
        "dash.completed_errors": "Concluído com {count} erro(s)",

        # ── Calendar ────────────────────────────────────────────
        "cal.time": "Horário",
        "cal.apply": "Aplicar",
        "cal.cancel": "Cancelar",
        "cal.days": "Seg,Ter,Qua,Qui,Sex,Sáb,Dom",

        # ── Settings window ─────────────────────────────────────
        "settings.title": "Configurações",
        "settings.header": "Configurações do Aplicativo",
        "settings.subtitle": "Edite as configurações persistidas no config.toml.",

        # ── Settings tabs ───────────────────────────────────────
        "settings.tab.general": "Geral",
        "settings.tab.paths": "Caminhos",
        "settings.tab.processor": "Processador",
        "settings.tab.ebs": "EBS",
        "settings.tab.columns": "Colunas",
        "settings.tab.folders": "Pastas",
        "settings.tab.credentials": "Credenciais",

        # ── Settings: General ───────────────────────────────────
        "settings.general.hint": "Preferências gerais do aplicativo.",
        "settings.general.language": "Idioma:",
        "settings.general.language_hint": "Altera o idioma da interface. Requer reinicialização.",
        "settings.general.restart_msg": "Idioma alterado. Por favor, reinicie o aplicativo para que a alteração tenha efeito.",
        "settings.general.data_source": "Fonte de Dados:",
        "settings.general.data_source_hint": "Selecione onde ler/gravar dados do DSNO: diretamente nas planilhas ou através do banco de dados local.",
        "settings.data_source.spreadsheet": "Planilha",
        "settings.data_source.database": "Banco de Dados",

        # ── Settings: Paths ─────────────────────────────────────
        "settings.paths.hint": "Diretórios e arquivos utilizados pelo processador DSNO.",
        "settings.paths.dsno_directory": "Diretório DSNO:",
        "settings.paths.dsno_directory_hint": "Pasta contendo os arquivos DSNO .txt.",
        "settings.paths.control_sheet": "Planilha de Controle:",
        "settings.paths.control_sheet_hint": "Planilha de controle ASN Navistar.",
        "settings.paths.customer_sheet": "Planilha do Cliente:",
        "settings.paths.customer_sheet_hint": "Planilha do cliente (opcional).",
        "settings.paths.customer_pre_path": "Pré-Caminho Cliente:",
        "settings.paths.customer_pre_path_hint": "Pasta padrão para navegação de planilhas.",

        # ── Settings: Processor ─────────────────────────────────
        "settings.processor.hint": "Configurações que controlam o comportamento do processamento.",
        "settings.processor.bypass_file_size_check": "Ignorar verificação de tamanho do arquivo:",
        "settings.processor.bypass_file_size_check_hint": "Se ativado, o processamento não falhará quando o tamanho do arquivo não mudar (útil para testes).",

        # ── Settings: EBS ───────────────────────────────────────
        "settings.ebs.hint": "URLs e diretórios do Oracle EBS para download e upload.",
        "settings.ebs.download_url": "URL Download:",
        "settings.ebs.download_url_hint": "URL completa da página de download do EBS.",
        "settings.ebs.upload_url": "URL Upload:",
        "settings.ebs.upload_url_hint": "URL completa da página de upload do EBS.",
        "settings.ebs.download_dir": "Dir. Download:",
        "settings.ebs.download_dir_hint": "Pasta onde os arquivos baixados serão salvos.",
        "settings.ebs.upload_dir": "Dir. Upload:",
        "settings.ebs.upload_dir_hint": "Pasta com os arquivos processados para upload.",
        "settings.ebs.headless_hint": "Quando ativado, o navegador roda em segundo plano (invisível).",
        "settings.ebs.headless": "Modo Headless:",
        "settings.ebs.headless_switch": "Navegador em segundo plano",

        # ── Settings: Columns ───────────────────────────────────
        "settings.columns.hint": "Nomes das colunas usadas nas planilhas do EBS.",
        "settings.columns.invoice_hint": "Nome da coluna que contém o número da fatura na planilha de controle.",
        "settings.columns.dsno": "Coluna DSNO:",
        "settings.columns.dsno_hint": "Nome da coluna que contém o identificador DSNO.",
        "settings.columns.date": "Coluna Data:",
        "settings.columns.date_hint": "Nome da coluna de data de criação.",
        "settings.columns.status": "Coluna Status:",
        "settings.columns.status_hint": "Nome da coluna de status.",
        "settings.columns.control_columns_section": "Colunas da Planilha de Controle",
        "settings.columns.customer_columns_section": "Colunas da Planilha do Cliente",
        "settings.columns.customer_config_section": "Configuração da Planilha do Cliente",
        "settings.columns.cust_invoice": "Invoice:",
        "settings.columns.cust_booking": "Booking/HAWB:",
        "settings.columns.cust_container": "Container:",
        "settings.columns.cust_sheet_name": "Nome da Planilha:",
        "settings.columns.cust_sheet_name_hint": "Deixe em branco para usar a primeira planilha. (OBS: Não é o nome do arquivo, mas da planilha dentro do arquivo)",

        # ── Settings: Folders ───────────────────────────────────
        "settings.folders.hint": "Índices de pastas usados pelo EBS para download e upload.",
        "settings.folders.download_indices": "Índices Download:",
        "settings.folders.download_indices_hint": "Índices separados por vírgula (ex: 92, 95, 101).",
        "settings.folders.upload_index": "Índice Upload:",
        "settings.folders.upload_index_hint": "Índice da pasta de upload.",

        # ── Settings: Credentials ───────────────────────────────
        "settings.credentials.hint": "Credenciais usadas para login automático no Microsoft / EBS.",
        "settings.credentials.email": "Email:",
        "settings.credentials.email_hint": "Endereço de e-mail corporativo.",
        "settings.credentials.password": "Senha:",
        "settings.credentials.password_hint": "Senha utilizada no login automático.",

        # ── Settings: Save messages ─────────────────────────────
        "settings.saved_title": "Configurações",
        "settings.saved_msg": "Configurações salvas com sucesso!\nAs alterações já estão em vigor.",
        "settings.save_error_title": "Erro",
        "settings.save_error_msg": "Erro ao salvar configurações:\n{error}",

        # ── Processing messages ─────────────────────────────────
        "msg.complete_title": "Concluído",
        "msg.success_title": "Sucesso",
        "msg.error_title": "Erro",
        "msg.download_title": "Download",
        "msg.upload_title": "Upload",
        "msg.processing_complete": "Processamento concluído: {success}/{total} com sucesso.",
        "msg.processing_errors": "{summary}\n{failed} erro(s).",
        "msg.download_complete": "Download concluído: {success}/{total} com sucesso.",
        "msg.upload_complete": "Upload concluído: {success}/{total} com sucesso.",
        "msg.cancelling": "Cancelando...\nPor favor, aguarde.",

        # ── Import wizard ──────────────────────────────────────
        "import.title": "Importar Planilha do Cliente",
        "import.select_file": "Selecionar Arquivo:",
        "import.btn_import": "Importar",
        "import.importing": "Importando...",
        "import.success": "Importação concluída: {imported} registro(s) importados, {skipped} ignorados.",
        "import.error": "Falha na importação: {error}",
        "import.no_file": "Selecione um arquivo primeiro.",
        "import.btn_label": "Importar Planilha do Cliente para DB",
        
        "import_control.title": "Importar Planilha de Controle",
        "import_control.select_file": "Selecionar Arquivo:",
        "import_control.btn_import": "Importar",
        "import_control.importing": "Importando...",
        "import_control.success": "Importação concluída: {imported} registro(s) importados, {skipped} ignorados.",
        "import_control.error": "Falha na importação: {error}",
        "import_control.no_file": "Selecione um arquivo primeiro.",
        "import_control.btn_label": "Importar Planilha de Controle para DB",
    },
}


# ── Public API ───────────────────────────────────────────────────────


def set_language(lang: str) -> None:
    """Set the active language.

    Args:
        lang: A language code present in ``SUPPORTED_LANGUAGES``
              (e.g. ``"en"`` or ``"pt"``).
    """
    global _current_language
    if lang in _TRANSLATIONS:
        _current_language = lang


def get_language() -> str:
    """Return the currently active language code."""
    return _current_language


def t(key: str, **kwargs) -> str:
    """Get a translated string for the current language.

    If the key is not found in the current language, falls back to
    English. If not found at all, returns the key itself.

    Supports ``str.format`` placeholders::

        t("dash.completed_errors", count=3)
        # → "Completed with 3 error(s)"

    Args:
        key: Dot-separated translation key.
        **kwargs: Values for ``str.format`` placeholders.

    Returns:
        The translated string.
    """
    lang_dict = _TRANSLATIONS.get(_current_language, _TRANSLATIONS["en"])
    text = lang_dict.get(key, _TRANSLATIONS["en"].get(key, key))
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text
