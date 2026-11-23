"""Materiais de render resolvidos pelo archtools — o Blender não escolhe nenhuma cor.

Toda superfície e toda peça de móvel do cena.json sai com um `acabamento`:

    {"cor_id", "hex", "rgba" (linear), "metal", "rugosidade", "origem"}

`origem` diz de onde veio a aparência:
- `produto`  — cor conhecida de um produto real (fotos enviadas pelo usuário; ver modelos.py);
- `natural`  — representação genérica de algo vivo (folhagem, caule), não é escolha de projeto;
- `estilo`   — cor da paleta resolvida de uma proposta/conceito (acabamentos.yaml);
- `neutro`   — NÃO DEFINIDO: cinza de marcação. Aparece no relatório do render como pendência.

Superfícies da arquitetura sem acabamento conhecido (paredes, teto, piso) também são `neutro`,
em tons claros só para legibilidade — não são proposta de cor.

`textura` (opcional) = preset procedural que o Blender monta sobre a cor (veio de madeira, trama
de tecido, réguas do piso...). O tipo e os parâmetros vêm daqui (TEXTURAS); o Blender só traduz
em nós. Dimensões em mm; `contraste`/`relevo` são parâmetros de render (0..1), não medidas.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path


def _srgb(c: float) -> int:
    v = 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
    return max(0, min(255, round(v * 255)))


# Presets de textura procedural (parâmetros padrão; mm). `reguas` = piso em réguas (porcelanato/madeira).
TEXTURAS: dict[str, dict] = {
    "liso": {},
    "pintura": {"escala": 3, "relevo": 0.04},
    "madeira": {"escala": 60, "contraste": 0.2, "direcao": "x"},
    "reguas": {"largura": 200, "comprimento": 1200, "junta": 2, "contraste": 0.18, "veio": 60},
    "tecido": {"escala": 2, "relevo": 0.35, "contraste": 0.08},
    "cotele": {"escala": 2, "relevo": 0.35, "contraste": 0.08, "nervura": 4.5},  # veludo cotelê: nervuras de 4,5 mm
    "couro": {"escala": 5, "relevo": 0.15, "contraste": 0.06},
    "metal": {"escala": 30, "variacao": 0.12},
    "folhagem": {"escala": 60, "contraste": 0.3},
    "papel": {"escala": 25, "contraste": 0.05},
}


def textura(tipo: str, **params) -> dict:
    if tipo not in TEXTURAS:
        raise ValueError(f"textura '{tipo}' não existe ({', '.join(TEXTURAS)})")
    return {"tipo": tipo, **TEXTURAS[tipo], **params}


def _mat(cor_id: str, rgba_linear, metal: float, rug: float, origem: str, tex: str | None = None, **extra) -> dict:
    r, g, b = rgba_linear[:3]
    d = {"cor_id": cor_id, "hex": f"#{_srgb(r):02X}{_srgb(g):02X}{_srgb(b):02X}",
         "rgba": [round(r, 5), round(g, 5), round(b, 5), 1.0], "metal": metal, "rugosidade": rug,
         "origem": origem, **extra}
    if tex:
        d["textura"] = textura(tex)
    return d


# Cinza de marcação: "aparência ainda não definida". Escolhido para destoar de qualquer paleta.
NEUTRO = _mat("neutro", (0.30, 0.30, 0.30), 0.0, 0.7, "neutro")

# Arquitetura com acabamento desconhecido (só legibilidade; não é proposta de cor).
SUPERFICIES = {
    "parede": _mat("neutro-parede", (0.80, 0.80, 0.80), 0.0, 0.9, "neutro"),
    "teto": _mat("neutro-teto", (0.85, 0.85, 0.85), 0.0, 0.9, "neutro"),
    "piso": _mat("neutro-piso", (0.45, 0.45, 0.45), 0.0, 0.7, "neutro"),
    "piso_externo": _mat("neutro-piso-externo", (0.35, 0.35, 0.35), 0.0, 0.9, "neutro"),
    "cercamento": _mat("neutro-cercamento", (0.25, 0.25, 0.25), 0.0, 0.8, "neutro"),
    "vidro": _mat("vidro", (0.8, 0.9, 1.0), 0.0, 0.05, "neutro", alfa=0.15),
}

# Peças dos modelos de produto (archtools.modelos): cor/acabamento observados nas fotos dos
# produtos reais enviadas pelo usuário (2026-11-17) — aproximações visuais.
PRODUTO = {
    "metal_preto": _mat("metal_preto", (0.02, 0.02, 0.02), 0.8, 0.45, "produto", "metal"),
    "madeira_clara": _mat("madeira_clara", (0.72, 0.56, 0.40), 0.0, 0.55, "produto", "madeira"),
    "preto_brilho": _mat("preto_brilho", (0.01, 0.01, 0.01), 0.0, 0.15, "produto"),
    "cromado": _mat("cromado", (0.85, 0.85, 0.87), 1.0, 0.12, "produto", "metal"),
    "nogueira": _mat("nogueira", (0.30, 0.18, 0.11), 0.0, 0.5, "produto", "madeira"),
    "madeira_pes": _mat("madeira_pes", (0.76, 0.58, 0.40), 0.0, 0.5, "produto", "madeira"),
    "discos": _mat("discos", (0.55, 0.47, 0.36), 0.0, 0.6, "produto"),
    "tela": _mat("tela", (0.03, 0.04, 0.06), 0.0, 0.08, "produto"),
    "tecido_preto": _mat("tecido_preto", (0.04, 0.04, 0.045), 0.0, 0.85, "produto", "tecido"),
    "folhagem": _mat("folhagem", (0.13, 0.35, 0.12), 0.0, 0.7, "natural", "folhagem"),
    "caule": _mat("caule", (0.30, 0.22, 0.12), 0.0, 0.8, "natural"),
    # capas de LP genéricas (rack_vinis) e moldura de TV: representação, não escolha de projeto
    "disco_a": _mat("disco_a", (0.42, 0.10, 0.06), 0.0, 0.5, "produto"),
    "disco_b": _mat("disco_b", (0.75, 0.68, 0.55), 0.0, 0.5, "produto"),
    "disco_c": _mat("disco_c", (0.05, 0.08, 0.12), 0.0, 0.5, "produto"),
    "moldura_tv": _mat("moldura_tv", (0.01, 0.01, 0.01), 0.0, 0.3, "produto"),
    # pegboard: furos (sombra), teclas claras e um controle branco (representação genérica)
    "furo": _mat("furo", (0.003, 0.003, 0.003), 0.0, 0.9, "produto"),
    "tecla": _mat("tecla", (0.55, 0.55, 0.52), 0.0, 0.5, "produto"),
    "controle_b": _mat("controle_b", (0.8, 0.8, 0.78), 0.0, 0.4, "produto"),
    "gancho": _mat("gancho", (0.6, 0.6, 0.62), 1.0, 0.3, "produto"),
    "malha": _mat("malha", (0.035, 0.035, 0.04), 0.0, 0.75, "produto", "tecido"),   # tela do encosto da cadeira
    "hairpin": _mat("hairpin", (0.02, 0.02, 0.02), 0.8, 0.4, "produto", "metal"),
}

# Materiais com aparência própria que a `cor` geral de um item do conceito NÃO pinta (capa de disco,
# tela, cromado): só `pecas:` explícito muda. Ex.: rack com `cor: nogueira` não pinta os LPs.
PROPRIOS = {"disco_a", "disco_b", "disco_c", "tela", "cromado", "moldura_tv", "furo", "tecla", "controle_b", "gancho",
            "malha", "hairpin"}

# Textura de peças de modelo cujo material não tem cor própria (a cor vem do conceito ou da cor real).
TEXTURA_DA_PECA = {"estofado": "tecido", "tapete": "tecido", "cortina": "tecido", "almofada": "tecido",
                   "cupula": "papel", "folhagem": "folhagem", "moldura": "madeira",
                   "metal_preto": "metal", "estrutura": "metal",
                   "livro_a": "liso", "livro_b": "liso", "livro_c": "liso"}  # lombada: papel/tecido liso, não veio


def orientar_veios(cena: dict) -> None:
    """Veio da madeira ao longo do lado maior de cada peça de móvel. `direcao` x = faixas nos planos
    y = constante (veio em x no tampo, vertical nas faces voltadas para x); y = o análogo. Peça mais alta
    que larga (porta, lateral): veio vertical na face larga."""
    for m in cena["moveis"]:
        for pt in m["partes"]:
            t = pt.get("acabamento", {}).get("textura")
            if t and t["tipo"] == "cotele":  # nervuras paralelas à largura: variam ao longo da profundidade
                pt["acabamento"] = {**pt["acabamento"], "textura": {**t, "eixo": (m.get("frente") or "+x")[1]}}
            if t and t["tipo"] == "madeira":
                x0, y0, x1, y1 = pt["bbox"]
                lx, ly = x1 - x0, y1 - y0
                if pt["z1"] - pt["z0"] > max(lx, ly):  # vertical: faixas cortando o lado maior em planta
                    d = "x" if ly >= lx else "y"
                else:
                    d = "x" if lx >= ly else "y"
                pt["acabamento"] = {**pt["acabamento"], "textura": {**t, "direcao": d}}


def de_hex(hex_: str, cor_id: str, origem: str = "produto", tex: str | None = None) -> dict:
    """Acabamento fosco a partir de uma cor sRGB conhecida (ex.: cor_real de produto do catálogo)."""
    from .acabamentos import hex_para_linear
    return _mat(cor_id, hex_para_linear(hex_)[:3], 0.0, 0.6, origem, tex)


def superficie(tipo: str) -> dict:
    return dict(SUPERFICIES[tipo])


def de_peca(material: str | None) -> dict:
    """Acabamento de uma peça pelo nome do material do modelo; desconhecido -> NEUTRO."""
    return dict(PRODUTO.get(material or "", NEUTRO))


def neutros(cena: dict) -> list[str]:
    """Móveis (e peças) que vão ao render sem aparência definida — relatório de pendências."""
    faltam = []
    for m in cena["moveis"]:
        pecas = [pt for pt in m["partes"] if pt.get("acabamento", NEUTRO)["origem"] == "neutro"]
        if not pecas:
            continue
        if len(pecas) == len(m["partes"]):
            faltam.append(m["id"])
        else:
            nomes = sorted({pt.get("material") or pt.get("parte") or "?" for pt in pecas})
            faltam.append(f"{m['id']} ({', '.join(nomes)})")
    return faltam


# ---------------------------------------------------------------- texturas de imagem (fase P4)
# Imagens CC0 em catalogo/texturas/<asset>/ (lista em texturas.yaml; baixadas por baixar.py, fora do
# git). A COR continua sendo a do acabamento: o Blender usa a imagem de cor só como variação de tom
# (luminância / média), mais a rugosidade e o normal. Sem as imagens no disco, fica o preset procedural.
RAIZ_TEXTURAS = Path(__file__).resolve().parents[3] / "catalogo" / "texturas"
IMAGEM_DO_TIPO = {"madeira": "madeira_escura", "tecido": "tecido_estofado", "cotele": "tecido_estofado", "metal": "metal_pintado",
                  "pintura": "parede_pintada", "reguas": "piso_madeira", "papel": "linho"}
IMAGEM_DO_MATERIAL = {"cortina": "linho", "cupula": "linho", "tapete": "fibra_tapete", "cromado": "aco_escovado"}
MAPAS = {"cor": "_Color.jpg", "rugosidade": "_Roughness.jpg", "normal": "_NormalGL.jpg"}


@lru_cache(maxsize=None)
def _catalogo_texturas(raiz: Path) -> dict:
    import yaml
    f = raiz / "texturas.yaml"
    if not f.exists():
        return {}
    return {t["id"]: t for t in yaml.safe_load(f.read_text(encoding="utf-8"))["texturas"]}


@lru_cache(maxsize=None)
def _luminancia_media(arquivo: Path) -> float:
    from PIL import Image, ImageStat
    return round(ImageStat.Stat(Image.open(arquivo).convert("L").resize((128, 128))).mean[0] / 255, 4)


def imagem_textura(tex_id: str, raiz: Path = RAIZ_TEXTURAS) -> dict | None:
    """Mapas da textura `tex_id` (texturas.yaml) se as imagens estiverem no disco; senão None."""
    t = _catalogo_texturas(raiz).get(tex_id)
    if not t:
        return None
    arqs = {k: raiz / t["asset"] / f"{t['asset']}_1K-JPG{suf}" for k, suf in MAPAS.items()}
    if not all(a.exists() for a in arqs.values()):
        return None
    return {"id": tex_id, "asset": t["asset"], "tamanho_mm": t["tamanho_mm"],
            "media": _luminancia_media(arqs["cor"]), **{k: str(a) for k, a in arqs.items()}}


def aplicar_imagens(cena: dict, raiz: Path = RAIZ_TEXTURAS) -> list[str]:
    """Acrescenta `imagem` às texturas do cena.json (móveis e revestimentos) que têm imagem CC0
    disponível. Devolve os ids de textura esperados mas ausentes no disco (ficam procedurais)."""
    faltam: set[str] = set()
    alvos = [(pt.get("material"), pt.get("acabamento")) for m in cena["moveis"] for pt in m["partes"]]
    alvos += [(None, rv) for rv in cena.get("revestimentos", [])]
    for material, ac in alvos:
        t = (ac or {}).get("textura")
        if not t:
            continue
        tex_id = IMAGEM_DO_MATERIAL.get(material) or IMAGEM_DO_TIPO.get(t["tipo"])
        if not tex_id:
            continue
        img = imagem_textura(tex_id, raiz)
        if img is None:
            faltam.add(tex_id)
            continue
        ac["textura"] = {**t, "imagem": img}
    return sorted(faltam)
