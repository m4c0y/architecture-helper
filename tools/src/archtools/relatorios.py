"""Relatórios em texto: quadro de áreas e pendências de medição."""

from __future__ import annotations

from .geometria import Derivado, area_m2, formatar, paredes, pe_direito, perimetro_m
from .schema import Geometria, Medida, Ponto, Status, status_mais_fraco


TITULO_TIPO = {
    "interno": "ambientes internos",
    "varanda": "varandas",
    "tecnico": "áreas técnicas",
    "externo": "áreas descobertas",
}


def _total(areas: list[Derivado]) -> Derivado:
    if not areas or not all(a.conhecido for a in areas):
        return Derivado(None, Status.desconhecido)
    return Derivado(sum(a.valor for a in areas), status_mais_fraco(*(a.status for a in areas)))


def quadro_areas(geo: Geometria) -> str:
    linhas = ["| Ambiente | Tipo | Área | Perímetro | Pé-direito | Paredes/lados (mm) |",
              "|---|---|---|---|---|---|"]
    por_tipo: dict[str, list[Derivado]] = {}
    for amb in geo.ambientes:
        a = area_m2(amb)
        por_tipo.setdefault(amb.tipo, []).append(a)
        comps = ", ".join(
            f"{p.indice}: {formatar(p.comprimento)}" for p in paredes(amb)
        ) or "—"
        pd = "n/a" if amb.tipo == "externo" else formatar(pe_direito(amb, geo), "mm")
        linhas.append(
            f"| {amb.nome} (`{amb.id}`) | {amb.tipo} | {formatar(a, 'm²', 2)} "
            f"| {formatar(perimetro_m(amb), 'm', 2)} | {pd} | {comps} |"
        )
    for tipo, titulo in TITULO_TIPO.items():
        if tipo in por_tipo:
            linhas.append(f"| **Total {titulo}** | | **{formatar(_total(por_tipo[tipo]), 'm²', 2)}** | | | |")
    linhas += ["", "Legenda: valor sem marca = confirmado; `~` = estimado; `?` = desconhecido.",
               "Áreas = polígonos internos (não incluem paredes)."]
    return "\n".join(linhas)


def _itens(geo: Geometria):
    """Percorre todas as medidas/pontos: (onde, campo, objeto)."""
    yield "projeto", "pe_direito_padrao", geo.pe_direito_padrao
    for amb in geo.ambientes:
        if amb.posicao is not None:
            yield f"ambiente `{amb.id}`", "posição na planta geral", amb.posicao
        if not amb.vertices:
            yield f"ambiente `{amb.id}`", "vertices", None
        for i, v in enumerate(amb.vertices):
            yield f"ambiente `{amb.id}`", f"vértice {i}", v
        if amb.pe_direito:
            yield f"ambiente `{amb.id}`", "pe_direito", amb.pe_direito
    for ab in geo.aberturas:
        for campo in ("distancia", "largura", "altura", "peitoril"):
            m = getattr(ab, campo)
            if m is not None:
                yield f"abertura `{ab.id}` ({ab.tipo}, {ab.ambiente})", campo, m
    for pf in geo.pontos_fixos:
        yield f"ponto fixo `{pf.id}` ({pf.tipo}, {pf.ambiente})", "posição", pf.posicao
        if pf.altura is not None:
            yield f"ponto fixo `{pf.id}`", "altura", pf.altura
    for c in geo.cercamentos:
        yield f"cercamento `{c.id}` ({c.tipo})", "altura", c.altura
        for i, p in enumerate(c.pontos):
            yield f"cercamento `{c.id}`", f"ponto {i}", p


def _valor(obj: Medida | Ponto) -> str:
    if isinstance(obj, Ponto):
        return f"({obj.x:.0f}, {obj.y:.0f})"
    return f"{obj.valor:.0f} mm"


def pendencias(geo: Geometria) -> str:
    desconhecidos, estimados = [], []
    for onde, campo, obj in _itens(geo):
        if obj is None:
            desconhecidos.append(f"- [ ] {onde} — {campo}: nenhum vértice cadastrado")
        elif obj.status is Status.desconhecido:
            desconhecidos.append(f"- [ ] {onde} — {campo}")
        elif obj.status is Status.estimado:
            estimados.append(f"- [ ] {onde} — {campo}: {_valor(obj)} (origem: {obj.fonte})")
    partes = [
        f"# Pendências de medição — {geo.projeto}",
        "",
        "> Arquivo GERADO por `archtools pendencias`. Não editar à mão.",
        "",
        f"## A medir (desconhecido) — {len(desconhecidos)}",
        "",
        *(desconhecidos or ["Nenhuma."]),
        "",
        f"## A confirmar (estimado) — {len(estimados)}",
        "",
        *(estimados or ["Nenhuma."]),
        "",
    ]
    return "\n".join(partes)
