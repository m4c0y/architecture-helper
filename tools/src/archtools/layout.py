"""Layout de móveis: esquema de `layout.yaml`, `criterios.yaml` e validações de uso.

Convenções
- Posição do móvel = CENTRO da projeção no piso, em coordenadas LOCAIS do ambiente
  (as mesmas dos vértices; relativas à `posicao` do ambiente, se houver).
- `frente` = direção para onde o lado de uso do móvel aponta (+x, -x, +y, -y).
  `largura` é medida ao longo da frente; `profundidade`, perpendicular a ela.
- `elevacao` = altura da base acima do piso (prateleira suspensa, projetor...).
- Posições são decisões de projeto (sem status). Dimensões são `Medida` (com status).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field
from shapely.affinity import translate
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

from .geometria import TOL_MM, deslocamento, paredes, poligono_global, segmento_abertura
from .schema import Geometria, Medida, Status, status_mais_fraco
from .validacao import Achado

ALTURA_BLOQUEIA_PASSAGEM = 1800  # móvel com base abaixo disso impede circular por baixo
ALCANCE_MIN_MM2 = 100 * 100  # a folga precisa de ao menos 1 dm² alcançável a partir da porta
AREA_MIN_MM2 = 1.0  # após encolher as geometrias em TOL_MM (só toques/frestas de até 5 mm são ignorados)


def _sobreposicao(a, b) -> float:
    """Área (mm²) em que a e b se sobrepõem, ignorando encostos de até TOL_MM."""
    return a.buffer(-TOL_MM, join_style="mitre").intersection(b.buffer(-TOL_MM, join_style="mitre")).area


def _fora(a, contorno) -> float:
    """Área (mm²) de a fora do contorno, com tolerância de TOL_MM."""
    return a.buffer(-TOL_MM, join_style="mitre").difference(contorno).area


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Criterios(_Base):
    decisao: str
    circulacao: dict[str, float]


class Movel(_Base):
    id: str
    nome: str
    ambiente: str
    categoria: Literal[
        "mesa", "cadeira", "sofa", "estante", "armario", "aparador", "cama",
        "bancada", "prateleira", "equipamento", "outro",
    ]
    x: float
    y: float
    frente: Literal["+x", "-x", "+y", "-y"]
    largura: Medida
    profundidade: Medida
    altura: Medida
    elevacao: Medida = Field(
        default_factory=lambda: Medida(valor=0, status="confirmado", fonte="apoiado no piso"))
    folga_frontal: str | None = None  # nome de um critério em criterios.yaml
    folga_largura: float | None = None  # mm; folga centrada mais estreita que o móvel (ex.: cadeira)
    # Forma de estofados (só para o volume 3D; validações usam a pegada e a altura total)
    altura_assento: Medida | None = None
    prof_encosto: Medida | None = None
    braco_largura: Medida | None = None
    braco_altura: Medida | None = None
    bracos: list[Literal["esquerdo", "direito"]] = Field(default_factory=list)  # de quem está sentado
    produto: str | None = None  # id no catálogo (herda medidas/modelo/cor); texto livre em layouts antigos
    modelo: str | None = None  # modelo 3D paramétrico (archtools.modelos.MODELOS); só aparência
    cor_real: str | None = None  # hex da cor conhecida do produto (normalmente herdada do catálogo)
    associado: str | None = None  # id do móvel cuja folga este pode ocupar (ex.: cadeira -> mesa)
    notas: str | None = None


class Layout(_Base):
    nome: str
    descricao: str | None = None
    ambiente: str | None = None  # layout de um ambiente só: vale para itens sem `ambiente`
    moveis: list[Movel] = Field(default_factory=list)


def carregar_layout(caminho: Path, catalogo: dict | None = None, ambiente_padrao: str | None = None) -> Layout:
    """Lê um layout.yaml. Itens com `produto` do catálogo herdam o que não informarem; num
    layout de ambiente (`ambientes/<id>/layout.yaml`) o `ambiente` dos itens é o da pasta."""
    from .catalogo import herdar
    with Path(caminho).open(encoding="utf-8") as f:
        dados = yaml.safe_load(f) or {}
    ambiente_padrao = ambiente_padrao or dados.get("ambiente")
    itens = []
    for item in dados.get("moveis") or []:
        item = herdar(item, catalogo or {})
        if ambiente_padrao is not None:
            if item.setdefault("ambiente", ambiente_padrao) != ambiente_padrao:
                raise ValueError(f"{caminho}: item '{item.get('id')}' está em '{item['ambiente']}', "
                                 f"mas o arquivo é do ambiente '{ambiente_padrao}'")
        pid = item.get("produto")
        if pid and catalogo is not None and pid not in catalogo and "largura" not in item:
            raise ValueError(f"{caminho}: item '{item.get('id')}' usa produto '{pid}', que não está no catálogo")
        itens.append(item)
    dados["moveis"] = itens
    return Layout.model_validate(dados)


def layouts_do_projeto(pasta: Path) -> list[Path]:
    """Layouts aprovados: `ambientes/*/layout.yaml` + o `layout.yaml` único antigo, se existir."""
    pasta = Path(pasta)
    arqs = sorted(pasta.glob("ambientes/*/layout.yaml"))
    if (pasta / "layout.yaml").exists():
        arqs.append(pasta / "layout.yaml")
    return arqs


def ambiente_do_arquivo(arquivo: Path) -> str | None:
    """`.../ambientes/<id>/layout.yaml` -> '<id>'; outros caminhos -> None."""
    p = Path(arquivo)
    return p.parent.name if p.parent.parent.name == "ambientes" else None


def carregar_layout_projeto(pasta: Path, catalogo: dict | None = None) -> Layout | None:
    """Todos os layouts aprovados do projeto num só (para planta geral e cena)."""
    arqs = layouts_do_projeto(pasta)
    if not arqs:
        return None
    moveis, ids = [], set()
    for a in arqs:
        lay = carregar_layout(a, catalogo, ambiente_do_arquivo(a))
        for m in lay.moveis:
            if m.id in ids:
                raise ValueError(f"{a}: id de item repetido entre layouts: '{m.id}'")
            ids.add(m.id)
            moveis.append(m)
    return Layout(nome=Path(pasta).name, descricao="layouts aprovados combinados", moveis=moveis)


def carregar_criterios(projeto_dir: Path) -> Criterios:
    with (Path(projeto_dir) / "criterios.yaml").open(encoding="utf-8") as f:
        return Criterios.model_validate(yaml.safe_load(f))


# ----------------------------------------------------------------------------- geometria


def _dims(m: Movel) -> tuple[float, float] | None:
    """(dx, dy) da projeção no piso, já considerando a orientação."""
    if m.largura.valor is None or m.profundidade.valor is None:
        return None
    w, d = m.largura.valor, m.profundidade.valor
    return (w, d) if m.frente in ("+y", "-y") else (d, w)


def pegada_local(m: Movel) -> Polygon | None:
    dims = _dims(m)
    if dims is None:
        return None
    dx, dy = dims
    return box(m.x - dx / 2, m.y - dy / 2, m.x + dx / 2, m.y + dy / 2)


def zona_uso_local(m: Movel, criterios: Criterios) -> Polygon | None:
    """Retângulo de folga em frente ao lado de uso (largura do móvel x critério)."""
    if m.folga_frontal is None:
        return None
    f = criterios.circulacao[m.folga_frontal]
    p = pegada_local(m)
    if p is None:
        return None
    x0, y0, x1, y1 = p.bounds
    if m.folga_largura is not None:  # estreita a faixa, mantendo-a centrada no móvel
        if m.frente in ("+y", "-y"):
            meia = min(m.folga_largura, x1 - x0) / 2
            x0, x1 = m.x - meia, m.x + meia
        else:
            meia = min(m.folga_largura, y1 - y0) / 2
            y0, y1 = m.y - meia, m.y + meia
    return {
        "+y": box(x0, y1, x1, y1 + f), "-y": box(x0, y0 - f, x1, y0),
        "+x": box(x1, y0, x1 + f, y1), "-x": box(x0 - f, y0, x0, y1),
    }[m.frente]


def _global(geom, amb):
    d, _ = deslocamento(amb)
    return None if geom is None or d is None else translate(geom, d[0], d[1])


def faixa_vertical(m: Movel) -> tuple[float, float]:
    base = m.elevacao.valor or 0
    topo = base + m.altura.valor if m.altura.valor is not None else float("inf")  # desconhecida: conservador
    return base, topo


# Mesa sem modelo = tampo + 4 pernas (o mesmo volume que a cena desenha): cabe coisa embaixo.
MESA_TAMPO, MESA_PERNA, MESA_RECUO = 30, 50, 40  # mm


def volumes(m: Movel, pegada: Polygon) -> list[tuple[Polygon, float, float]]:
    """Volumes (pegada, z0, z1) usados nas colisões. Mesa sem modelo: tampo + pernas; demais: caixa."""
    z0, z1 = faixa_vertical(m)
    if m.categoria != "mesa" or m.modelo or z1 == float("inf") or z1 - z0 <= MESA_TAMPO:
        return [(pegada, z0, z1)]
    x0, y0, x1, y1 = pegada.bounds
    vols = [(box(x0, y0, x1, y1), z1 - MESA_TAMPO, z1)]
    for px in (x0 + MESA_RECUO, x1 - MESA_RECUO - MESA_PERNA):
        for py in (y0 + MESA_RECUO, y1 - MESA_RECUO - MESA_PERNA):
            vols.append((box(px, py, px + MESA_PERNA, py + MESA_PERNA), z0, z1 - MESA_TAMPO))
    return vols


def status_dims(m: Movel) -> Status:
    return status_mais_fraco(m.largura.status, m.profundidade.status)


def giro_porta(geo: Geometria, ab) -> tuple[Polygon, tuple[float, float]] | None:
    """Quarto de círculo varrido pela folha (global) e ponto de acesso interno da porta."""
    amb = next((a for a in geo.ambientes if a.id == ab.ambiente), None)
    ps = paredes(amb) if amb else []
    if ab.parede >= len(ps) or ab.sentido is None:
        return None
    seg = segmento_abertura(ab, ps[ab.parede])
    pol, _ = poligono_global(amb)
    if seg is None or pol is None:
        return None
    a, b, _ = seg
    w = Point(a).distance(Point(b))
    eixo, ponta = (a, b) if ab.sentido.dobradica == "inicio" else (b, a)
    ux, uy = (ponta[0] - eixo[0]) / w, (ponta[1] - eixo[1]) / w
    nx, ny = -uy, ux
    meio = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    if not pol.contains(Point(meio[0] + nx * 10, meio[1] + ny * 10)):
        nx, ny = -nx, -ny
    if ab.sentido.abre_para == "fora":
        return None  # varre o ambiente vizinho; não verificado aqui
    quadrado = Polygon([eixo, (eixo[0] + ux * w, eixo[1] + uy * w),
                        (eixo[0] + (ux + nx) * w, eixo[1] + (uy + ny) * w),
                        (eixo[0] + nx * w, eixo[1] + ny * w)])
    return quadrado.intersection(Point(eixo).buffer(w, quad_segs=32)), (meio[0] + nx * 50, meio[1] + ny * 50)


# ----------------------------------------------------------------------------- validação


def validar_layout(geo: Geometria, layout: Layout, criterios: Criterios) -> list[Achado]:
    achados: list[Achado] = []
    add = achados.append
    ambientes = {a.id: a for a in geo.ambientes}

    pegadas: dict[str, Polygon] = {}
    for m in layout.moveis:
        onde = f"móvel '{m.id}'"
        amb = ambientes.get(m.ambiente)
        if amb is None:
            add(Achado("erro", onde, f"ambiente '{m.ambiente}' não existe"))
            continue
        if m.folga_frontal and m.folga_frontal not in criterios.circulacao:
            add(Achado("erro", onde, f"critério '{m.folga_frontal}' não existe em criterios.yaml"))
        p = _global(pegada_local(m), amb)
        if p is None:
            add(Achado("nao_verificavel", onde, "dimensões ou posição do ambiente desconhecidas"))
            continue
        pegadas[m.id] = p
        pol, _ = poligono_global(amb)
        fora = _fora(p, pol)
        if fora > AREA_MIN_MM2:
            add(Achado("erro", onde, f"sai do ambiente '{amb.id}' em {fora / 1e6:.3f} m²", status_dims(m)))

    moveis = {m.id: m for m in layout.moveis if m.id in pegadas}
    ids = list(moveis)

    # colisões (volumes: pegada + faixa vertical; mesa = tampo + pernas)
    vols = {k: volumes(moveis[k], pegadas[k]) for k in ids}
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            inter = max((_sobreposicao(pa, pb) for pa, za0, za1 in vols[a] for pb, zb0, zb1 in vols[b]
                         if za1 > zb0 and zb1 > za0), default=0.0)
            if inter > AREA_MIN_MM2:
                add(Achado("erro", f"móveis '{a}' e '{b}'", f"colidem ({inter / 1e6:.3f} m²)",
                           status_mais_fraco(status_dims(moveis[a]), status_dims(moveis[b]))))

    # cadeiras se movem: não bloqueiam a circulação nem invadem folgas
    bloqueiam = {k: p for k, p in pegadas.items()
                 if (moveis[k].elevacao.valor or 0) < ALTURA_BLOQUEIA_PASSAGEM and moveis[k].categoria != "cadeira"}

    # zonas de uso
    zonas = {}
    for k, m in moveis.items():
        z = _global(zona_uso_local(m, criterios), ambientes[m.ambiente])
        if z is None:
            continue
        zonas[k] = z
        pol, _ = poligono_global(ambientes[m.ambiente])
        fora = _fora(z, pol)
        if fora > AREA_MIN_MM2:
            add(Achado("erro", f"móvel '{k}'", f"folga '{m.folga_frontal}' sai do ambiente "
                       f"({fora / 1e6:.3f} m²)", status_dims(m)))
        for o, po in bloqueiam.items():
            if o == k or moveis[o].associado == k:
                continue
            inter = z.intersection(po)
            if _sobreposicao(z, po) > AREA_MIN_MM2:
                prof = min(inter.bounds[2] - inter.bounds[0], inter.bounds[3] - inter.bounds[1])
                add(Achado("erro", f"móvel '{k}'",
                           f"folga '{m.folga_frontal}' ({criterios.circulacao[m.folga_frontal]:.0f} mm) "
                           f"invadida por '{o}': {inter.area / 1e6:.2f} m², até {prof:.0f} mm",
                           status_mais_fraco(status_dims(m), status_dims(moveis[o]))))

    # giro das portas
    portas_do_ambiente: dict[str, list] = {}
    for ab in geo.aberturas:
        if ab.tipo != "porta":
            continue
        g = giro_porta(geo, ab)
        if g is None:
            continue
        portas_do_ambiente.setdefault(ab.ambiente, []).append((ab, g))
        for k, p in bloqueiam.items():
            if _sobreposicao(p, g[0]) > AREA_MIN_MM2:
                add(Achado("erro", f"móvel '{k}'", f"no giro da porta '{ab.id}'", status_dims(moveis[k])))

    # janelas: móvel alto encostado na janela
    for ab in geo.aberturas:
        if ab.tipo != "janela" or ab.peitoril is None or ab.peitoril.valor is None:
            continue
        amb = ambientes.get(ab.ambiente)
        ps = paredes(amb) if amb else []
        seg = segmento_abertura(ab, ps[ab.parede]) if ab.parede < len(ps) else None
        if seg is None:
            continue
        faixa =LineString([seg[0], seg[1]]).buffer(300, cap_style="flat")
        for k, p in pegadas.items():
            _, topo = faixa_vertical(moveis[k])
            if _sobreposicao(p, faixa) > AREA_MIN_MM2 and topo > ab.peitoril.valor:
                alt = "desconhecida" if topo == float("inf") else f"{topo:.0f} mm"
                add(Achado("aviso", f"móvel '{k}'",
                           f"em frente à '{ab.id}' com topo ({alt}) acima do peitoril "
                           f"({ab.peitoril.valor:.0f} mm)"))

    # pontos fixos encobertos
    for pf in geo.pontos_fixos:
        amb = ambientes.get(pf.ambiente)
        d, _ = deslocamento(amb) if amb else (None, None)
        if d is None or pf.posicao.x is None:
            continue
        pt = Point(pf.posicao.x + d[0], pf.posicao.y + d[1]).buffer(150)
        for k, p in pegadas.items():
            if p.intersects(pt):
                add(Achado("aviso", f"móvel '{k}'", f"encosta no ponto '{pf.id}' ({pf.tipo}) — verificar acesso"))

    # circulação: das portas até a frente de cada móvel, com passagem secundária
    r = criterios.circulacao["passagem_secundaria"] / 2
    por_ambiente: dict[str, list[str]] = {}
    for k, m in moveis.items():
        por_ambiente.setdefault(m.ambiente, []).append(k)
    for amb_id, ks in por_ambiente.items():
        pol, _ = poligono_global(ambientes[amb_id])
        livre = pol.difference(unary_union([bloqueiam[k] for k in ks if k in bloqueiam]))
        nucleo = livre.buffer(-r)
        acessivel = []
        for ab, (_, acesso) in portas_do_ambiente.get(amb_id, []):
            partes = getattr(nucleo, "geoms", [nucleo])
            comp = [c for c in partes if not c.is_empty and c.distance(Point(acesso)) < r]
            if not comp:
                add(Achado("erro", f"porta '{ab.id}'",
                           f"sem passagem de {2 * r:.0f} mm a partir da porta"))
            acessivel += comp
        if not acessivel:
            if portas_do_ambiente.get(amb_id):
                continue
            add(Achado("nao_verificavel", f"ambiente '{amb_id}'", "sem porta com sentido definido"))
            continue
        alcance = unary_union(acessivel).buffer(r)
        for k in ks:
            if k in zonas and zonas[k].intersection(alcance).area < ALCANCE_MIN_MM2:
                add(Achado("erro", f"móvel '{k}'",
                           f"frente inacessível com passagem de {2 * r:.0f} mm a partir da porta"))
    return achados


def resumo_ocupacao(geo: Geometria, layout: Layout) -> str:
    ambientes = {a.id: a for a in geo.ambientes}
    linhas = []
    por_amb: dict[str, list[Movel]] = {}
    for m in layout.moveis:
        por_amb.setdefault(m.ambiente, []).append(m)
    for amb_id, ms in por_amb.items():
        pol, _ = poligono_global(ambientes[amb_id])
        piso = [_global(pegada_local(m), ambientes[amb_id]) for m in ms
                if (m.elevacao.valor or 0) < ALTURA_BLOQUEIA_PASSAGEM]
        ocup = unary_union([p for p in piso if p is not None]).area
        linhas.append(f"{amb_id}: área {pol.area / 1e6:.2f} m², ocupada no piso {ocup / 1e6:.2f} m² "
                      f"({100 * ocup / pol.area:.0f}%), livre {(pol.area - ocup) / 1e6:.2f} m²")
    return "\n".join(linhas)
