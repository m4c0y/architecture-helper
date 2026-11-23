"""Acabamento fotográfico com IA (fase P5) das imagens do render final — imagens ILUSTRATIVAS.

    uv run --project tools archtools ia projetos/<p> --ambiente dorm2

Lê `ambientes/<id>/render_final.yaml` (câmeras, períodos, pasta `saida` e o bloco `ia:`), manda cada
render do Blender para o modelo de edição de imagem do Gemini (Google AI Studio) com um prompt que
pede fotorrealismo SEM mudar composição, móveis, cores ou luz, e grava em `<saida>/ia/` com o selo
"ILUSTRATIVA (IA)" no canto. O render do Blender continua sendo a imagem que vale (medidas, cores).

Chave da API: variável de ambiente GEMINI_API_KEY ou o arquivo ~/.archtools/gemini.key (fora do
repositório). A chave nunca vai para a URL nem para os relatórios.
"""
from __future__ import annotations

import base64
import io
import json
import os
import urllib.request
from datetime import datetime
from pathlib import Path

import yaml

MODELO_PADRAO = "gemini-2.5-flash-image"
URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
ARQUIVO_CHAVE = Path.home() / ".archtools" / "gemini.key"
SELO = "ILUSTRATIVA (IA)"

PROMPT_BASE = (
    "EDIT the first image (a rough 3D render) into a real photograph of the SAME view. "
    "The output must overlay the input exactly: same camera, same crop and zoom, same horizon and "
    "vanishing points, the same wall corners, ceiling line, window and door openings in the same "
    "pixels. Do not zoom out, do not show any part of the room outside the frame, do not move, mirror "
    "or re-arrange anything, do not change which wall is which.\n"
    "Every object stays where it is in the input, with the same footprint, height and color; nothing "
    "is added and nothing is removed (if something is cut by the image border, keep it cut the same "
    "way). Many objects are crude placeholders (boxes, tubes, rolls, blobs): replace each one, in "
    "place, with the real detailed object listed below; when a product photo is attached, that "
    "object must look exactly like the product. Never keep a placeholder shape.\n"
    "Photographic quality: indistinguishable from a real interior photo taken with a full-frame "
    "camera — real materials, natural light falloff and bounce, soft shadows, fine grain; nothing "
    "that looks 3D, CGI, plastic or clay. No people, no text, no watermark."
)
PERIODO = {
    "dia": "Daylight: soft natural light entering only through the window and the door opening.",
    "noite": "Night: dark outside the window; the room is lit only by its warm lamps and LED strips.",
}


def chave() -> str:
    k = os.environ.get("GEMINI_API_KEY", "").strip()
    if not k and ARQUIVO_CHAVE.exists():
        k = ARQUIVO_CHAVE.read_text(encoding="utf-8").strip()
    if not k:
        raise RuntimeError(f"sem chave do Gemini: defina GEMINI_API_KEY ou crie {ARQUIVO_CHAVE}")
    return k


SENSOR = 36.0  # mm: largura do sensor da câmera do Blender (padrão; ajuste horizontal)


def itens_na_camera(cena: dict, cam_id: str, ambiente: str | None = None, proporcao: float = 16 / 9) -> list[dict]:
    """Onde cada móvel aparece na imagem da câmera `cam_id` (projeção do centro da caixa; sem
    oclusão): [{"id", "nome", "x", "y"}] com x, y em fração da imagem (0 = esquerda/topo)."""
    import math
    cam = next(c for c in cena["cameras"] if c["id"] == cam_id)
    p, a = cam["pos"], cam["alvo"]
    f = [a[i] - p[i] for i in range(3)]
    nf = math.sqrt(sum(v * v for v in f))
    f = [v / nf for v in f]
    r = [f[1], -f[0], 0.0]  # f × (0, 0, 1)
    nr = math.sqrt(r[0] ** 2 + r[1] ** 2) or 1.0
    r = [v / nr for v in r]
    u = [r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0]]
    esc = cam.get("lente", 18) / SENSOR

    def tela(pt):
        d = [pt[i] - p[i] for i in range(3)]
        z = sum(d[i] * f[i] for i in range(3))
        if z <= 100:
            return None
        return (0.5 + sum(d[i] * r[i] for i in range(3)) / z * esc,
                0.5 - sum(d[i] * u[i] for i in range(3)) / z * esc * proporcao)

    itens = []
    for m in cena["moveis"]:
        if ambiente and m.get("ambiente") != ambiente:
            continue
        x0, y0, x1, y1 = m["bbox"]
        if x0 <= p[0] <= x1 and y0 <= p[1] <= y1:
            continue  # a câmera está sobre o item (ex.: sentado no sofá): ele não aparece de fato
        cantos = [tela((x, y, z)) for x in (x0, x1) for y in (y0, y1) for z in (m["z0"], m["z1"])]
        cantos = [c for c in cantos if c]
        if not cantos:
            continue
        sx0, sx1 = min(c[0] for c in cantos), max(c[0] for c in cantos)
        sy0, sy1 = min(c[1] for c in cantos), max(c[1] for c in cantos)
        cx0, cx1, cy0, cy1 = max(sx0, 0), min(sx1, 1), max(sy0, 0), min(sy1, 1)
        if cx1 - cx0 < 0.01 or cy1 - cy0 < 0.01:
            continue  # fora do quadro (a caixa projetada não cruza a imagem)
        nome = m["nome"].split(" (ref")[0].split(" (OPCIONAL")[0]  # sem as notas de origem
        fracao = (cx1 - cx0) * (cy1 - cy0) / max((sx1 - sx0) * (sy1 - sy0), 1e-9)  # quanto da caixa projetada aparece
        itens.append({"id": m["id"], "nome": nome, "x": round((cx0 + cx1) / 2, 2), "y": round((cy0 + cy1) / 2, 2),
                      "cortado": sx0 < -0.01 or sx1 > 1.01 or sy0 < -0.01 or sy1 > 1.01, "fracao": round(fracao, 2)})
    return sorted(itens, key=lambda i: (i["x"], i["y"]))


