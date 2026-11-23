"""Acabamentos e luzes de uma proposta de estilo (`acabamentos.yaml`) → dados para o cena.json.

Liga as escolhas do arquiteto (cores da paleta resolvida por `archtools estilo`) às superfícies
e móveis de UM ambiente, e define as luzes das luminárias do layout.

    ambiente: dorm2
    fonte: "proposta dorm2-japandi (Estúdio Ma), 2026-11-17"
    paredes: {padrao: branco_arroz, "1": verde_garrafa}   # índice da parede -> id de cor
    teto: branco_arroz
    piso: null                                           # null = piso existente (neutro)
                                                         # "#RRGGBB" = cor real do revestimento escolhido
                                                         #   (extraída por `archtools paleta`; não é do estilo)
    piso_textura: {tipo: reguas, largura: 200, comprimento: 1200}   # opcional (presets em materiais.TEXTURAS)
    moveis:
      sofa: {cor: pedra, textura: tecido}                # todas as peças; textura opcional
      vaso: {pecas: {vaso: argila}}                      # material da peça do modelo -> cor
      lum-papel: {cor: branco_arroz, forma: esfera}
    luzes:
      lum-papel: {luminaria: pendente_papel, intensidade_w: 40}

Regras:
- Toda cor/luminária precisa existir no estilo RESOLVIDO (itens excluídos por conflito não valem).
- `intensidade_w` é parâmetro de render do Blender (W), não grandeza fotométrica medida.
- A temperatura de cor vem do estilo (K) — nunca escrita aqui: da `camada` de iluminação do
  principal (geral/tarefa/destaque), se indicada; senão, da própria luminária.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .estilo import HEX, Cor, EstiloResolvido, Luminaria
from .geometria import paredes as paredes_amb
from .geometria import deslocamento, pe_direito, poligono_global
from .materiais import PRODUTO
from .schema import Geometria

ESPESSURA_PINTURA = 3  # mm — painel fino rente à face interna da parede (só visual)


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AcabMovel(_Base):
    cor: str | None = None
    pecas: dict[str, str] = Field(default_factory=dict)
    forma: Literal["caixa", "cilindro", "esfera"] | None = None
    textura: str | None = None  # preset de materiais.TEXTURAS; padrão: pelas tags da cor / material da peça


class TexturaPiso(_Base):
    tipo: str
    largura: float | None = Field(default=None, gt=0)       # mm (réguas/placas)
    comprimento: float | None = Field(default=None, gt=0)   # mm


class Luz(_Base):
    luminaria: str
    intensidade_w: float = Field(gt=0)
    # ponto | spot | linha (fita de ponta a ponta sob o móvel). Padrão: linha p/ luminária fita_led, senão ponto.
    # Na linha, intensidade_w é por metro de fita.
    tipo: Literal["ponto", "spot", "linha"] | None = None
    altura: float | None = None  # mm acima da base do móvel; padrão: centro (pendente) ou topo - 50
    camada: Literal["geral", "tarefa", "destaque"] | None = None  # se dada, K = temperatura da camada
    cupula_acesa: bool | None = None  # cúpula brilha à noite; padrão: pendente/piso/coluna
    # spot: ponto para onde aponta, em coordenadas LOCAIS do ambiente (mm); padrão: para baixo
    alvo: list[float] | None = Field(default=None, min_length=3, max_length=3)
    abertura: float | None = Field(default=None, gt=0, le=180)  # spot: ângulo do cone (graus); padrão 70


class Acabamentos(_Base):
    ambiente: str
    fonte: str
    paredes: dict[str, str] = Field(default_factory=dict)
    teto: str | None = None
    piso: str | None = None
    piso_textura: TexturaPiso | None = None
    moveis: dict[str, AcabMovel] = Field(default_factory=dict)
    luzes: dict[str, Luz] = Field(default_factory=dict)


def carregar_acabamentos(arquivo: Path) -> Acabamentos:
    return Acabamentos.model_validate(yaml.safe_load(Path(arquivo).read_text(encoding="utf-8")))


# ------------------------------------------------------------------ cor

def _linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_para_linear(h: str) -> list[float]:
    """#RRGGBB (sRGB) -> RGBA linear (o Blender trabalha em espaço linear)."""
    return [round(_linear(int(h[i:i + 2], 16) / 255), 5) for i in (1, 3, 5)] + [1.0]


