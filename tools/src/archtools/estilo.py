"""Arquitetos (personas de estilo) e seleção de estilo por projeto/ambiente.

- `arquitetos/<id>/arquiteto.yaml` (raiz do repositório, reutilizável entre projetos): paleta,
  materiais, iluminação, luminárias e regras de UM estilo. Persona fictícia.
- `projetos/<p>/estilo.yaml` (ou `propostas/<x>/estilo.yaml`): quem decora o quê.
    padrao:   {principal: <id>, acentos: [<id>, ...]}   # casa toda
    ambientes:
      <ambiente>: {principal: <id>, acentos: [...]}      # sobrepõe o padrão

Combinação (determinística):
- principal define a base: paleta base/apoio, materiais, temperatura de cor, regras.
- acentos contribuem só com cores de destaque, materiais e luminárias, marcados com a origem.
- item de acento cujas tags estão em `regras.evitar_tags` do principal é EXCLUÍDO e relatado
  como conflito (o principal manda).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Cor(_Base):
    id: str
    nome: str
    hex: str
    papel: Literal["base", "apoio", "destaque"]
    uso: str
    tags: list[str] = Field(default_factory=list)

    @field_validator("hex")
    @classmethod
    def _hex(cls, v: str) -> str:
        if not HEX.match(v):
            raise ValueError(f"cor '{v}' não é hex #RRGGBB")
        return v.upper()


class Material(_Base):
    id: str
    nome: str
    onde: list[Literal["piso", "parede", "teto", "marcenaria", "moveis", "estofados", "tecidos",
                       "luminarias", "bancada", "decoracao"]]
    uso: str
    tags: list[str] = Field(default_factory=list)


class Luminaria(_Base):
    id: str
    tipo: Literal["pendente", "trilho", "spot", "arandela", "coluna", "mesa", "fita_led",
                  "plafon", "embutido", "luminaria_piso"]
    descricao: str
    temperatura_k: int
    tags: list[str] = Field(default_factory=list)


class Iluminacao(_Base):
    temperatura_k: dict[Literal["geral", "tarefa", "destaque"], int]
    estrategia: str


class Regras(_Base):
    fazer: list[str]
    evitar: list[str]
    evitar_tags: list[str] = Field(default_factory=list)


class Arquiteto(_Base):
    id: str
    nome: str
    estilo: str
    estado: Literal["rascunho", "aprovado"]
    fonte: str
    resumo: str
    paleta: list[Cor]
    materiais: list[Material]
    iluminacao: Iluminacao
    luminarias: list[Luminaria]
    regras: Regras

    @model_validator(mode="after")
    def _ids_unicos(self) -> "Arquiteto":
        for nome, itens in (("paleta", self.paleta), ("materiais", self.materiais),
                            ("luminarias", self.luminarias)):
            ids = [i.id for i in itens]
            if len(ids) != len(set(ids)):
                raise ValueError(f"ids repetidos em {nome}")
        if not any(c.papel == "base" for c in self.paleta):
            raise ValueError("a paleta precisa de ao menos uma cor 'base'")
        return self


class Escolha(_Base):
    principal: str
    acentos: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _sem_repeticao(self) -> "Escolha":
        if self.principal in self.acentos:
            raise ValueError("o principal não pode ser também acento")
        if len(self.acentos) != len(set(self.acentos)):
            raise ValueError("acentos repetidos")
        return self


class Selecao(_Base):
    padrao: Escolha | None = None
    ambientes: dict[str, Escolha] = Field(default_factory=dict)


def carregar_arquitetos(pasta: Path) -> dict[str, Arquiteto]:
    arqs: dict[str, Arquiteto] = {}
    for f in sorted(Path(pasta).glob("*/arquiteto.yaml")):
        a = Arquiteto.model_validate(yaml.safe_load(f.read_text(encoding="utf-8")))
        if a.id != f.parent.name:
            raise ValueError(f"{f}: id '{a.id}' difere da pasta '{f.parent.name}'")
        arqs[a.id] = a
    return arqs


def carregar_selecao(arquivo: Path) -> Selecao:
    return Selecao.model_validate(yaml.safe_load(Path(arquivo).read_text(encoding="utf-8")) or {})


class Item(_Base):
    origem: str  # id do arquiteto
    papel: Literal["principal", "acento"]
    dado: Cor | Material | Luminaria


class Conflito(_Base):
    acento: str
    categoria: str
    item: str
    tags: list[str]

    def __str__(self) -> str:
        return (f"conflito: {self.categoria} '{self.item}' de {self.acento} excluído — tags {', '.join(self.tags)} "
                f"estão em evitar_tags do principal")


class EstiloResolvido(_Base):
    alvo: str  # 'padrao' ou id do ambiente
    escolha: Escolha
    paleta: list[Item]
    materiais: list[Item]
    luminarias: list[Item]
    iluminacao: Iluminacao
    regras: Regras
    conflitos: list[Conflito]


def escolha_para(sel: Selecao, ambiente: str | None) -> tuple[str, Escolha] | None:
    if ambiente and ambiente in sel.ambientes:
        return ambiente, sel.ambientes[ambiente]
    if sel.padrao:
        return (ambiente or "padrao"), sel.padrao
    return None


def resolver(arqs: dict[str, Arquiteto], alvo: str, esc: Escolha) -> EstiloResolvido:
    faltam = [i for i in [esc.principal, *esc.acentos] if i not in arqs]
    if faltam:
        raise KeyError(f"arquiteto(s) inexistente(s): {', '.join(faltam)} (disponíveis: {', '.join(arqs)})")
    p = arqs[esc.principal]
    proibidas = set(p.regras.evitar_tags)
    paleta = [Item(origem=p.id, papel="principal", dado=c) for c in p.paleta]
    materiais = [Item(origem=p.id, papel="principal", dado=m) for m in p.materiais]
    luminarias = [Item(origem=p.id, papel="principal", dado=lu) for lu in p.luminarias]
    conflitos: list[Conflito] = []

    def contribuir(destino: list[Item], aid: str, categoria: str, itens) -> None:
        for d in itens:
            ruins = sorted(proibidas & set(d.tags))
            if ruins:
                conflitos.append(Conflito(acento=aid, categoria=categoria, item=d.id, tags=ruins))
            else:
                destino.append(Item(origem=aid, papel="acento", dado=d))

    for aid in esc.acentos:
        a = arqs[aid]
        contribuir(paleta, aid, "cor", [c for c in a.paleta if c.papel == "destaque"])
        contribuir(materiais, aid, "material", a.materiais)
        contribuir(luminarias, aid, "luminária", a.luminarias)

    return EstiloResolvido(alvo=alvo, escolha=esc, paleta=paleta, materiais=materiais,
                           luminarias=luminarias, iluminacao=p.iluminacao, regras=p.regras,
                           conflitos=conflitos)


def validar_selecao(sel: Selecao, arqs: dict[str, Arquiteto], ambientes: set[str]) -> list[str]:
    """Erros da seleção: arquitetos inexistentes, ambientes que não existem na geometria."""
    erros = []
    escolhas = ([("padrao", sel.padrao)] if sel.padrao else []) + list(sel.ambientes.items())
    for alvo, esc in escolhas:
        for aid in [esc.principal, *esc.acentos]:
            if aid not in arqs:
                erros.append(f"{alvo}: arquiteto '{aid}' não existe")
    for amb in sel.ambientes:
        if amb not in ambientes:
            erros.append(f"ambiente '{amb}' não existe em geometria.yaml")
    return erros


def texto_resolvido(r: EstiloResolvido, arqs: dict[str, Arquiteto]) -> str:
    def rot(i: Item) -> str:
        return "" if i.papel == "principal" else f"  [acento: {i.origem}]"

    nomes = [arqs[r.escolha.principal].nome] + [f"{arqs[a].nome} (acento)" for a in r.escolha.acentos]
    linhas = [f"## {r.alvo}: {' + '.join(nomes)}"]
    rasc = [a for a in [r.escolha.principal, *r.escolha.acentos] if arqs[a].estado == "rascunho"]
    if rasc:
        linhas.append(f"(persona em rascunho: {', '.join(rasc)})")
    linhas.append("Paleta:")
    for i in r.paleta:
        linhas.append(f"  {i.dado.hex}  {i.dado.papel:<8} {i.dado.nome} — {i.dado.uso}{rot(i)}")
    linhas.append("Materiais:")
    for i in r.materiais:
        linhas.append(f"  {i.dado.nome} ({', '.join(i.dado.onde)}) — {i.dado.uso}{rot(i)}")
    t = r.iluminacao.temperatura_k
    linhas.append("Iluminação: " + ", ".join(f"{k} {v} K" for k, v in t.items())
                  + f" — {r.iluminacao.estrategia.strip()}")
    linhas.append("Luminárias:")
    for i in r.luminarias:
        linhas.append(f"  {i.dado.tipo}: {i.dado.descricao} ({i.dado.temperatura_k} K){rot(i)}")
    linhas.append("Fazer:  " + "; ".join(r.regras.fazer))
    linhas.append("Evitar: " + "; ".join(r.regras.evitar))
    linhas += [str(c) for c in r.conflitos]
    return "\n".join(linhas)
