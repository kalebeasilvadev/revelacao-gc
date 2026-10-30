"""Ponto de entrada do aplicativo desktop: sobe a API local e abre as janelas do operador e do telão."""

import os
import socket
import sys
import threading
import time
from pathlib import Path

import uvicorn
import webview

from revelacao.banco import Banco
from revelacao.servidor import criar_app

NOME = "Revelação dos GCs"
FUNDO = "#020703"


def pasta_dados() -> Path:
    if os.environ.get("REVELACAO_DADOS"):
        return Path(os.environ["REVELACAO_DADOS"])
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Revelacao GC"
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home())) / "Revelacao GC"
    return Path.home() / ".local" / "share" / "revelacao-gc"


def liberar_autoplay() -> None:
    """O telão nunca recebe clique; sem isto o WebView do Windows e do Linux bloqueia som e vídeo."""
    flag = "--autoplay-policy=no-user-gesture-required"
    if sys.platform == "win32":
        # O pywebview monta os argumentos do WebView2 sozinho (a variável de ambiente é ignorada); este ajuste
        # é o único texto que ele concatena neles. Com valor vazio, a porta de depuração não é aberta.
        webview.settings["REMOTE_DEBUGGING_PORT"] = f" {flag}"
    elif sys.platform.startswith("linux"):
        atual = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
        if flag not in atual:
            os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = f"{atual} {flag}".strip()


def porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Api:
    """Funções nativas expostas ao JavaScript em window.pywebview.api (atributos com _ ficam ocultos)."""

    def __init__(self, app: "Aplicativo", papel: str):
        self._app = app
        self._papel = papel

    def exportar(self) -> str | None:
        janela = self._app.operador
        if not janela:
            return None
        escolha = janela.create_file_dialog(
            webview.FileDialog.SAVE, save_filename="revelacao-gc-backup.zip", file_types=("Backup (*.zip)",)
        )
        if not escolha:
            return None
        destino = Path(escolha if isinstance(escolha, str) else escolha[0])
        self._app.banco.exportar(destino)
        return str(destino)

    def tela_cheia(self) -> None:
        janela = self._app.operador if self._papel == "operador" else self._app.telao
        if janela:
            janela.toggle_fullscreen()

    def telao_tela_cheia(self) -> None:
        if self._app.telao:
            self._app.telao.toggle_fullscreen()

    def abrir_telao(self) -> None:
        self._app.abrir_telao()


class Aplicativo:
    def __init__(self, banco: Banco, url: str):
        self.banco = banco
        self.url = url
        self.operador: webview.Window | None = None
        self.telao: webview.Window | None = None

    def abrir_operador(self) -> None:
        self.operador = webview.create_window(
            f"{NOME} · Operador", f"{self.url}?modo=operador#controle", js_api=Api(self, "operador"),
            width=1240, height=840, min_size=(900, 600), background_color=FUNDO,
        )
        if self.operador:
            self.operador.events.closed += self._operador_fechou

    def abrir_telao(self) -> None:
        if self.telao:
            return
        try:
            telas = list(webview.screens)
        except Exception:
            telas = []
        titulo, url, api = f"{NOME} · Telão", f"{self.url}?modo=telao", Api(self, "telao")
        if len(telas) > 1:
            janela = webview.create_window(
                titulo, url, js_api=api, background_color=FUNDO, screen=telas[1], fullscreen=True
            )
        else:
            janela = webview.create_window(titulo, url, js_api=api, background_color=FUNDO, width=1280, height=720)
        if janela:
            janela.events.closed += self._telao_fechou
        self.telao = janela

    def _telao_fechou(self) -> None:
        self.telao = None

    def _operador_fechou(self) -> None:
        if self.telao:
            self.telao.destroy()


def main() -> None:
    banco = Banco(pasta_dados())
    app = criar_app(banco, Path(__file__).parent / "static")
    porta = int(os.environ.get("REVELACAO_PORTA") or porta_livre())
    servidor = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=porta, log_config=None, loop="asyncio", http="h11")
    )
    threading.Thread(target=servidor.run, daemon=True).start()
    while not servidor.started:
        time.sleep(0.05)

    url = f"http://127.0.0.1:{porta}/"
    if os.environ.get("REVELACAO_SEM_JANELA"):
        print(f"Operador: {url}?modo=operador  Telão: {url}?modo=telao", flush=True)
        threading.Event().wait()

    liberar_autoplay()
    aplicativo = Aplicativo(banco, url)
    aplicativo.abrir_operador()
    aplicativo.abrir_telao()
    webview.start()
    servidor.should_exit = True


if __name__ == "__main__":
    main()
