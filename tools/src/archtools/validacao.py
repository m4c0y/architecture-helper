"""Validações determinísticas de `geometria.yaml`.

Níveis:
- erro             inconsistência nos dados (falha mesmo que baseada em estimativas)
- aviso            provável problema ou informação faltando para fases seguintes
- nao_verificavel  a regra não pôde ser checada por falta de dados (desconhecidos)
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Literal

from shapely.geometry import Point

from .geometria import (
    TOL_MM, Derivado, de_medida, formatar, paredes, pe_direito, poligono, poligono_global,
    segmento_abertura, soma,
)
from .schema import Geometria, Status, status_mais_fraco

Nivel = Literal["erro", "aviso", "nao_verificavel"]


@dataclass(frozen=True)
class Achado:
    nivel: Nivel
    onde: str
    mensagem: str
    base: Status | None = None  # status dos dados que sustentam o achado

    def __str__(self) -> str:
        sufixo = " [baseado em dados estimados]" if self.base is Status.estimado else ""
        return f"[{self.nivel}] {self.onde}: {self.mensagem}{sufixo}"


def validar(geo: Geometria) -> list[Achado]:
    achados: list[Achado] = []
    add = achados.append

    # --- identificadores únicos e referências
    for nome, itens in (("ambiente", geo.ambientes), ("abertura", geo.aberturas),
                        ("ponto_fixo", geo.pontos_fixos)):
        for id_, n in Counter(i.id for i in itens).items():
            if n > 1:
                add(Achado("erro", f"{nome} '{id_}'", f"id repetido {n} vezes"))

    ambientes = {a.id: a for a in geo.ambientes}
    if not ambientes:
        add(Achado("nao_verificavel", "projeto", "nenhum ambiente cadastrado ainda"))

    # --- ambientes: polígono
    poligonos = {}
    for amb in geo.ambientes:
        onde = f"ambiente '{amb.id}'"
        if len(amb.vertices) < 3:
            add(Achado("nao_verificavel", onde, "menos de 3 vértices; área e paredes indeterminadas"))
            continue
        pol, st = poligono(amb)
        if pol is None:
            add(Achado("nao_verificavel", onde, "há vértices desconhecidos; área e paredes indeterminadas"))
            continue
        if not pol.is_valid:
            add(Achado("erro", onde, "polígono inválido (lados se cruzam ou vértices fora de ordem)", st))
            continue
        if pol.area <= 0:
            add(Achado("erro", onde, "área nula", st))
            continue
        poligonos[amb.id] = (pol, st)

    # --- sobreposição entre ambientes (na planta geral)
    globais = {}
    for amb in geo.ambientes:
        if amb.id in poligonos:
            pg, sg = poligono_global(amb)
            if pg is None:
                add(Achado("nao_verificavel", f"ambiente '{amb.id}'",
                           "posição na planta geral desconhecida; sobreposição não verificada"))
            else:
                globais[amb.id] = (pg, sg)
    ids = list(globais)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            (pa, sa), (pb, sb) = globais[a], globais[b]
            inter = pa.buffer(-TOL_MM).intersection(pb.buffer(-TOL_MM))
            if inter.area > 0:
                add(Achado("erro", f"ambientes '{a}' e '{b}'",
                           f"sobrepõem-se em {inter.area / 1e6:.3f} m²", status_mais_fraco(sa, sb)))

    # --- aberturas
    por_parede: dict[tuple[str, int], list] = {}
    for ab in geo.aberturas:
        onde = f"abertura '{ab.id}'"
        amb = ambientes.get(ab.ambiente)
        if amb is None:
            add(Achado("erro", onde, f"ambiente '{ab.ambiente}' não existe"))
            continue
        ps = paredes(amb)
        if ps and ab.parede >= len(ps):
            add(Achado("erro", onde, f"parede {ab.parede} não existe em '{amb.id}' (0 a {len(ps) - 1})"))
            continue
        if not ps:
            add(Achado("nao_verificavel", onde, "ambiente sem geometria definida"))
            continue
        parede = ps[ab.parede]

        # cabe na parede?
        fim = soma(de_medida(ab.distancia), de_medida(ab.largura))
        if fim.conhecido and parede.comprimento.conhecido:
            st = status_mais_fraco(fim.status, parede.comprimento.status)
            if fim.valor > parede.comprimento.valor + TOL_MM:
                add(Achado("erro", onde,
                           f"distância + largura = {fim.valor:.0f} mm ultrapassa a parede "
                           f"{ab.parede} ({parede.comprimento.valor:.0f} mm)", st))
        else:
            add(Achado("nao_verificavel", onde, "posição na parede indeterminada (dados desconhecidos)"))

        seg = segmento_abertura(ab, parede)
        if seg is not None:
            por_parede.setdefault((amb.id, ab.parede), []).append((ab, fim))

        # alturas
        pd = pe_direito(amb, geo)
        topo: Derivado
        if ab.tipo == "janela":
            if ab.peitoril is None:
                add(Achado("aviso", onde, "janela sem peitoril informado (use status desconhecido se não souber)"))
                topo = Derivado(None, Status.desconhecido)
            else:
                topo = soma(de_medida(ab.peitoril), de_medida(ab.altura))
        else:
            topo = de_medida(ab.altura)
        if topo.conhecido and pd.conhecido:
            if topo.valor > pd.valor + TOL_MM:
                add(Achado("erro", onde,
                           f"topo da abertura ({topo.valor:.0f} mm) acima do pé-direito ({pd.valor:.0f} mm)",
                           status_mais_fraco(topo.status, pd.status)))
        else:
            add(Achado("nao_verificavel", onde, "altura vs pé-direito não verificável (dados desconhecidos)"))

        if ab.tipo == "porta" and ab.sentido is None:
            add(Achado("aviso", onde, "porta de giro sem 'sentido' (necessário para circulação na fase 2)"))

    # --- aberturas sobrepostas na mesma parede
    for (amb_id, p), lista in por_parede.items():
        lista.sort(key=lambda t: t[0].distancia.valor)
        for (a1, f1), (a2, _) in zip(lista, lista[1:]):
            if a2.distancia.valor < f1.valor - TOL_MM:
                add(Achado("erro", f"aberturas '{a1.id}' e '{a2.id}'",
                           f"sobrepõem-se na parede {p} de '{amb_id}'",
                           status_mais_fraco(f1.status, a2.distancia.status)))

    # --- pontos fixos
    for pf in geo.pontos_fixos:
        onde = f"ponto fixo '{pf.id}'"
        if pf.ambiente not in ambientes:
            add(Achado("erro", onde, f"ambiente '{pf.ambiente}' não existe"))
            continue
        if pf.ambiente not in poligonos or pf.posicao.status is Status.desconhecido:
            add(Achado("nao_verificavel", onde, "posição ou ambiente indeterminado"))
            continue
        pol, st = poligonos[pf.ambiente]
        if not pol.buffer(TOL_MM).covers(Point(pf.posicao.x, pf.posicao.y)):
            add(Achado("erro", onde, f"fora do ambiente '{pf.ambiente}'",
                       status_mais_fraco(st, pf.posicao.status)))

    return achados


def resumo(achados: list[Achado]) -> str:
    c = Counter(a.nivel for a in achados)
    return (f"{c['erro']} erro(s), {c['aviso']} aviso(s), "
            f"{c['nao_verificavel']} item(ns) não verificável(is)")


__all__ = ["Achado", "validar", "resumo", "formatar"]
