import subprocess
import os
import sys
from pathlib import Path

# Adiciona o diretório raiz ao path para importar a versão
sys.path.insert(0, str(Path(__file__).parent.parent))
try:
    from dsno_processor import __version__
except ImportError:
    __version__ = "2.0.0"


def run_command(command, shell=True):
    print(f"Executando: {command}")
    result = subprocess.run(command, shell=shell)
    if result.returncode != 0:
        print(f"Erro ao executar: {command}")
        sys.exit(result.returncode)


def main():
    root_dir = Path(__file__).parent.parent
    os.chdir(root_dir)

    print(f"--- Iniciando Build para versão {__version__} ---")

    # 1. PyInstaller
    run_command("pyinstaller main.spec --clean --noconfirm")

    # 2. Inno Setup (ISCC)
    # Tenta localizar o ISCC.exe se não estiver no PATH
    iscc_path = r"C:\Users\ao32v\AppData\Local\Programs\Inno Setup 6\ISCC.exe"

    print("Gerando instalador...")
    run_command(f'"{iscc_path}" /dMyAppVersion={__version__} installer_setup.iss')

    print("\nSucesso! O instalador foi gerado na pasta 'Output/'.")


if __name__ == "__main__":
    main()