def kelvin_para_linear(k: float) -> list[float]:
    """Cor aproximada de um corpo negro (aproximação de Tanner Helland, 1000–40000 K) em RGB linear."""
    t = max(1000, min(40000, k)) / 100
    r = 255 if t <= 66 else 329.698727446 * (t - 60) ** -0.1332047592
    g = 99.4708025861 * math.log(t) - 161.1195681661 if t <= 66 else 288.1221695283 * (t - 60) ** -0.0755148492
    b = 255 if t >= 66 else (0 if t <= 19 else 138.5177312231 * math.log(t - 10) - 305.0447927307)
    return [round(_linear(max(0, min(255, v)) / 255), 5) for v in (r, g, b)]


def textura_padrao(cor: Cor, superficie: str = "objeto") -> str | None:
    """Preset de textura inferido das tags da cor (madeira, couro, metal) ou da superfície (pintura)."""
    tags = set(cor.tags)
    if superficie == "parede":
        return "pintura"
    if tags & {"nogueira", "madeira_clara", "madeira_escura", "madeira"}:
        return "madeira"
    if "couro" in tags:
        return "couro"
    if tags & {"latao", "metal_preto"}:
        return "metal"
    return None


def acabamento_de(cor: Cor, superficie: str = "objeto", tex: str | None = None, **tex_params) -> dict:
    """Material de render: cor + metálico/rugosidade inferidos das tags da cor (+ textura procedural)."""
    from .materiais import textura
    tags = set(cor.tags)
    metal, rug = (1.0, 0.35) if "latao" in tags else (0.8, 0.45) if "metal_preto" in tags else \
        (0.0, 0.45) if "couro" in tags else (0.0, 0.85 if superficie == "parede" else 0.6)
    d = {"cor_id": cor.id, "hex": cor.hex, "rgba": hex_para_linear(cor.hex), "metal": metal, "rugosidade": rug,
         "origem": "estilo"}
    tex = tex or textura_padrao(cor, superficie)
    if tex and tex != "liso":
        d["textura"] = textura(tex, **{k: v for k, v in tex_params.items() if v is not None})
    return d


# ------------------------------------------------------------------ validação + exportação

def _indices(r: EstiloResolvido) -> tuple[dict[str, Cor], dict[str, Luminaria], dict[str, str]]:
    cores = {i.dado.id: i.dado for i in r.paleta}
    lums = {i.dado.id: i.dado for i in r.luminarias}
    origem = {i.dado.id: i.origem for i in [*r.paleta, *r.luminarias]}
    return cores, lums, origem



RECUO_FITA = 30  # mm da borda frontal do móvel até a fita (perfil escondido sob a frente)


def _fita(m: dict, luz: Luz, lum, k: float, origem: str) -> dict:
    """Fita de LED de ponta a ponta sob o móvel: segmento no eixo do comprimento (perpendicular à
    frente), recuado RECUO_FITA da borda frontal, na face de baixo (+ `altura`, se dada)."""
    x0, y0, x1, y1 = m["bbox"]
    f = m["frente"]
    if f[1] == "x":  # frente em x -> fita corre em y
        x = x1 - RECUO_FITA if f == "+x" else x0 + RECUO_FITA
        pos, comp, eixo = [x, (y0 + y1) / 2], y1 - y0, "y"
    else:
        y = y1 - RECUO_FITA if f == "+y" else y0 + RECUO_FITA
        pos, comp, eixo = [(x0 + x1) / 2, y], x1 - x0, "x"
    z = m["z0"] + (luz.altura or 0) - 5
    return {"id": f"luz-{m['id']}", "movel": m["id"], "luminaria": lum.id, "origem": origem,
            "pos": [*pos, z], "tipo": "linha", "eixo": eixo, "comprimento": comp,
            "w_por_m": luz.intensidade_w, "intensidade_w": round(luz.intensidade_w * comp / 1000, 2),
            "temperatura_k": k, "camada": luz.camada, "rgb": kelvin_para_linear(k), "emissor": False}


