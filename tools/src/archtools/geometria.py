"""Cálculos geométricos com propagação de status.

Todo valor calculado é um `Derivado`: carrega o valor e o status mais fraco
das entradas. Se alguma entrada é desconhecida, o valor é None.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from shapely.affinity import translate
from shapely.geometry import Polygon

from .schema import Abertura, Ambiente, Geometria, Medida, Status, status_mais_fraco

TOL_MM = 5.0  # tolerância para comparações geométricas


@dataclass(frozen=True)
class Derivado:
    valor: float | None
    status: Status

    @property
    def conhecido(self) -> bool:
        return self.valor is not None


def de_medida(m: Medida | None) -> Derivado:
    if m is None:
        return Derivado(None, Status.desconhecido)
    return Derivado(m.valor, m.status)


def formatar(d: Derivado, unidade: str = "", casas: int = 0) -> str:
    """Texto com marcação de status: '12.5 m²' / '~12.5 m² (estimado)' / '? (desconhecido)'."""
    if d.valor is None:
        return "? (desconhecido)"
    num = f"{d.valor:.{casas}f}{(' ' + unidade) if unidade else ''}"
    return num if d.status is Status.confirmado else f"~{num} (estimado)"


def poligono(amb: Ambiente) -> tuple[Polygon | None, Status]:
    """Polígono nas coordenadas próprias do ambiente (relativas à `posicao`, se houver).

    O status reflete só as dimensões internas — não o encaixe na planta geral.
    """
    if len(amb.vertices) < 3:
        return None, Status.desconhecido
    st = status_mais_fraco(*(v.status for v in amb.vertices))
    if st is Status.desconhecido:
        return None, st
    return Polygon([(v.x, v.y) for v in amb.vertices]), st


def deslocamento(amb: Ambiente) -> tuple[tuple[float, float] | None, Status]:
    """Translação local → global. Sem `posicao`, os vértices já são globais."""
    if amb.posicao is None:
        return (0.0, 0.0), Status.confirmado
    if amb.posicao.status is Status.desconhecido:
        return None, Status.desconhecido
    return (amb.posicao.x, amb.posicao.y), amb.posicao.status


def poligono_global(amb: Ambiente) -> tuple[Polygon | None, Status]:
    """Polígono na planta geral; status = mais fraco entre dimensões e posição."""
    pol, st = poligono(amb)
    d, st_pos = deslocamento(amb)
    if pol is None or d is None:
        return None, Status.desconhecido
    return translate(pol, d[0], d[1]), status_mais_fraco(st, st_pos)


def area_m2(amb: Ambiente) -> Derivado:
    pol, st = poligono(amb)
    return Derivado(None if pol is None else pol.area / 1e6, st)


def perimetro_m(amb: Ambiente) -> Derivado:
    pol, st = poligono(amb)
    return Derivado(None if pol is None else pol.length / 1e3, st)


@dataclass(frozen=True)
class Parede:
    indice: int
    inicio: tuple[float, float] | None  # coordenadas GLOBAIS (None se posição desconhecida)
    fim: tuple[float, float] | None
    comprimento: Derivado  # intrínseco: não depende da posição do ambiente
    status_global: Status  # status do traçado na planta geral


def paredes(amb: Ambiente) -> list[Parede]:
    n = len(amb.vertices)
    if n < 3:
        return []
    d, st_pos = deslocamento(amb)
    resultado = []
    for i in range(n):
        a, b = amb.vertices[i], amb.vertices[(i + 1) % n]
        st = status_mais_fraco(a.status, b.status)
        if st is Status.desconhecido:
            resultado.append(Parede(i, None, None, Derivado(None, st), Status.desconhecido))
            continue
        comp = Derivado(math.hypot(b.x - a.x, b.y - a.y), st)
        if d is None:
            resultado.append(Parede(i, None, None, comp, Status.desconhecido))
        else:
            resultado.append(Parede(i, (a.x + d[0], a.y + d[1]), (b.x + d[0], b.y + d[1]),
                                    comp, status_mais_fraco(st, st_pos)))
    return resultado


def pe_direito(amb: Ambiente, geo: Geometria) -> Derivado:
    return de_medida(amb.pe_direito or geo.pe_direito_padrao)


def soma(*ds: Derivado) -> Derivado:
    st = status_mais_fraco(*(d.status for d in ds))
    if any(d.valor is None for d in ds):
        return Derivado(None, Status.desconhecido)
    return Derivado(sum(d.valor for d in ds), st)


def segmento_abertura(
    ab: Abertura, parede: Parede
) -> tuple[tuple[float, float], tuple[float, float], Status] | None:
    """Coordenadas (início, fim) da abertura sobre a parede, ou None se indeterminável."""
    dist, larg = de_medida(ab.distancia), de_medida(ab.largura)
    if parede.inicio is None or not dist.conhecido or not larg.conhecido:
        return None
    comp = parede.comprimento.valor
    if not comp:
        return None
    (x0, y0), (x1, y1) = parede.inicio, parede.fim
    ux, uy = (x1 - x0) / comp, (y1 - y0) / comp
    a = (x0 + ux * dist.valor, y0 + uy * dist.valor)
    b = (x0 + ux * (dist.valor + larg.valor), y0 + uy * (dist.valor + larg.valor))
    st = status_mais_fraco(parede.status_global, dist.status, larg.status)
    return a, b, st
