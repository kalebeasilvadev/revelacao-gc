"""Persistência: configuração do evento no SQLite e arquivos de mídia numa pasta ao lado."""

import json
import shutil
import sqlite3
import threading
import uuid
import zipfile
from pathlib import Path
from typing import IO


class Banco:
    def __init__(self, pasta: Path):
        self.pasta = pasta
        self.pasta_midia = pasta / "midia"
        self.pasta_midia.mkdir(parents=True, exist_ok=True)
        self._trava = threading.Lock()
        self._con = sqlite3.connect(pasta / "revelacao.db", check_same_thread=False)
        self._con.executescript(
            """
            create table if not exists config (
                id integer primary key check (id = 1),
                dados text not null,
                atualizado_em text not null default (datetime('now'))
            );
            create table if not exists midia (
                id text primary key,
                nome text not null,
                tipo text not null,
                arquivo text not null,
                criado_em text not null default (datetime('now'))
            );
            """
        )

    def ler_config(self) -> dict | None:
        with self._trava:
            linha = self._con.execute("select dados from config where id = 1").fetchone()
        return json.loads(linha[0]) if linha else None

    def salvar_config(self, dados: dict) -> None:
        with self._trava, self._con:
            self._con.execute(
                "insert into config (id, dados) values (1, ?) "
                "on conflict(id) do update set dados = excluded.dados, atualizado_em = datetime('now')",
                (json.dumps(dados, ensure_ascii=False),),
            )

    def listar_midia(self) -> list[dict]:
        with self._trava:
            linhas = self._con.execute("select id, nome, tipo from midia order by criado_em").fetchall()
        return [{"id": i, "nome": n, "tipo": t} for i, n, t in linhas]

    def adicionar_midia(self, nome: str, tipo: str, conteudo: IO[bytes], id_: str | None = None) -> str:
        id_ = id_ or uuid.uuid4().hex
        arquivo = id_ + Path(nome).suffix.lower()
        with open(self.pasta_midia / arquivo, "wb") as destino:
            shutil.copyfileobj(conteudo, destino)
        with self._trava, self._con:
            self._con.execute(
                "insert into midia (id, nome, tipo, arquivo) values (?, ?, ?, ?)", (id_, nome, tipo, arquivo)
            )
        return id_

    def caminho_midia(self, id_: str) -> tuple[Path, str] | None:
        with self._trava:
            linha = self._con.execute("select arquivo, tipo from midia where id = ?", (id_,)).fetchone()
        return (self.pasta_midia / linha[0], linha[1]) if linha else None

    def remover_midia(self, id_: str) -> None:
        achado = self.caminho_midia(id_)
        with self._trava, self._con:
            self._con.execute("delete from midia where id = ?", (id_,))
        if achado:
            achado[0].unlink(missing_ok=True)

    def limpar_midia(self) -> None:
        for m in self.listar_midia():
            self.remover_midia(m["id"])

    def exportar(self, destino: Path) -> None:
        midias = self.listar_midia()
        with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("config.json", json.dumps(self.ler_config(), ensure_ascii=False))
            z.writestr("midia.json", json.dumps(midias, ensure_ascii=False))
            for m in midias:
                achado = self.caminho_midia(m["id"])
                if achado and achado[0].exists():
                    z.write(achado[0], f"midia/{m['id']}")

    def importar(self, origem: IO[bytes]) -> None:
        with zipfile.ZipFile(origem) as z:
            config = json.loads(z.read("config.json"))
            midias = json.loads(z.read("midia.json"))
            faltando = [m["id"] for m in midias if f"midia/{m['id']}" not in z.namelist()]
            if faltando:
                raise ValueError(f"arquivos de mídia ausentes no backup: {', '.join(faltando)}")
            self.limpar_midia()
            for m in midias:
                with z.open(f"midia/{m['id']}") as conteudo:
                    self.adicionar_midia(m["nome"], m["tipo"], conteudo, m["id"])
        if config:
            self.salvar_config(config)
