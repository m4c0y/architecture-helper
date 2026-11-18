"""Esquema de `geometria.yaml`.

Toda grandeza física é uma `Medida` (valor + status + fonte). Coordenadas de
vértices e pontos são um `Ponto` com um único status para o par (x, y).
Unidade: milímetros.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Status(str, Enum):
    confirmado = "confirmado"
    estimado = "estimado"
    desconhecido = "desconhecido"

    @property
    def forca(self) -> int:
        return {"confirmado": 2, "estimado": 1, "desconhecido": 0}[self.value]


def status_mais_fraco(*statuses: Status) -> Status:
    """Status de um valor derivado: o mais fraco entre as entradas."""
    if not statuses:
        return Status.desconhecido
    return min(statuses, key=lambda s: s.forca)


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _checar_valor_status(valor, status: Status, fonte: str | None) -> None:
    if status is Status.desconhecido and valor is not None:
        raise ValueError("status 'desconhecido' exige valor null (não invente medidas)")
    if status is not Status.desconhecido and valor is None:
        raise ValueError(f"status '{status.value}' exige um valor; use 'desconhecido' se não houver")
    if status is not Status.desconhecido and not (fonte and fonte.strip()):
        raise ValueError(f"status '{status.value}' exige 'fonte' (de onde veio o valor)")


class Medida(_Base):
    valor: float | None = None
    status: Status
    fonte: str | None = None

    @model_validator(mode="after")
    def _coerente(self) -> "Medida":
        _checar_valor_status(self.valor, self.status, self.fonte)
        if self.valor is not None and self.valor < 0:
            raise ValueError("medida negativa")
        return self


class Ponto(_Base):
    x: float | None = None
    y: float | None = None
    status: Status
    fonte: str | None = None

    @model_validator(mode="after")
    def _coerente(self) -> "Ponto":
        if (self.x is None) != (self.y is None):
            raise ValueError("informe x e y juntos, ou nenhum dos dois (status desconhecido)")
        _checar_valor_status(self.x, self.status, self.fonte)
        return self


class Ambiente(_Base):
    """Se `posicao` existe, `vertices` (e os pontos fixos do ambiente) são relativos a ela.

    Isso separa as dimensões internas (ex.: cotas confirmadas) do encaixe do ambiente na
    planta geral (que pode ser só estimado, ex.: quando a espessura das paredes é desconhecida).
    Sem `posicao`, os vértices são coordenadas globais.
    """

    id: str
    nome: str
    # interno: fechado e coberto | varanda: coberta, aberta | externo: descoberto | tecnico: nicho/shaft
    tipo: Literal["interno", "varanda", "externo", "tecnico"] = "interno"
    posicao: Ponto | None = None
    vertices: list[Ponto] = Field(default_factory=list)
    pe_direito: Medida | None = None  # se ausente, usa pe_direito_padrao
    notas: str | None = None


class SentidoPorta(_Base):
    dobradica: Literal["inicio", "fim"]  # lado da parede (em relação ao vértice inicial)
    abre_para: Literal["dentro", "fora"]  # em relação ao ambiente da abertura


class Abertura(_Base):
    id: str
    tipo: Literal["porta", "janela", "vao", "porta_correr"]
    ambiente: str
    parede: int = Field(ge=0)
    distancia: Medida  # do vértice inicial da parede até a borda da abertura
    largura: Medida
    altura: Medida
    peitoril: Medida | None = None  # janelas
    sentido: SentidoPorta | None = None  # portas de giro
    notas: str | None = None


class PontoFixo(_Base):
    id: str
    tipo: Literal[
        "tomada", "interruptor", "ponto_luz", "ponto_agua", "esgoto", "ralo",
        "gas", "ar_condicionado", "ponto_tv", "pilar", "quadro_eletrico", "outro",
    ]
    ambiente: str
    posicao: Ponto  # no mesmo sistema de coordenadas dos vértices do ambiente
    altura: Medida | None = None
    notas: str | None = None


class Cercamento(_Base):
    """Limite linear do lote/área externa (tela, muro, grade). Pontos em coordenadas globais."""

    id: str
    tipo: str  # ex.: "tela fortinet"
    altura: Medida
    pontos: list[Ponto] = Field(min_length=2)
    notas: str | None = None


class Geometria(_Base):
    projeto: str
    unidade: Literal["mm"] = "mm"
    origem: str  # descrição física do ponto (0, 0)
    pe_direito_padrao: Medida
    ambientes: list[Ambiente] = Field(default_factory=list)
    aberturas: list[Abertura] = Field(default_factory=list)
    pontos_fixos: list[PontoFixo] = Field(default_factory=list)
    cercamentos: list[Cercamento] = Field(default_factory=list)


def carregar_geometria(projeto_dir: Path) -> Geometria:
    caminho = Path(projeto_dir) / "geometria.yaml"
    with caminho.open(encoding="utf-8") as f:
        dados = yaml.safe_load(f) or {}
    return Geometria.model_validate(dados)
