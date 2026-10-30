"""Baixa as fontes do Google Fonts para revelacao/static/fonts, para o app funcionar sem internet."""

import re
import urllib.request
from pathlib import Path

FAMILIAS = (
    "family=Share+Tech+Mono&family=IBM+Plex+Mono:wght@400;600&family=Orbitron:wght@500;700;900"
    "&family=Exo+2:wght@400;600;700&family=Press+Start+2P&family=Chakra+Petch:wght@400;600;700"
    "&family=Cormorant+Garamond:ital,wght@0,600;0,700;1,500&family=Manrope:wght@400;600;700"
    "&family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,800&display=swap"
)
SUBSETS = {"latin", "latin-ext"}
DESTINO = Path(__file__).resolve().parent.parent / "revelacao" / "static" / "fonts"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def baixar(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA})) as r:
        return r.read()


def campo(padrao: str, texto: str) -> str:
    achado = re.search(padrao, texto)
    if not achado:
        raise ValueError(f"padrão {padrao!r} não encontrado no CSS do Google Fonts")
    return achado.group(1)


def main() -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    css = baixar(f"https://fonts.googleapis.com/css2?{FAMILIAS}").decode()
    blocos = re.findall(r"/\* ([\w-]+) \*/\s*(@font-face \{.*?\})", css, re.S)
    saida = []
    for subset, bloco in blocos:
        if subset not in SUBSETS:
            continue
        url = campo(r"url\((https://[^)]+)\)", bloco)
        familia = campo(r"font-family: '([^']+)'", bloco)
        estilo = campo(r"font-style: (\w+)", bloco)
        peso = campo(r"font-weight: ([\d ]+);", bloco).replace(" ", "-")
        nome = f"{familia.replace(' ', '')}-{estilo}-{peso}-{subset}.woff2"
        arquivo = DESTINO / nome
        if not arquivo.exists():
            arquivo.write_bytes(baixar(url))
        saida.append(bloco.replace(url, nome))
    (DESTINO / "fonts.css").write_text("\n".join(saida) + "\n", encoding="utf-8")
    print(f"{len(saida)} faces em {DESTINO}")


if __name__ == "__main__":
    main()
