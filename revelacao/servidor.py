"""API local consumida pelas telas (admin e palco) e servidor dos arquivos estáticos."""

import asyncio
import json
import tempfile
import zipfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from revelacao.banco import Banco


class Canal:
    """Repassa mensagens entre a janela do operador e a do telão (Server-Sent Events)."""

    def __init__(self):
        self.filas: set[asyncio.Queue] = set()

    def publicar(self, mensagem: dict) -> None:
        for fila in list(self.filas):
            fila.put_nowait(mensagem)


def criar_app(banco: Banco, estaticos: Path) -> FastAPI:
    app = FastAPI(title="Revelação dos GCs", docs_url=None, redoc_url=None)
    canal = Canal()

    @app.get("/api/config")
    def ler_config():
        return banco.ler_config()

    @app.put("/api/config")
    async def salvar_config(request: Request):
        banco.salvar_config(await request.json())
        canal.publicar({"tipo": "config", "origem": request.headers.get("x-cliente")})
        return {"ok": True}

    @app.post("/api/comando")
    async def comando(request: Request):
        canal.publicar(await request.json())
        return {"ok": True}

    @app.get("/api/eventos")
    async def eventos(request: Request):
        fila: asyncio.Queue = asyncio.Queue()
        canal.filas.add(fila)

        async def transmitir():
            try:
                yield ": conectado\n\n"
                while not await request.is_disconnected():
                    try:
                        mensagem = await asyncio.wait_for(fila.get(), timeout=15)
                        yield f"data: {json.dumps(mensagem, ensure_ascii=False)}\n\n"
                    except TimeoutError:
                        yield ": ping\n\n"
            finally:
                canal.filas.discard(fila)

        return StreamingResponse(transmitir(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    @app.get("/api/midia")
    def listar_midia():
        return banco.listar_midia()

    @app.post("/api/midia")
    def enviar_midia(arquivo: UploadFile):
        tipo = arquivo.content_type or "application/octet-stream"
        id_ = banco.adicionar_midia(arquivo.filename or "arquivo", tipo, arquivo.file)
        return {"id": id_, "tipo": tipo}

    @app.delete("/api/midia")
    def limpar_midia():
        banco.limpar_midia()
        return {"ok": True}

    @app.delete("/api/midia/{id_}")
    def remover_midia(id_: str):
        banco.remover_midia(id_)
        return {"ok": True}

    @app.get("/midia/{id_}")
    def baixar_midia(id_: str):
        achado = banco.caminho_midia(id_)
        if not achado or not achado[0].exists():
            raise HTTPException(404, "Mídia não encontrada")
        return FileResponse(achado[0], media_type=achado[1])

    @app.get("/api/backup")
    def exportar_backup():
        tmp = Path(tempfile.mkstemp(suffix=".zip")[1])
        banco.exportar(tmp)
        return FileResponse(tmp, filename="revelacao-gc-backup.zip", background=BackgroundTask(tmp.unlink))

    @app.post("/api/backup")
    def importar_backup(arquivo: UploadFile):
        try:
            banco.importar(arquivo.file)
        except (KeyError, ValueError, zipfile.BadZipFile) as erro:
            raise HTTPException(400, f"Backup inválido: {erro}") from erro
        return {"ok": True}

    app.mount("/", StaticFiles(directory=estaticos, html=True), name="estaticos")
    return app