def validar_acabamentos(acab: Acabamentos, r: EstiloResolvido, geo: Geometria, cena: dict) -> list[str]:
    cores, lums, _ = _indices(r)
    excluidos = {c.item for c in r.conflitos}
    erros: list[str] = []

    def cor_ok(onde: str, cid: str | None) -> None:
        if cid is None:
            return
        if cid in excluidos and cid not in cores:
            erros.append(f"{onde}: cor '{cid}' foi excluída por conflito com o principal")
        elif cid not in cores:
            erros.append(f"{onde}: cor '{cid}' não está na paleta resolvida ({', '.join(cores)})")

    amb = next((a for a in geo.ambientes if a.id == acab.ambiente), None)
    if amb is None:
        return [f"ambiente '{acab.ambiente}' não existe em geometria.yaml"]
    n = len(amb.vertices)
    for k, cid in acab.paredes.items():
        if k != "padrao" and not (k.isdigit() and int(k) < n):
            erros.append(f"paredes: '{k}' não é 'padrao' nem índice de parede (0..{n - 1})")
        cor_ok(f"paredes.{k}", cid)
    from .materiais import TEXTURAS

    def tex_ok(onde: str, t: str | None) -> None:
        if t is not None and t not in TEXTURAS:
            erros.append(f"{onde}: textura '{t}' não existe ({', '.join(TEXTURAS)})")

    tex_ok("piso_textura", acab.piso_textura.tipo if acab.piso_textura else None)
    cor_ok("teto", acab.teto)
    if not (acab.piso and HEX.match(acab.piso)):  # hex = cor real do piso escolhido
        cor_ok("piso", acab.piso)
    moveis = {m["id"]: m for m in cena["moveis"]}
    for mid, am in acab.moveis.items():
        m = moveis.get(mid)
        if m is None:
            erros.append(f"moveis.{mid}: não existe no layout")
            continue
        if m["ambiente"] != acab.ambiente:
            erros.append(f"moveis.{mid}: está em '{m['ambiente']}', não em '{acab.ambiente}'")
        cor_ok(f"moveis.{mid}", am.cor)
        tex_ok(f"moveis.{mid}.textura", am.textura)
        mats = {p.get("material") for p in m["partes"]}
        for peca, cid in am.pecas.items():
            if peca not in mats:
                erros.append(f"moveis.{mid}.pecas: '{peca}' não é material de nenhuma peça ({sorted(filter(None, mats))})")
            cor_ok(f"moveis.{mid}.pecas.{peca}", cid)
    for mid, luz in acab.luzes.items():
        if mid not in moveis:
            erros.append(f"luzes.{mid}: não existe no layout")
        if luz.luminaria not in lums:
            erros.append(f"luzes.{mid}: luminária '{luz.luminaria}' não está no estilo resolvido ({', '.join(lums)})")
        if (luz.alvo is not None or luz.abertura is not None) and luz.tipo != "spot":
            erros.append(f"luzes.{mid}: 'alvo'/'abertura' só valem para tipo 'spot'")
    return erros


