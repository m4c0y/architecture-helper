"""Referências visuais: um YAML "irmão" por imagem (`<nome>.yaml` ao lado de `<nome>.jpg`).

Usado nas bibliotecas de estilo (`arquitetos/<id>/referencias/`) e nas referências de projeto
(`projetos/<p>/referencias/`). Três níveis, como o status das medidas:

- `analise`  → OBSERVADO: o que o agente (visão) ou um script identificou na imagem;
- `usuario`  → PREFERÊNCIA: o que o usuário confirmou que gosta / não gosta;
- aprovado   → só quando um conceito aprovado cita a referência (fora deste arquivo).

    id: sala-tijolo-01                      # = nome do arquivo sem extensão
    arquivo: sala-tijolo-01.jpg
    origem: "magnific.com/<página>, 2026-11-18"
    licenca: "Magnific/Freepik — licença gratuita, exige atribuição"
    atribuicao: "Imagem de <autor> no Freepik"
    tipo: ambiente
    ilustra: ["parede de tijolo aparente", "trilho com spots"]
    analise:
      por: "agente (visão), 2026-11-18"
      paleta: {script: "archtools paleta --cores 6", cores: [{hex: "#9C4F36", fracao: 0.22}]}
      influencias: [{estilo: industrial, peso: alto}, {estilo: mid_century, peso: baixo}]
      elementos:
        - {tipo: revestimento, descricao: "tijolinho aparente em uma parede", tags: [tijolo]}
      luz: "quente, pontual, rasante na textura"
      composicao: "uma parede de destaque, demais neutras"
    usuario: {gosto: [...], nao_gosto: [...], confirmado_em: 2026-11-18}

A paleta vem SEMPRE do script (`archtools paleta`), nunca "a olho". Medidas/proporções lidas em
imagem não entram aqui como números — referências nunca são fonte de geometria.
"""

from __future__ import annotations

import datetime as dt
import math
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .estilo import HEX, Arquiteto, carregar_vocabulario  # noqa: F401 (reexporta)

EXTENSOES = {".jpg", ".jpeg", ".png", ".webp"}
TIPOS = ("ambiente", "movel", "luminaria", "objeto", "paleta", "revestimento", "piso",
         "material", "produto")


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CorExtraida(_Base):
    hex: str
    fracao: float = Field(ge=0, le=1)

    @field_validator("hex")
    @classmethod
    def _hex(cls, v: str) -> str:
        if not HEX.match(v):
            raise ValueError(f"cor '{v}' não é hex #RRGGBB")
        return v.upper()


class PaletaExtraida(_Base):
    script: str
    cores: list[CorExtraida]

    @model_validator(mode="after")
    def _soma(self) -> "PaletaExtraida":
        # frações vêm arredondadas a 3 casas: cada uma pode errar até 0,0005
        if sum(c.fracao for c in self.cores) > 1 + 0.0005 * len(self.cores):
            raise ValueError("frações da paleta somam mais que 1")
        return self


class Influencia(_Base):
    estilo: str  # id de arquiteto quando existir; senão, nome livre (ex.: escandinavo)
    peso: Literal["alto", "medio", "baixo"]


class Elemento(_Base):
    tipo: Literal[TIPOS]  # type: ignore[valid-type]
    descricao: str
    tags: list[str] = Field(default_factory=list)


class Analise(_Base):
    por: str
    paleta: PaletaExtraida | None = None
    influencias: list[Influencia] = Field(default_factory=list)
    elementos: list[Elemento] = Field(default_factory=list)
    luz: str | None = None
    composicao: str | None = None


class Preferencia(_Base):
    gosto: list[str] = Field(default_factory=list)
    nao_gosto: list[str] = Field(default_factory=list)
    confirmado_em: dt.date


class Referencia(_Base):
    id: str
    arquivo: str
    origem: str
    licenca: str
    atribuicao: str | None = None
    tipo: Literal[TIPOS]  # type: ignore[valid-type]
    ilustra: list[str] = Field(default_factory=list)
    analise: Analise | None = None
    usuario: Preferencia | None = None


# ---------------------------------------------------------------- leitura e validação

class Achado(_Base):
    nivel: Literal["erro", "aviso"]
    onde: str
    msg: str

    def __str__(self) -> str:
        return f"[{self.nivel.upper()}] {self.onde}: {self.msg}"


def pastas_de_referencias(caminho: Path) -> list[Path]:
    """`arquitetos/` → todas as `*/referencias/`; senão, a própria pasta."""
    caminho = Path(caminho)
    subs = sorted(p for p in caminho.glob("*/referencias") if p.is_dir())
    return subs or [caminho]


