"""Baixa as texturas CC0 listadas em texturas.yaml (ambientCG, 1K-JPG) para catalogo/texturas/<asset>/.

    uv run --project tools python catalogo/texturas/baixar.py

Extrai só os mapas usados (cor, rugosidade, normal OpenGL) — nenhum outro arquivo do ZIP.
Já baixadas são puladas.
"""
import io
import urllib.request
import zipfile
from pathlib import Path

import yaml

AQUI = Path(__file__).resolve().parent
MAPAS = ("_Color.jpg", "_Roughness.jpg", "_NormalGL.jpg")

for t in yaml.safe_load((AQUI / "texturas.yaml").read_text(encoding="utf-8"))["texturas"]:
    destino = AQUI / t["asset"]
    if destino.exists() and all((destino / f"{t['asset']}_1K-JPG{m}").exists() for m in MAPAS):
        print(f"ok (já existe): {t['asset']}")
        continue
    url = f"https://ambientcg.com/get?file={t['asset']}_1K-JPG.zip"
    req = urllib.request.Request(url, headers={"User-Agent": "archtools-texturas"})
    dados = urllib.request.urlopen(req, timeout=120).read()
    destino.mkdir(exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(dados)) as z:
        for nome in z.namelist():
            base = Path(nome).name
            if base.endswith(MAPAS) and "/" not in nome.strip("/"):
                (destino / base).write_bytes(z.read(nome))
    print(f"baixado: {t['asset']} ({len(dados) / 1e6:.1f} MB) -> {sorted(p.name for p in destino.iterdir())}")
