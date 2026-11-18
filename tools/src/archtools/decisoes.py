"""Decisões (`projetos/<p>/decisoes/NNNN-*.md`) com cabeçalho YAML opcional de aprovação.

    ---
    numero: "0011"
    estado: aceita                 # aceita | substituida | revogada
    substituida_por: null          # "0014" quando estado = substituida
    aprova:                        # arquivos aprovados por esta decisão (relativos ao projeto)
      - {arquivo: layout.yaml, sha256: "3fa1c2…"}
    base:                          # o que estava valendo quando aprovou (opcional)
      - {arquivo: geometria.yaml, sha256: "9c0d…"}
    ---
    # 0011 — Título
    ...

Os hashes vêm de `archtools aprovacao` (nunca escritos à mão). Decisões antigas, sem
cabeçalho, continuam válidas: o estado é lido da linha "**Estado:**" do texto.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .manifesto import hash_arquivo


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Item(_Base):
    arquivo: str
    sha256: str


class Cabecalho(_Base):
    numero: str
    estado: Literal["aceita", "substituida", "revogada"]
    substituida_por: str | None = None
    aprova: list[Item] = Field(default_factory=list)
    base: list[Item] = Field(default_factory=list)


@dataclass
class Decisao:
    arquivo: Path
    numero: str
    titulo: str
    estado: str  # aceita | substituida | revogada | desconhecido
    cabecalho: Cabecalho | None


_FRONT = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
_ESTADO = re.compile(r"\*\*Estado:\*\*\s*(.+)", re.I)


def _estado_do_texto(texto: str) -> str:
    m = _ESTADO.search(texto)
    if not m:
        return "desconhecido"
    v = m.group(1).lower().strip()
    if v.startswith(("substituída", "substituida")):
        return "substituida"
    if v.startswith("revog"):
        return "revogada"
    return "aceita" if v.startswith("aceit") else "desconhecido"


def carregar(pasta_projeto: Path) -> list[Decisao]:
    res = []
    for f in sorted((Path(pasta_projeto) / "decisoes").glob("[0-9][0-9][0-9][0-9]-*.md")):
        texto = f.read_text(encoding="utf-8")
        cab = None
        m = _FRONT.match(texto)
        if m:
            cab = Cabecalho.model_validate(yaml.safe_load(m.group(1)))
            texto = texto[m.end():]
        tit = next((ln[2:].strip() for ln in texto.splitlines() if ln.startswith("# ")), f.stem)
        res.append(Decisao(f, f.name[:4], tit, cab.estado if cab else _estado_do_texto(texto), cab))
    return res


def bloco_aprovacao(pasta_projeto: Path, numero: str, aprova: list[str], base: list[str] = ()) -> str:
    """Cabeçalho pronto para colar no topo de uma decisão nova (hashes calculados agora)."""
    pasta = Path(pasta_projeto)

    def itens(arqs):
        out = []
        for a in arqs:
            p = pasta / a
            if not p.exists():
                raise FileNotFoundError(f"{p} não existe")
            out.append({"arquivo": Path(a).as_posix(), "sha256": hash_arquivo(p)})
        return out

    dados = {"numero": numero, "estado": "aceita", "aprova": itens(aprova)}
    if base:
        dados["base"] = itens(base)
    return "---\n" + yaml.safe_dump(dados, sort_keys=False, allow_unicode=True) + "---\n"


@dataclass
class Aprovado:
    arquivo: str
    decisao: str
    estado: str  # "ok" | "alterado" | "ausente"


def aprovacoes(pasta_projeto: Path, decs: list[Decisao]) -> list[Aprovado]:
    """Última aprovação vigente de cada arquivo e se o conteúdo ainda é o aprovado."""
    ultimo: dict[str, tuple[str, str]] = {}
    for d in decs:
        if d.cabecalho is None or d.estado != "aceita":
            continue
        for it in d.cabecalho.aprova:
            ultimo[it.arquivo] = (d.numero, it.sha256)
    res = []
    for arq, (num, h) in sorted(ultimo.items()):
        p = Path(pasta_projeto) / arq
        estado = "ausente" if not p.exists() else ("ok" if hash_arquivo(p) == h else "alterado")
        res.append(Aprovado(arq, num, estado))
    return res
