"""Conceito de um ambiente (`conceito.yaml`): como o ambiente fica. Par do `layout.yaml` (o que vai onde).

Aprovado em `projetos/<p>/ambientes/<id>/conceito.yaml`; propostas em
`projetos/<p>/propostas/<x>/conceito.yaml` (ao lado do `layout.yaml` da proposta).

    ambiente: dorm2                      # opcional em ambientes/<id>/ (vale o nome da pasta)
    fonte: "proposta escritorio (Estúdio Ma), 2026-11-18"
    estilo: {principal: japandi, acentos: []}   # opcional: senão, `padrao` de projetos/<p>/estilo.yaml
    referencias:                         # referências aprovadas para o ambiente (não são copiadas)
      - {id: quarto-vaso-01, biblioteca: japandi, papel: ancora}   # arquitetos/japandi/referencias/
      - {id: minha-foto-01, papel: evitar}                         # projetos/<p>/referencias/
    superficies:
      paredes: {padrao: branco_arroz, "1": verde_garrafa}   # índice da parede -> id de cor
      teto: branco_arroz
      piso: null                         # null = existente/desconhecido; "#RRGGBB" = cor real
      piso_textura: {tipo: reguas, largura: 200, comprimento: 1200}   # opcional (materiais.TEXTURAS)
    itens:                               # ids do layout.yaml do mesmo ambiente
      sofa: {cor: pedra}
      vaso: {pecas: {vaso: argila}}
    luzes:
      lum-papel: {luminaria: pendente_papel, camada: geral, intensidade_w: 50}

Cores e luminárias precisam existir no estilo RESOLVIDO (`archtools estilo`). Itens com
`cor_real` no catálogo não devem ser recoloridos (aviso).
Depende do layout (ids dos itens); o layout não depende do conceito.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .acabamentos import AcabMovel, Acabamentos, Luz, TexturaPiso
from .estilo import Escolha


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RefAprovada(_Base):
    id: str
    biblioteca: str | None = None  # id de arquiteto; None = referências do projeto
    papel: Literal["ancora", "material", "evitar", "detalhe"] = "ancora"


class Superficies(_Base):
    paredes: dict[str, str] = Field(default_factory=dict)
    teto: str | None = None
    piso: str | None = None
    piso_textura: TexturaPiso | None = None


class Conceito(_Base):
    ambiente: str | None = None
    fonte: str
    estilo: Escolha | None = None
    referencias: list[RefAprovada] = Field(default_factory=list)
    superficies: Superficies = Field(default_factory=Superficies)
    itens: dict[str, AcabMovel] = Field(default_factory=dict)
    luzes: dict[str, Luz] = Field(default_factory=dict)

    def acabamentos(self) -> Acabamentos:
        """Adaptador para o validador/exportador de acabamentos existente."""
        return Acabamentos(ambiente=self.ambiente, fonte=self.fonte, paredes=self.superficies.paredes,
                           teto=self.superficies.teto, piso=self.superficies.piso,
                           piso_textura=self.superficies.piso_textura, moveis=self.itens,
                           luzes=self.luzes)


def carregar_conceito(arquivo: Path, ambiente_padrao: str | None = None) -> Conceito:
    dados = yaml.safe_load(Path(arquivo).read_text(encoding="utf-8")) or {}
    c = Conceito.model_validate(dados)
    if c.ambiente is None:
        if ambiente_padrao is None:
            raise ValueError(f"{arquivo}: informe `ambiente` (fora de ambientes/<id>/ não há padrão)")
        c.ambiente = ambiente_padrao
    elif ambiente_padrao is not None and c.ambiente != ambiente_padrao:
        raise ValueError(f"{arquivo}: ambiente '{c.ambiente}' difere da pasta '{ambiente_padrao}'")
    return c


def escolha_do_conceito(c: Conceito, pasta_projeto: Path) -> Escolha | None:
    if c.estilo is not None:
        return c.estilo
    from .estilo import carregar_selecao
    f = Path(pasta_projeto) / "estilo.yaml"
    return carregar_selecao(f).padrao if f.exists() else None


def validar_referencias_aprovadas(c: Conceito, pasta_projeto: Path, pasta_arqs: Path) -> list[str]:
    erros = []
    for r in c.referencias:
        base = (Path(pasta_arqs) / r.biblioteca / "referencias") if r.biblioteca else Path(pasta_projeto) / "referencias"
        if not (base / f"{r.id}.yaml").exists():
            erros.append(f"referencias: '{r.id}' não existe em {base}")
    return erros


def avisos_cor_real(c: Conceito, cena: dict) -> list[str]:
    reais = {m["id"] for m in cena["moveis"] if m.get("cor_real")}
    return [f"itens.{mid}: produto com cor real conhecida ({mid}) — recolorir só com decisão explícita"
            for mid in c.itens if mid in reais]