def _onde(x: float, y: float) -> str:
    h = "left" if x < 0.2 else "center-left" if x < 0.4 else "center" if x < 0.6 else "center-right" if x < 0.8 else "right"
    v = "top" if y < 0.2 else "upper" if y < 0.4 else "middle" if y < 0.6 else "lower" if y < 0.8 else "bottom"
    return f"{v} {h} (x {x:.0%}, y {y:.0%})"


def montar_prompt(descricao: str | None, periodo: str | None, itens: list[dict] | None = None) -> str:
    partes = [PROMPT_BASE]
    if descricao:
        partes.append("Materials and colors (only for objects that are in the image): " + " ".join(descricao.split()))
    if itens:
        partes.append(
            "Objects in the image (names in Portuguese) and where the visible part of each one is — "
            "these and only these; keep each at its place:")
        partes += [f"- {i['nome']}: {_onde(i['x'], i['y'])}" + (" — partly cut by the image border, keep it cut"
                                                               if i.get("cortado") else "") for i in itens]
    if periodo in PERIODO:
        partes.append(PERIODO[periodo])
    return "\n".join(partes)


def _jpeg(img: bytes, lado_max: int | None = None) -> dict:
    from PIL import Image
    im = Image.open(io.BytesIO(img)).convert("RGB")
    if lado_max:
        im.thumbnail((lado_max, lado_max))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=92)
    return {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(buf.getvalue()).decode()}}


def corpo_requisicao(img_png: bytes, prompt: str, proporcao: str = "16:9", referencias=(),
                     tamanho: str | None = None) -> dict:
    """Render primeiro; depois as imagens de referência (ex.: foto do produto real), cada uma
    precedida do texto que diz o que ela mostra."""
    partes = [{"text": prompt}, _jpeg(img_png)]
    for texto, img in referencias:
        partes += [{"text": f"Reference image: {texto}"}, _jpeg(img, 1600)]
    cfg = {"aspectRatio": proporcao}
    if tamanho:
        cfg["imageSize"] = tamanho
    return {"contents": [{"parts": partes}],
            "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": cfg}}


def imagem_da_resposta(resp: dict) -> bytes:
    for cand in resp.get("candidates", []):
        for parte in (cand.get("content") or {}).get("parts", []):
            dado = parte.get("inlineData") or parte.get("inline_data")
            if dado and dado.get("data"):
                return base64.b64decode(dado["data"])
    motivo = [c.get("finishReason") for c in resp.get("candidates", [])] or resp.get("promptFeedback")
    raise RuntimeError(f"o modelo não devolveu imagem (motivo: {motivo})")


