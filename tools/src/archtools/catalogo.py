"""Catálogo de produtos: medidas e aparência de itens reais, num lugar só.

Procura em duas pastas (a do projeto vence em caso de id repetido):
- `projetos/<p>/catalogo/produtos/<id>.yaml` — produtos escolhidos pelo usuário (privado);
- `catalogo/produtos/<id>.yaml` (raiz do repositório) — itens genéricos reutilizáveis.

    id: sofa-chaise-194
    nome: "Sofá com chaise 194"
    categoria: sofa
    fonte: "anúncio da loja (medidas), foto do usuário (2026-11-17)"
    link: null
    largura:      {valor: 1940, status: estimado, fonte: "anúncio: 194 cm"}
    profundidade: {valor: 940,  status: estimado, fonte: "anúncio: corpo 94 cm"}
    altura:       {valor: 900,  status: estimado, fonte: "anúncio: 90 cm"}
    modelo: null                 # modelo 3D paramétrico (archtools.modelos), se houver
    cor_real: null               # hex = cor conhecida (render não recolore); null = a definir no conceito
                                 # {material: hex} = cor real por peça do modelo (ex.: estofado, estrutura)
    textura: tecido              # opcional: preset de textura do produto (materiais.TEXTURAS)
    altura_assento: {...}        # forma de estofado (opcional, como no layout)

No `layout.yaml`, um item com `produto: <id>` herda do catálogo tudo o que não informar
(categoria, medidas, modelo, forma, cor_real). O que o layout informar prevalece.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .estilo import HEX
from .schema import Medida

HERDAVEIS = ("categoria", "largura", "profundidade", "altura", "modelo", "altura_assento", "prof_encosto",
             "braco_largura", "braco_altura", "bracos", "blocos_assento", "almofadas_encosto", "armacao", "cor_real",
             "textura")


class Produto(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    nome: str
    categoria: str
    fonte: str
    link: str | None = None
    largura: Medida
    profundidade: Medida
    altura: Medida
    modelo: str | None = None
    cor_real: str | dict[str, str] | None = None
    textura: str | None = None
    altura_assento: Medida | None = None
    prof_encosto: Medida | None = None
    braco_largura: Medida | None = None
    braco_altura: Medida | None = None
    bracos: list[str] = Field(default_factory=list)
    blocos_assento: int | None = Field(default=None, ge=1)
    almofadas_encosto: int | None = Field(default=None, ge=1)
    armacao: Literal["tubular"] | None = None
    fotos: list[str] = Field(default_factory=list)  # fotos do produto real (relativas ao projeto): referência p/ IA
    tags: list[str] = Field(default_factory=list)
    notas: str | None = None

    @field_validator("cor_real")
    @classmethod
    def _hex(cls, v):
        return valida_cor_real(v)

    @field_validator("textura")
    @classmethod
    def _tex(cls, v):
        from .materiais import TEXTURAS
        if v is not None and v not in TEXTURAS:
            raise ValueError(f"textura '{v}' não existe ({', '.join(TEXTURAS)})")
        return v


def valida_cor_real(v):
    """Hex único ou {material da peça: hex}; devolve em maiúsculas."""
    if v is None:
        return v
    cores = v if isinstance(v, dict) else {"": v}
    for h in cores.values():
        if not HEX.match(h):
            raise ValueError(f"cor_real '{h}' não é hex #RRGGBB")
    return {k: h.upper() for k, h in v.items()} if isinstance(v, dict) else v.upper()


def pastas_catalogo(pasta_projeto: Path | None, raiz: Path = Path(".")) -> list[Path]:
    """Ordem de busca: raiz primeiro, projeto depois (o projeto sobrescreve)."""
    pastas = [Path(raiz) / "catalogo" / "produtos"]
    if pasta_projeto is not None:
        pastas.append(Path(pasta_projeto) / "catalogo" / "produtos")
    return pastas


def carregar_catalogo(pastas: list[Path]) -> dict[str, Produto]:
    cat: dict[str, Produto] = {}
    for pasta in pastas:
        for f in sorted(Path(pasta).glob("*.yaml")):
            p = Produto.model_validate(yaml.safe_load(f.read_text(encoding="utf-8")))
            if p.id != f.stem:
                raise ValueError(f"{f}: id '{p.id}' difere do nome do arquivo")
            cat[p.id] = p
    return cat


def herdar(item: dict, cat: dict[str, Produto]) -> dict:
    """Completa um item de layout (dict cru do YAML) com os dados do produto do catálogo."""
    pid = item.get("produto")
    if not pid or pid not in cat:
        return item
    dados = cat[pid].model_dump(mode="json", exclude_none=True)
    novo = dict(item)
    for campo in HERDAVEIS:
        if campo not in novo and campo in dados and dados[campo] not in ([], None):
            novo[campo] = dados[campo]
    return novo
