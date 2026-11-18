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
"""

from __future__ import annotations


def _srgb(c: float) -> int:
    v = 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
    return max(0, min(255, round(v * 255)))


def _mat(cor_id: str, rgba_linear, metal: float, rug: float, origem: str, **extra) -> dict:
    r, g, b = rgba_linear[:3]
    return {"cor_id": cor_id, "hex": f"#{_srgb(r):02X}{_srgb(g):02X}{_srgb(b):02X}",
            "rgba": [round(r, 5), round(g, 5), round(b, 5), 1.0], "metal": metal, "rugosidade": rug,
            "origem": origem, **extra}


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
    "metal_preto": _mat("metal_preto", (0.02, 0.02, 0.02), 0.8, 0.45, "produto"),
    "madeira_clara": _mat("madeira_clara", (0.72, 0.56, 0.40), 0.0, 0.55, "produto"),
    "preto_brilho": _mat("preto_brilho", (0.01, 0.01, 0.01), 0.0, 0.15, "produto"),
    "cromado": _mat("cromado", (0.85, 0.85, 0.87), 1.0, 0.12, "produto"),
    "nogueira": _mat("nogueira", (0.30, 0.18, 0.11), 0.0, 0.5, "produto"),
    "madeira_pes": _mat("madeira_pes", (0.76, 0.58, 0.40), 0.0, 0.5, "produto"),
    "discos": _mat("discos", (0.55, 0.47, 0.36), 0.0, 0.6, "produto"),
    "tela": _mat("tela", (0.03, 0.04, 0.06), 0.0, 0.08, "produto"),
    "tecido_preto": _mat("tecido_preto", (0.04, 0.04, 0.045), 0.0, 0.85, "produto"),
    "folhagem": _mat("folhagem", (0.13, 0.35, 0.12), 0.0, 0.7, "natural"),
    "caule": _mat("caule", (0.30, 0.22, 0.12), 0.0, 0.8, "natural"),
}


def de_hex(hex_: str, cor_id: str, origem: str = "produto") -> dict:
    """Acabamento fosco a partir de uma cor sRGB conhecida (ex.: cor_real de produto do catálogo)."""
    from .acabamentos import hex_para_linear
    return _mat(cor_id, hex_para_linear(hex_)[:3], 0.0, 0.6, origem)


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
