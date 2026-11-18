"""`archtools status <projeto>`: estado do projeto calculado, nunca guardado à mão.

- Decisões e aprovações (cabeçalho `aprova` com hash): o que está aprovado e se o arquivo foi
  alterado depois da aprovação sem nova decisão ("drift").
- Saídas: desatualizadas (entrada mudou), sem manifesto (geradas antes ou sobras).
- Pendências de medição: quantas e se pendencias.md está em dia.
- Fase de cada ambiente, derivada dos arquivos aprovados.

Fases (decisão do usuário, 2026-11-18): P1 levantamento · P2 projeto do ambiente (2a briefing,
2b conceito, 2c layout) · P3 preview e refinamento · P4 detalhamento · P5 render final · P6 entrega.
Cada ambiente tem `ambientes/<id>/` com briefing.md, conceito.yaml e layout.yaml (a pasta é a
aprovação; propostas ficam em propostas/). O layout.yaml único antigo do projeto ainda conta como
layout aprovado dos ambientes que tiverem itens nele, até ser migrado.
P4–P6 ainda não têm artefatos próprios: só P2a–P3 são distinguíveis por enquanto.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import yaml

from .decisoes import aprovacoes, carregar
from .manifesto import rel, verificar
from .relatorios import pendencias
from .schema import Geometria

FONTES_APROVAVEIS = ("geometria.yaml", "layout.yaml", "estilo.yaml", "criterios.yaml")


def _layout_por_ambiente(pasta: Path) -> Counter:
    """Itens nos layouts aprovados (pastas de ambiente + layout.yaml único antigo)."""
    cont = Counter()
    for f in sorted(pasta.glob("ambientes/*/layout.yaml")):
        dados = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        cont[f.parent.name] += len(dados.get("moveis") or [])
    f = pasta / "layout.yaml"
    if f.exists():
        dados = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        cont.update(m.get("ambiente") for m in dados.get("moveis", []))
    return cont


def _propostas_abertas(pasta: Path) -> Counter:
    """Propostas não arquivadas por ambiente (pelo `ambiente:` do layout/conceito da proposta)."""
    cont = Counter()
    for d in sorted((pasta / "propostas").glob("*/")):
        leia = d / "LEIA-ME.md"
        if leia.exists() and "arquivad" in leia.read_text(encoding="utf-8")[:400].lower():
            continue
        ambs = set()
        for nome in ("layout.yaml", "conceito.yaml"):
            if (d / nome).exists():
                dados = yaml.safe_load((d / nome).read_text(encoding="utf-8")) or {}
                ambs |= {dados.get("ambiente")} | {m.get("ambiente") for m in dados.get("moveis") or []}
        for a in ambs - {None}:
            cont[a] += 1
    return cont


def _estilo(pasta: Path) -> tuple[bool, set[str]]:
    f = pasta / "estilo.yaml"
    if not f.exists():
        return False, set()
    dados = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    return bool(dados.get("padrao")), set(dados.get("ambientes") or {})


def fase_ambiente(tem_layout: bool, tem_conceito: bool, tem_briefing: bool = False) -> str:
    if tem_layout and tem_conceito:
        return "P3 preview e refinamento"
    if tem_layout:
        return "P2b conceito (layout aprovado, conceito pendente)"
    if tem_conceito:
        return "P2c layout (conceito aprovado, layout pendente)"
    if tem_briefing:
        return "P2b/P2c conceito e layout (briefing feito)"
    return "P2a briefing (nada aprovado)"


def relatorio(pasta: Path, geo: Geometria) -> tuple[str, int]:
    """Texto do status e quantidade de problemas (drift + saídas não-ok + pendencias.md velho)."""
    pasta = Path(pasta)
    linhas = [f"# Status — {geo.projeto}", ""]
    problemas = 0

    decs = carregar(pasta)
    est = Counter(d.estado for d in decs)
    com_cab = sum(d.cabecalho is not None for d in decs)
    linhas.append(f"## Decisões: {len(decs)} (" + ", ".join(f"{k} {v}" for k, v in sorted(est.items()))
                  + f"); com cabeçalho de aprovação: {com_cab}")
    aps = aprovacoes(pasta, decs)
    aprovados = {a.arquivo for a in aps}
    for a in aps:
        if a.estado == "ok":
            linhas.append(f"  OK        {a.arquivo} (decisão {a.decisao})")
        else:
            problemas += 1
            msg = "ALTERADO depois da aprovação, sem nova decisão" if a.estado == "alterado" else "AUSENTE"
            linhas.append(f"  {msg}: {a.arquivo} (aprovado na decisão {a.decisao})")
    fontes = [f for f in FONTES_APROVAVEIS if (pasta / f).exists()] + [
        f.relative_to(pasta).as_posix() for f in sorted(pasta.glob("ambientes/*/*.yaml"))]
    sem = [f for f in fontes if f not in aprovados]
    if sem:
        linhas.append(f"  sem aprovação registrada com hash: {', '.join(sem)}")
        linhas.append("  (decisões antigas não têm cabeçalho; use `archtools aprovacao` na próxima decisão)")

    linhas += ["", "## Saídas"]
    arquivadas = [p for p in sorted((pasta / "propostas").glob("*/LEIA-ME.md"))
                  if "arquivad" in p.read_text(encoding="utf-8")[:400].lower()]
    ignorar = [rel(p.parent) + "/" for p in arquivadas]
    saidas = [s for s in verificar(pasta) if not any(s.arquivo.startswith(i) for i in ignorar)]
    cont = Counter(s.estado for s in saidas)
    linhas.append("  " + (", ".join(f"{k}: {v}" for k, v in sorted(cont.items())) or "nenhuma"))
    soltos: dict[str, int] = {}
    for s in saidas:
        if s.estado == "ok":
            continue
        problemas += 1
        if s.estado == "sem_manifesto":  # agrupa por pasta: geralmente é uma pasta inteira antiga
            soltos[s.arquivo.rsplit("/", 1)[0]] = soltos.get(s.arquivo.rsplit("/", 1)[0], 0) + 1
            continue
        extra = f" — {'; '.join(s.motivos)}" if s.motivos else ""
        linhas.append(f"  {s.estado.upper():<14} {s.arquivo}{extra}")
    for d, n in soltos.items():
        linhas.append(f"  SEM_MANIFESTO  {d}/ ({n} arquivo{'s' if n > 1 else ''}) — regerar; o que não voltar é sobra")
    if arquivadas:
        linhas.append(f"  ({len(arquivadas)} proposta(s) arquivada(s) não conferida(s): "
                      + ", ".join(p.parent.name for p in arquivadas) + ")")

    linhas += ["", "## Pendências de medição"]
    texto = pendencias(geo)
    n = sum(1 for ln in texto.splitlines() if ln.startswith("- [ ]"))
    arq = pasta / "pendencias.md"
    em_dia = arq.exists() and arq.read_text(encoding="utf-8").replace("\r\n", "\n") == texto
    if not em_dia:
        problemas += 1
    linhas.append(f"  {n} itens; pendencias.md " + ("em dia" if em_dia else
                                                   "DESATUALIZADO — rode `archtools pendencias`"))

    linhas += ["", "## Ambientes"]
    por_amb = _layout_por_ambiente(pasta)
    abertas = _propostas_abertas(pasta)
    _, com_estilo = _estilo(pasta)  # estilo.yaml antigo por ambiente conta como conceito aprovado
    for amb in geo.ambientes:
        if amb.tipo not in ("interno", "varanda"):
            continue
        d = pasta / "ambientes" / amb.id
        conceito = (d / "conceito.yaml").exists() or amb.id in com_estilo
        fase = fase_ambiente(por_amb[amb.id] > 0, conceito, (d / "briefing.md").exists())
        det = [f"{por_amb[amb.id]} itens no layout" if por_amb[amb.id] else "sem layout"]
        if abertas[amb.id]:
            det.append(f"{abertas[amb.id]} proposta(s) em aberto")
        linhas.append(f"  {amb.id:<18} {fase}  [{'; '.join(det)}]")
    linhas += ["", f"Problemas: {problemas}"]
    return "\n".join(linhas), problemas