def aplicar_acabamentos(cena: dict, acab: Acabamentos, r: EstiloResolvido, geo: Geometria) -> dict:
    """Acrescenta ao cena.json: painéis de pintura, forro colorido, cores dos móveis e luzes.
    Chame `validar_acabamentos` antes (aqui se assume tudo válido)."""
    cores, lums, origem = _indices(r)
    amb = next(a for a in geo.ambientes if a.id == acab.ambiente)
    pol, _ = poligono_global(amb)
    pd = pe_direito(amb, geo).valor or cena["pe_direito"]
    from .cena import _prisma, _superficie  # evita import circular
    from shapely.geometry import Point, Polygon

    cena.setdefault("revestimentos", [])
    cena.setdefault("luzes", [])
    # paredes: painel fino rente à face interna (as aberturas são recortadas no Blender)
    for p in paredes_amb(amb):
        cid = acab.paredes.get(str(p.indice), acab.paredes.get("padrao"))
        if cid is None or p.inicio is None:
            continue
        (ax, ay), (bx, by) = p.inicio, p.fim
        L = math.hypot(bx - ax, by - ay)
        nx, ny = -(by - ay) / L, (bx - ax) / L
        meio = ((ax + bx) / 2, (ay + by) / 2)
        if not pol.contains(Point(meio[0] + nx * 10, meio[1] + ny * 10)):
            nx, ny = -nx, -ny  # normal para dentro do ambiente
        e0, e1 = 0.5, 0.5 + ESPESSURA_PINTURA
        painel = Polygon([(ax + nx * e0, ay + ny * e0), (bx + nx * e0, by + ny * e0),
                          (bx + nx * e1, by + ny * e1), (ax + nx * e1, ay + ny * e1)])
        cena["revestimentos"].append(_prisma(painel, 0, pd, id=f"pintura-{amb.id}-{p.indice}", recortar=True,
                                             **acabamento_de(cores[cid], "parede")))
    if acab.teto:
        cena["revestimentos"].append(_superficie(pol, pd - 1, id=f"teto-{amb.id}", face="baixo",
                                                 **acabamento_de(cores[acab.teto], "parede")))
    if acab.piso:
        pt = acab.piso_textura
        tex = dict(tex=pt.tipo, largura=pt.largura, comprimento=pt.comprimento) if pt else {}
        if HEX.match(acab.piso):  # cor real do revestimento escolhido (não vem do estilo)
            real = Cor(id="cor_real", nome="revestimento real", hex=acab.piso, papel="base", uso="piso")
            ac = {**acabamento_de(real, "piso", **tex), "origem": "cor_real"}
        else:
            ac = acabamento_de(cores[acab.piso], "piso", **tex)
        cena["revestimentos"].append(_superficie(pol, 1, id=f"piso-{amb.id}-cor", **ac))

    from .materiais import PROPRIOS, TEXTURA_DA_PECA
    moveis = {m["id"]: m for m in cena["moveis"]}
    for mid, am in acab.moveis.items():
        m = moveis[mid]
        for pt in m["partes"]:
            mat = pt.get("material")
            cid = am.pecas.get(mat) or (None if mat in PROPRIOS else am.cor)
            if cid:
                tex = am.textura or TEXTURA_DA_PECA.get(pt.get("material")) or textura_padrao(cores[cid])  # a peça manda
                pt["acabamento"] = acabamento_de(cores[cid], tex=tex)
            if am.forma and not m.get("modelo"):
                pt["forma"] = am.forma

    for mid, luz in acab.luzes.items():
        m, lum = moveis[mid], lums[luz.luminaria]
        tipo = luz.tipo or ("linha" if lum.tipo == "fita_led" else "ponto")
        k = r.iluminacao.temperatura_k.get(luz.camada, lum.temperatura_k) if luz.camada else lum.temperatura_k
        if tipo == "linha":
            cena["luzes"].append(_fita(m, luz, lum, k, origem[lum.id]))
            continue
        cupula = next((pt for pt in m["partes"] if pt.get("material") == "cupula"), None)
        x0, y0, x1, y1 = (cupula or m)["bbox"]
        if luz.altura is not None:
            z = m["z0"] + luz.altura
        elif cupula is not None:  # luz no centro do difusor (spot: na base dele)
            z = cupula["z0"] + 10 if tipo == "spot" else (cupula["z0"] + cupula["z1"]) / 2
        elif lum.tipo == "pendente":
            z = (m["z0"] + m["z1"]) / 2
        else:
            z = m["z1"] - 50
        acesa = luz.cupula_acesa if luz.cupula_acesa is not None else lum.tipo in ("pendente", "luminaria_piso", "coluna")
        cena["luzes"].append({"id": f"luz-{mid}", "movel": mid, "luminaria": lum.id, "origem": origem[lum.id],
                              "pos": [(x0 + x1) / 2, (y0 + y1) / 2, z], "tipo": tipo,
                              "intensidade_w": luz.intensidade_w, "temperatura_k": k, "camada": luz.camada,
                              "rgb": kelvin_para_linear(k), "emissor": acesa})
        if tipo == "spot":
            if luz.alvo is not None:
                d, _ = deslocamento(amb)
                cena["luzes"][-1]["alvo"] = [luz.alvo[0] + d[0], luz.alvo[1] + d[1], luz.alvo[2]]
            if luz.abertura is not None:
                cena["luzes"][-1]["abertura"] = luz.abertura
        if lum.tipo == "pendente" and m["z1"] < pd:  # fio até a laje
            cx, cy = (m["bbox"][0] + m["bbox"][2]) / 2, (m["bbox"][1] + m["bbox"][3]) / 2
            m["partes"].append({"bbox": [cx - 4, cy - 4, cx + 4, cy + 4], "z0": m["z1"], "z1": pd,
                                "forma": "cilindro", "material": "metal_preto",
                                "acabamento": dict(PRODUTO["metal_preto"], origem="estilo")})

    cena["estilo"] = {"ambiente": acab.ambiente, "fonte": acab.fonte,
                      "principal": r.escolha.principal, "acentos": r.escolha.acentos}
    cena["suposicoes"] += [
        f"{acab.ambiente}: cores/luzes da proposta de estilo ({acab.fonte}); intensidades = parâmetro de render",
        "luminárias = volumes simples (caixa/esfera); o arco da luminária de arco não é modelado",
    ]
    return cena