def chamar(img_png: bytes, prompt: str, modelo: str, k: str, timeout: int = 300, referencias=(),
           tamanho: str | None = None) -> bytes:
    req = urllib.request.Request(URL.format(modelo=modelo), method="POST",
                                 data=json.dumps(corpo_requisicao(img_png, prompt, referencias=referencias,
                                                                  tamanho=tamanho)).encode(),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": k})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return imagem_da_resposta(json.loads(r.read()))


def selar(img: bytes, texto: str = SELO) -> bytes:
    """Selo visível no canto inferior direito: a imagem é ilustrativa, não o render de projeto."""
    from PIL import Image, ImageDraw, ImageFont
    im = Image.open(io.BytesIO(img)).convert("RGB")
    d = ImageDraw.Draw(im)
    tam = max(14, im.width // 70)
    try:
        fonte = ImageFont.truetype("arial.ttf", tam)
    except OSError:
        fonte = ImageFont.load_default()
    x0, y0, x1, y1 = d.textbbox((0, 0), texto, font=fonte)
    m = tam // 2
    pos = (im.width - (x1 - x0) - 2 * m, im.height - (y1 - y0) - 2 * m)
    d.rectangle([pos[0] - m, pos[1] - m, im.width - m, im.height - m], fill=(0, 0, 0))
    d.text(pos, texto, fill=(255, 255, 255), font=fonte)
    out = io.BytesIO()
    im.save(out, "PNG")
    return out.getvalue()


MAX_REFERENCIAS = 10  # fotos por imagem (o modelo aceita poucas; as dos itens maiores/mais centrais primeiro)


def fotos_dos_produtos(pasta: Path) -> dict[str, list[Path]]:
    """{id do produto: [fotos]} a partir do campo `fotos` do catálogo do projeto."""
    out = {}
    for f in sorted((pasta / "catalogo" / "produtos").glob("*.yaml")):
        dados = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        fotos = [pasta / p for p in dados.get("fotos") or []]
        if fotos:
            out[dados.get("id", f.stem)] = fotos
    return out


def referencias_da_camera(cena: dict, itens: list[dict], fotos: dict[str, list[Path]]) -> list[tuple[str, Path]]:
    """(texto, foto) para cada produto com foto que aparece na imagem."""
    produto = {m["id"]: m.get("produto") for m in cena["moveis"]}
    refs = []
    for i in sorted(itens, key=lambda i: abs(i["x"] - 0.5) + abs(i["y"] - 0.5)):
        for foto in fotos.get(produto.get(i["id"]) or "", []):
            refs.append((f"product photo of '{i['nome']}' (in the image at {_onde(i['x'], i['y'])}): "
                         "use it ONLY for how this one object looks (shape, details, material, color). "
                         "Ignore everything else in the photo — background, room, other furniture, "
                         "footstools, rugs, decor — none of it exists in the room", foto))
    return refs[:MAX_REFERENCIAS]


def rodar(pasta: Path, ambiente: str, chamada=chamar, k: str | None = None) -> tuple[list[Path], list[Path]]:
    """Polir todas as imagens do render final do ambiente. Devolve (gerados, entradas)."""
    cfg_arq = pasta / "ambientes" / ambiente / "render_final.yaml"
    cfg = yaml.safe_load(cfg_arq.read_text(encoding="utf-8")) or {}
    ia = cfg.get("ia") or {}
    modelo = ia.get("modelo", MODELO_PADRAO)
    refs_cfg = ia.get("referencias", [])  # {imagem, descricao, item?}: com `item`, só nas vistas onde ele aparece
    tamanho = ia.get("tamanho")
    origem = pasta / cfg.get("saida", "saidas/final") / "blender"
    destino = origem.parent / "ia"
    destino.mkdir(parents=True, exist_ok=True)
    k = k or chave()
    cena_arq = pasta / "saidas" / "cena.json"
    cena = json.loads(cena_arq.read_text(encoding="utf-8")) if cena_arq.exists() else None
    gerados, entradas, rel = [], [cfg_arq] + ([cena_arq] if cena else []), []
    fotos = fotos_dos_produtos(pasta)
    for cam in cfg.get("cameras", []):
        for per in cfg.get("periodos", ["dia"]):
            fonte = origem / f"{ambiente}-{cam}-{per}.png"
            if not fonte.exists():
                print(f"falta o render: {fonte} (pulado)")
                continue
            itens = itens_na_camera(cena, f"{ambiente}-{cam}", ambiente) if cena else None
            prompt = montar_prompt(ia.get("descricao"), per, itens)
            refs_cam = referencias_da_camera(cena, itens, fotos) if cena else []
            visiveis = {i["id"]: i for i in itens or []}
            refs = [((f"{r['descricao']} (this is '{visiveis[r['item']]['nome']}', center at "
                      f"{_onde(visiveis[r['item']]['x'], visiveis[r['item']]['y'])})" if r.get("item") else r["descricao"]),
                     (pasta / r["imagem"]).read_bytes())
                    for r in refs_cfg if not r.get("item") or r["item"] in visiveis]
            todas = refs + [(t, f.read_bytes()) for t, f in refs_cam]
            img = selar(chamada(fonte.read_bytes(), prompt, modelo, k, referencias=todas, tamanho=tamanho))
            entradas += [f for _, f in refs_cam]
            alvo = destino / f"{ambiente}-{cam}-{per}-ia.png"
            alvo.write_bytes(img)
            gerados.append(alvo)
            entradas.append(fonte)
            rel.append({"imagem": alvo.name, "render": fonte.name, "modelo": modelo, "prompt": prompt,
                        "referencias": [r["imagem"] for r in refs_cfg if not r.get("item") or r["item"] in visiveis]
                        + [str(f.relative_to(pasta)) for _, f in refs_cam]})
            print(f"gerado: {alvo}")
    (destino / "relatorio.json").write_text(json.dumps(
        {"gerado_em": datetime.now().isoformat(timespec="seconds"), "aviso": "imagens ILUSTRATIVAS geradas por IA; "
         "o render do Blender é a referência de medidas e cores", "imagens": rel}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    gerados.append(destino / "relatorio.json")
    return gerados, entradas