def carregar_pasta(pasta: Path) -> tuple[dict[str, Referencia], list[Achado]]:
    refs: dict[str, Referencia] = {}
    achados: list[Achado] = []
    imagens = {p.name for p in pasta.iterdir() if p.suffix.lower() in EXTENSOES}
    citadas: set[str] = set()
    for f in sorted(pasta.glob("*.yaml")):
        if f.name == "index.yaml":  # formato antigo (lista única) — não é sidecar
            continue
        onde = str(f)
        try:
            r = Referencia.model_validate(yaml.safe_load(f.read_text(encoding="utf-8")))
        except Exception as e:  # noqa: BLE001 — erro de esquema vira achado
            achados.append(Achado(nivel="erro", onde=onde, msg=f"esquema: {e}"))
            continue
        if r.id != f.stem:
            achados.append(Achado(nivel="erro", onde=onde, msg=f"id '{r.id}' difere do nome do arquivo '{f.stem}'"))
        if r.arquivo not in imagens:
            achados.append(Achado(nivel="erro", onde=onde, msg=f"imagem '{r.arquivo}' não existe na pasta"))
        citadas.add(r.arquivo)
        refs[r.id] = r
    for img in sorted(imagens - citadas):
        achados.append(Achado(nivel="aviso", onde=str(pasta / img), msg="imagem sem YAML de referência"))
    return refs, achados


def validar_referencias(refs: dict[str, Referencia], vocab: set[str] | None,
                        arquitetos: set[str], onde: str) -> list[Achado]:
    achados = []
    for r in refs.values():
        if r.analise is None:
            achados.append(Achado(nivel="aviso", onde=f"{onde}/{r.id}", msg="ainda não analisada"))
            continue
        if r.analise.paleta is None:
            achados.append(Achado(nivel="aviso", onde=f"{onde}/{r.id}",
                                  msg="sem paleta (rodar archtools paleta --gravar)"))
        for el in r.analise.elementos:
            fora = sorted(set(el.tags) - vocab) if vocab is not None else []
            if fora:
                achados.append(Achado(nivel="erro", onde=f"{onde}/{r.id}",
                                      msg=f"tags fora do vocabulário (arquitetos/tags.yaml): {', '.join(fora)}"))
        for inf in r.analise.influencias:
            if inf.estilo not in arquitetos:
                achados.append(Achado(nivel="aviso", onde=f"{onde}/{r.id}",
                                      msg=f"influência '{inf.estilo}' não tem persona em arquitetos/"))
    return achados


def cobertura(refs: dict[str, Referencia]) -> dict[str, int]:
    """Quantas referências por tipo (para saber o que ainda falta pedir ao usuário)."""
    cont = {t: 0 for t in TIPOS}
    for r in refs.values():
        cont[r.tipo] += 1
    return cont


# ---------------------------------------------------------------- paleta (determinística)

def extrair_paleta(imagem: Path, n_cores: int = 6, lado: int = 200) -> list[CorExtraida]:
    """Cores dominantes por median cut (Pillow) sobre a imagem reduzida — determinístico."""
    from PIL import Image

    with Image.open(imagem) as im:
        im = im.convert("RGB")
        im.thumbnail((lado, lado), Image.Resampling.LANCZOS)
        q = im.quantize(colors=n_cores, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        pal = q.getpalette()
        contagem = q.getcolors()  # [(n, índice)]
    total = sum(n for n, _ in contagem)
    cores = []
    for n, i in sorted(contagem, key=lambda c: (-c[0], c[1])):
        r, g, b = pal[3 * i: 3 * i + 3]
        cores.append(CorExtraida(hex=f"#{r:02X}{g:02X}{b:02X}", fracao=round(n / total, 3)))
    return cores


def _lab(hex_: str) -> tuple[float, float, float]:
    """sRGB (D65) → CIELAB."""
    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(int(hex_[i:i + 2], 16) / 255) for i in (1, 3, 5))
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 1.0
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e(a: str, b: str) -> float:
    """Diferença de cor CIE76 (≈2: quase imperceptível; >10: cores claramente diferentes)."""
    return math.dist(_lab(a), _lab(b))


def mais_proxima(hex_: str, arq: Arquiteto) -> tuple[str, float]:
    melhor = min(arq.paleta, key=lambda c: delta_e(hex_, c.hex))
    return melhor.id, round(delta_e(hex_, melhor.hex), 1)


def gravar_paleta(sidecar: Path, cores: list[CorExtraida], script: str) -> None:
    """Atualiza `analise.paleta` de um YAML de referência existente (reescreve o arquivo)."""
    dados = yaml.safe_load(sidecar.read_text(encoding="utf-8"))
    analise = dados.get("analise") or {"por": f"archtools paleta, {dt.date.today().isoformat()}"}
    analise["paleta"] = {"script": script, "cores": [c.model_dump() for c in cores]}
    dados["analise"] = analise
    Referencia.model_validate(dados)  # não grava nada inválido
    sidecar.write_text(yaml.safe_dump(dados, sort_keys=False, allow_unicode=True, width=110),
                       encoding="utf-8")
