"""Teste de fumaça do executável empacotado.

Abre o app gerado em dist/ com uma pasta de dados temporária e confere:
1. o servidor interno responde (telas, fontes e API);
2. a janela do telão está rodando (manda o status pelo canal de eventos);
3. a janela do operador gravou a configuração inicial no banco.

Uso: uv run python scripts/teste_fumaca.py [--sem-janela]
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DIST = RAIZ / "dist"


def executavel() -> Path:
    if sys.platform == "darwin":
        return DIST / "Revelacao GC.app" / "Contents" / "MacOS" / "Revelacao GC"
    if sys.platform == "win32":
        return DIST / "Revelacao GC.exe"
    return DIST / "revelacao-gc" / "revelacao-gc"


def porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def get(url: str, timeout: float = 5):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.status, r.read()


def esperar(condicao, segundos: float, descricao: str):
    limite = time.time() + segundos
    while time.time() < limite:
        try:
            resultado = condicao()
            if resultado:
                return resultado
        except Exception:
            pass
        time.sleep(0.5)
    raise SystemExit(f"FALHOU: {descricao} (esperei {segundos:.0f}s)")


def status_do_telao(base: str) -> dict | None:
    with urllib.request.urlopen(f"{base}/api/eventos", timeout=10) as r:
        limite = time.time() + 10
        while time.time() < limite:
            linha = r.readline().decode().strip()
            if linha.startswith("data:"):
                mensagem = json.loads(linha[5:])
                if mensagem.get("tipo") == "status":
                    return mensagem
    return None


def encerrar(processo: subprocess.Popen) -> None:
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(processo.pid)], capture_output=True)
    else:
        processo.terminate()
        try:
            processo.wait(10)
        except subprocess.TimeoutExpired:
            processo.kill()


def main() -> None:
    sem_janela = "--sem-janela" in sys.argv
    exe = executavel()
    if not exe.exists():
        raise SystemExit(f"FALHOU: executável não encontrado em {exe}. Rode scripts/build.py antes.")

    porta = porta_livre()
    base = f"http://127.0.0.1:{porta}"
    dados = tempfile.mkdtemp(prefix="revelacao-teste-")
    env = {**os.environ, "REVELACAO_DADOS": dados, "REVELACAO_PORTA": str(porta)}
    if sem_janela:
        env["REVELACAO_SEM_JANELA"] = "1"

    print(f"Abrindo {exe} na porta {porta}")
    processo = subprocess.Popen([str(exe)], env=env)
    try:
        esperar(lambda: get(f"{base}/api/midia")[0] == 200, 90, "servidor interno subir")
        for caminho in ["/", "/fonts/fonts.css", "/api/config"]:
            codigo, _ = get(base + caminho)
            if codigo != 200:
                raise SystemExit(f"FALHOU: {caminho} respondeu {codigo}")
        print("OK  servidor interno responde (telas, fontes, API)")

        if not sem_janela:
            status = esperar(lambda: status_do_telao(base), 90, "janela do telão mandar status")
            print(f"OK  janela do telão rodando (tela: {status.get('tela')}, áudio: {status.get('som')})")
            config = esperar(lambda: json.loads(get(f"{base}/api/config")[1]), 60, "janela do operador gravar a configuração")
            print(f"OK  janela do operador gravou o evento ({len(config.get('casais', []))} casais de exemplo)")
        print("Teste de fumaça passou.")
    finally:
        encerrar(processo)


if __name__ == "__main__":
    main()
