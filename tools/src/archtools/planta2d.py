"""Planta 2D gerada a partir de `geometria.yaml` (PNG + SVG).

Convenção visual:
- linha contínua preta = parede com dados confirmados
- linha tracejada laranja = parede com dados estimados
- aberturas em azul; arco de giro de portas quando há 'sentido'
- pontos fixos como marcadores com o id
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Arc, Patch  # noqa: E402
from shapely.geometry import Point  # noqa: E402
from shapely.ops import polylabel  # noqa: E402

from .geometria import (  # noqa: E402
    area_m2, deslocamento, formatar, paredes, poligono_global, segmento_abertura,
)
from .geometria import de_medida as _de  # noqa: E402
from .schema import Geometria, Status  # noqa: E402

COR = {Status.confirmado: "black", Status.estimado: "darkorange"}
ESTILO = {Status.confirmado: "-", Status.estimado: "--"}
FUNDO = {"interno": "#f2f2f2", "varanda": "#e3edf9", "externo": "#e4f3dc", "tecnico": "#e6e6e6"}


def desenhar(geo: Geometria, destino: Path, layout=None, criterios=None,
             recorte: str | None = None, nome: str = "planta") -> list[Path]:
    """Desenha a planta. Com `layout`, inclui móveis e folgas; `recorte` = id de ambiente para zoom."""
    destino.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(12, 10))
    ax.set_aspect("equal")
    sem_geometria = []
    ambientes = {a.id: a for a in geo.ambientes}

    for amb in geo.ambientes:
        pol, _ = poligono_global(amb)
        if pol is None:
            sem_geometria.append(amb.id)
            continue
        _, st_pos = deslocamento(amb)
        xs, ys = pol.exterior.xy
        ax.fill(xs, ys, color=FUNDO[amb.tipo], zorder=0)
        espessura = 0.8 if amb.tipo == "externo" else 2  # externo: limite, não parede
        for p in paredes(amb):
            if p.inicio is None:
                continue
            st = p.comprimento.status
            ax.plot([p.inicio[0], p.fim[0]], [p.inicio[1], p.fim[1]],
                    color=COR[st], linestyle=ESTILO[st], linewidth=espessura, zorder=2)
            if amb.tipo == "externo":
                continue  # comprimentos de áreas externas ficam no quadro de áreas
            mx, my = _para_dentro(pol, p.inicio, p.fim, 180)
            ax.annotate(f"p{p.indice}: {formatar(p.comprimento).replace(' (estimado)', '')}",
                        (mx, my), fontsize=7, color=COR[st], ha="center", va="center",
                        bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.8), zorder=4)
        c = polylabel(pol, tolerance=10)  # ponto mais afastado das bordas
        pequeno = pol.area < 5e6  # < 5 m²: rótulo compacto para não colidir
        area_txt = formatar(area_m2(amb), "m²", 2).replace(" (estimado)", "")
        rotulo = f"{amb.nome}\n{area_txt}"
        if st_pos is Status.estimado and not pequeno:
            rotulo += "\n(posição estimada)"
        ax.text(c.x, c.y, rotulo, ha="center", va="center", fontsize=6 if pequeno else 9,
                weight="bold", zorder=5, alpha=0.85)

    for ab in geo.aberturas:
        amb = ambientes.get(ab.ambiente)
        ps = paredes(amb) if amb else []
        if ab.parede >= len(ps):
            continue
        seg = segmento_abertura(ab, ps[ab.parede])
        if seg is None:
            continue
        (ax_, ay), (bx, by), st = seg
        ax.plot([ax_, bx], [ay, by], color="white", linewidth=4, zorder=3)
        ax.plot([ax_, bx], [ay, by], color="royalblue", linewidth=1.5,
                linestyle=ESTILO[st], zorder=3)
        ax.text((ax_ + bx) / 2, (ay + by) / 2, ab.id, fontsize=6, color="royalblue",
                ha="center", va="bottom", zorder=4)
        if ab.tipo == "porta" and ab.sentido is not None:
            _arco_porta(ax, amb, ab, (ax_, ay), (bx, by))

    for pf in geo.pontos_fixos:
        amb = ambientes.get(pf.ambiente)
        d, _ = deslocamento(amb) if amb else (None, None)
        if pf.posicao.status is Status.desconhecido or d is None:
            continue
        x, y = pf.posicao.x + d[0], pf.posicao.y + d[1]
        ax.plot(x, y, marker="o", markersize=4, color="crimson", zorder=6)
        ax.annotate(pf.id, (x, y), xytext=(3, 3), textcoords="offset points",
                    fontsize=6, color="crimson", zorder=6)

    for c in geo.cercamentos:
        pts = [(p.x, p.y) for p in c.pontos if p.status is not Status.desconhecido]
        if len(pts) < 2:
            continue
        ax.plot(*zip(*pts), color="forestgreen", linewidth=2.5, linestyle="-.", zorder=3)
        meio = pts[len(pts) // 2 - 1], pts[len(pts) // 2]
        ax.text((meio[0][0] + meio[1][0]) / 2, (meio[0][1] + meio[1][1]) / 2,
                f"{c.tipo} h={formatar(_de(c.altura), 'mm').replace(' (estimado)', '')}",
                fontsize=7, color="forestgreen", ha="center", va="bottom", zorder=6)

    legenda = [Line2D([], [], color="black", label="confirmado"),
               Line2D([], [], color="darkorange", linestyle="--", label="estimado"),
               Line2D([], [], color="royalblue", label="abertura"),
               Line2D([], [], color="crimson", marker="o", linestyle="", label="ponto fixo"),
               Line2D([], [], color="forestgreen", linestyle="-.", label="cercamento")]
    ax.legend(handles=legenda, loc="upper right", fontsize=8)
    titulo = f"{geo.projeto} — planta gerada do YAML (mm)"
    if layout is not None:
        _desenhar_layout(ax, geo, layout, criterios)
        titulo += f"\nlayout: {layout.nome}"
        legenda += [Patch(facecolor="#d9b38c", edgecolor="saddlebrown", label="móvel (piso)"),
                    Patch(facecolor="none", edgecolor="saddlebrown", hatch="//", label="móvel suspenso"),
                    Patch(facecolor="#fff3b0", edgecolor="goldenrod", linestyle=":", label="folga de uso")]
        ax.legend(handles=legenda, loc="upper right", fontsize=8)
    if sem_geometria:
        titulo += f"\nsem geometria: {', '.join(sem_geometria)}"
    if recorte is not None:
        pol, _ = poligono_global(ambientes[recorte])
        x0, y0, x1, y1 = pol.bounds
        ax.set_xlim(x0 - 500, x1 + 500)
        ax.set_ylim(y0 - 500, y1 + 500)
        for t in ax.texts:  # rótulos de outros ambientes não vazam para fora do recorte
            t.set_clip_on(True)
        ax.set_title  # noqa: B018
        ax.legend(handles=legenda, loc="upper left", bbox_to_anchor=(1.01, 1), fontsize=8)
    ax.set_title(titulo, fontsize=10)
    ax.grid(True, linewidth=0.3, alpha=0.5)
    ax.tick_params(labelsize=7)

    saidas = [destino / f"{nome}.png", destino / f"{nome}.svg"]
    fig.savefig(saidas[0], dpi=150, bbox_inches="tight")
    fig.savefig(saidas[1], bbox_inches="tight")
    plt.close(fig)
    return saidas


def _desenhar_layout(ax, geo, layout, criterios) -> None:
    from .layout import _global, pegada_local, zona_uso_local
    ambientes = {a.id: a for a in geo.ambientes}
    for m in layout.moveis:
        amb = ambientes.get(m.ambiente)
        if amb is None:
            continue
        if criterios is not None:
            z = _global(zona_uso_local(m, criterios), amb)
            if z is not None:
                ax.fill(*z.exterior.xy, facecolor="#fff3b0", edgecolor="goldenrod",
                        linestyle=":", alpha=0.6, zorder=6)
        p = _global(pegada_local(m), amb)
        if p is None:
            continue
        suspenso = (m.elevacao.valor or 0) > 0
        estimado = m.largura.status is not Status.confirmado or m.profundidade.status is not Status.confirmado
        ax.fill(*p.exterior.xy, facecolor="none" if suspenso else "#d9b38c", edgecolor="saddlebrown",
                hatch="//" if suspenso else None, linestyle="--" if estimado else "-",
                linewidth=1.2, alpha=0.9, zorder=7)
        c = p.centroid
        ax.text(c.x, c.y, f"{m.nome}\n{m.largura.valor:.0f}×{m.profundidade.valor:.0f}",
                ha="center", va="center", fontsize=6.5, zorder=8,
                bbox=dict(boxstyle="round,pad=0.1", fc="white", ec="none", alpha=0.7))


def _para_dentro(pol, a, b, deslocamento: float) -> tuple[float, float]:
    """Ponto médio do segmento a-b deslocado para dentro do polígono (só para rótulos)."""
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    comp = math.dist(a, b) or 1.0
    nx, ny = -(b[1] - a[1]) / comp, (b[0] - a[0]) / comp
    if not pol.contains(Point(mx + nx * 10, my + ny * 10)):
        nx, ny = -nx, -ny
    return mx + nx * deslocamento, my + ny * deslocamento


def _arco_porta(ax, amb, ab, a, b) -> None:
    """Arco de 90° indicando o giro da folha."""
    pol, _ = poligono_global(amb)
    largura = math.dist(a, b)
    if largura == 0:
        return
    eixo, ponta = (a, b) if ab.sentido.dobradica == "inicio" else (b, a)
    ang_folha_fechada = math.degrees(math.atan2(ponta[1] - eixo[1], ponta[0] - eixo[0]))
    # normal que aponta para dentro do ambiente
    nx, ny = -(b[1] - a[1]) / largura, (b[0] - a[0]) / largura
    meio = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    if not pol.contains(Point(meio[0] + nx * 10, meio[1] + ny * 10)):
        nx, ny = -nx, -ny
    if ab.sentido.abre_para == "fora":
        nx, ny = -nx, -ny
    ang_normal = math.degrees(math.atan2(ny, nx))
    # arco entre a folha fechada e a folha aberta (90°), pelo lado da normal
    diff = (ang_normal - ang_folha_fechada) % 360
    t1, t2 = (ang_folha_fechada, ang_normal) if diff <= 180 else (ang_normal, ang_folha_fechada)
    ax.add_patch(Arc(eixo, 2 * largura, 2 * largura, theta1=t1, theta2=t2,
                     color="royalblue", linewidth=0.8, linestyle=":", zorder=3))
    fim = (eixo[0] + nx * largura, eixo[1] + ny * largura)
    ax.plot([eixo[0], fim[0]], [eixo[1], fim[1]], color="royalblue", linewidth=0.8, zorder=3)
