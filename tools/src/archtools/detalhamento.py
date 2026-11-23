"""Fase P4 (detalhamento): `ambientes/<id>/detalhamento.yaml` sobe a fidelidade de itens APROVADOS
sem mudar nenhuma decisão.

    itens:
      persiana: {modelo: persiana_romana, nota: "dobras horizontais"}

Só a representação 3D (`modelo` de archtools.modelos) pode mudar, e ela é sempre encaixada na
mesma caixa (largura × profundidade × altura do layout/catálogo): posição, medidas, cores e
validações continuam as do layout e do conceito aprovados. Não precisa de decisão nova.
"""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict


class ItemDetalhe(BaseModel):
    model_config = ConfigDict(extra="forbid")
    modelo: str
    nota: str | None = None


class Detalhamento(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fonte: str | None = None
    itens: dict[str, ItemDetalhe] = {}


def arquivos(pasta: Path) -> list[Path]:
    return sorted(Path(pasta).glob("ambientes/*/detalhamento.yaml"))


def aplicar_detalhamento(layout, pasta: Path) -> tuple[list[Path], list[str]]:
    """Troca o `modelo` dos itens listados nos detalhamento.yaml dos ambientes. Devolve os arquivos
    usados e os erros (item inexistente no ambiente, modelo desconhecido)."""
    from .modelos import MODELOS
    usados, erros = [], []
    por_id = {m.id: m for m in layout.moveis} if layout is not None else {}
    for f in arquivos(pasta):
        amb = f.parent.name
        det = Detalhamento.model_validate(yaml.safe_load(f.read_text(encoding="utf-8")) or {})
        usados.append(f)
        for mid, it in det.itens.items():
            m = por_id.get(mid)
            if m is None or m.ambiente != amb:
                erros.append(f"{f}: item '{mid}' não está no layout aprovado de '{amb}'")
            elif it.modelo not in MODELOS:
                erros.append(f"{f}: modelo '{it.modelo}' não existe ({', '.join(sorted(MODELOS))})")
            else:
                m.modelo = it.modelo
    return usados, erros
