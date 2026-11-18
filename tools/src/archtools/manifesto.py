"""Manifestos de saídas: de quais entradas (e de qual versão delas) cada arquivo gerado veio.

Cada pasta de saídas tem um `manifest.json`:

    {"versao": 1,
     "saidas": {"planta.png": {"entradas": {"projetos/p/geometria.yaml": "3fa1…"},
                               "comando": "archtools planta projetos/p",
                               "gerado_em": "2026-11-18T21:00:00", "archtools": "0.1.0"}}}

Caminhos das entradas: relativos à pasta de onde o comando roda (a raiz do repositório).
Hash: sha256 (16 primeiros hex) do conteúdo; em arquivos de texto, CRLF vira LF antes, para o
mesmo conteúdo dar o mesmo hash no Windows e no git.

Uma saída está DESATUALIZADA se alguma entrada mudou, sumiu ou é ela mesma uma saída
desatualizada (ex.: render ← cena.json ← geometria.yaml). Arquivos na pasta que nenhum
manifesto lista são relatados como "sem manifesto" (gerados antes disto, ou sobras).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

TEXTO = {".yaml", ".yml", ".md", ".json", ".py", ".txt", ".svg", ".csv"}
NOME = "manifest.json"
IGNORAR = {NOME, ".gitkeep"}
IGNORAR_SUFIXOS = {".blend1"}  # backup automático do Blender


def versao() -> str:
    try:
        from importlib.metadata import version
        return version("archtools")
    except Exception:  # noqa: BLE001
        return "desconhecida"


def hash_arquivo(p: Path) -> str:
    dados = Path(p).read_bytes()
    if Path(p).suffix.lower() in TEXTO:
        dados = dados.replace(b"\r\n", b"\n")
    return hashlib.sha256(dados).hexdigest()[:16]


def rel(p: Path) -> str:
    p = Path(p).resolve()
    try:
        return p.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return p.as_posix()


def registrar(pasta: Path, saidas: list[Path], entradas: list[Path], comando: str) -> Path:
    """Acrescenta/atualiza no manifest.json da pasta as saídas geradas agora."""
    pasta = Path(pasta)
    arq = pasta / NOME
    man = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {"versao": 1, "saidas": {}}
    ent = {rel(e): hash_arquivo(e) for e in entradas if e is not None and Path(e).exists()}
    agora = dt.datetime.now().isoformat(timespec="seconds")
    for s in saidas:
        nome = Path(s).resolve().relative_to(pasta.resolve()).as_posix()
        man["saidas"][nome] = {"entradas": ent, "comando": comando, "gerado_em": agora, "archtools": versao()}
    man["saidas"] = dict(sorted(man["saidas"].items()))
    arq.write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
    return arq


@dataclass
class Saida:
    arquivo: str  # relativo à raiz
    estado: str  # "ok" | "desatualizada" | "ausente" | "sem_manifesto"
    motivos: list[str] = field(default_factory=list)


def verificar(raiz_busca: Path) -> list[Saida]:
    """Estado de todas as saídas sob `raiz_busca` (procura manifest.json recursivamente)."""
    raiz_busca = Path(raiz_busca)
    registros: dict[str, dict] = {}
    listados: set[Path] = set()
    pastas: list[Path] = []
    for mf in sorted(raiz_busca.rglob(NOME)):
        pastas.append(mf.parent)
        man = json.loads(mf.read_text(encoding="utf-8"))
        for nome, info in man.get("saidas", {}).items():
            caminho = mf.parent / nome
            listados.add(caminho.resolve())
            registros[rel(caminho)] = info

    cache: dict[str, Saida] = {}

    def avaliar(chave: str, pilha: tuple = ()) -> Saida:
        if chave in cache:
            return cache[chave]
        info = registros[chave]
        if not Path(chave).exists():
            s = Saida(chave, "ausente", ["arquivo listado no manifesto não existe"])
        else:
            motivos = []
            for ent, h in info["entradas"].items():
                if not Path(ent).exists():
                    motivos.append(f"{ent} não existe mais")
                elif hash_arquivo(Path(ent)) != h:
                    motivos.append(f"{ent} mudou")
                elif ent in registros and ent not in pilha:
                    dep = avaliar(ent, pilha + (chave,))
                    if dep.estado != "ok":
                        motivos.append(f"{ent} está desatualizada")
            s = Saida(chave, "desatualizada" if motivos else "ok", motivos)
        cache[chave] = s
        return s

    resultado = [avaliar(k) for k in sorted(registros)]
    # arquivos soltos nas pastas de saída (inclusive pastas sem manifesto ainda)
    for pasta in sorted({*pastas, *(p for p in raiz_busca.rglob("saidas") if p.is_dir())}):
        subpastas = [p for p in pastas if p != pasta and p.is_relative_to(pasta)]  # têm manifesto próprio
        for f in sorted(pasta.rglob("*")):
            if (f.is_file() and f.name not in IGNORAR and f.suffix not in IGNORAR_SUFIXOS
                    and f.resolve() not in listados and not any(f.is_relative_to(p) for p in subpastas)):
                resultado.append(Saida(rel(f), "sem_manifesto"))
    return resultado
