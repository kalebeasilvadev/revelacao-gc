"""Empacota o aplicativo com PyInstaller para o sistema atual e gera o pacote final em dist/pacotes.

- macOS:   Revelacao-GC-macos-<arch>.zip      (contém "Revelacao GC.app")
- Windows: Revelacao-GC-windows-<arch>.exe    (arquivo único)
- Linux:   Revelacao-GC-linux-<arch>.tar.gz   (pasta com o executável "revelacao-gc")

Uso: uv run python scripts/build.py
"""

import os
import platform
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import PyInstaller.__main__

RAIZ = Path(__file__).resolve().parent.parent
DIST = RAIZ / "dist"
PACOTES = DIST / "pacotes"
ARQ = {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(platform.machine().lower(), platform.machine())


def main() -> None:
    os.chdir(RAIZ)
    nome = "revelacao-gc" if sys.platform.startswith("linux") else "Revelacao GC"
    opcoes = [
        "main.py",
        "--name", nome,
        "--windowed",
        "--noconfirm",
        "--clean",
        "--add-data", f"revelacao/static{os.pathsep}revelacao/static",
        "--collect-submodules", "uvicorn",
    ]
    if sys.platform == "darwin":
        opcoes += ["--osx-bundle-identifier", "br.igreja.revelacaogc"]
    elif sys.platform == "win32":
        opcoes += ["--onefile"]
    PyInstaller.__main__.run(opcoes)

    PACOTES.mkdir(parents=True, exist_ok=True)
    if sys.platform == "darwin":
        pacote = PACOTES / f"Revelacao-GC-macos-{ARQ}.zip"
        pacote.unlink(missing_ok=True)
        subprocess.run(["ditto", "-c", "-k", "--keepParent", str(DIST / f"{nome}.app"), str(pacote)], check=True)
    elif sys.platform == "win32":
        pacote = PACOTES / f"Revelacao-GC-windows-{ARQ}.exe"
        shutil.copy2(DIST / f"{nome}.exe", pacote)
    else:
        pacote = PACOTES / f"Revelacao-GC-linux-{ARQ}.tar.gz"
        with tarfile.open(pacote, "w:gz") as tar:
            tar.add(DIST / nome, arcname=nome)
    shutil.rmtree(RAIZ / "build", ignore_errors=True)
    print(f"\nPacote pronto: {pacote}")


if __name__ == "__main__":
    main()
