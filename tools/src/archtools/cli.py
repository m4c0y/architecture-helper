"""CLI: archtools <comando> <pasta-do-projeto>"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from .relatorios import pendencias, quadro_areas
from .schema import carregar_geometria
from .validacao import resumo, validar


def _carregar(pasta: Path):
    try:
        return carregar_geometria(pasta)
    except FileNotFoundError:
        sys.exit(f"ERRO: {pasta / 'geometria.yaml'} não encontrado")
    except ValidationError as e:
        print(f"ERRO de esquema em {pasta / 'geometria.yaml'}:", file=sys.stderr)
        for err in e.errors():
            local = ".".join(str(p) for p in err["loc"])
            print(f"  - {local}: {err['msg']}", file=sys.stderr)
        sys.exit(2)


def cmd_validar(pasta: Path) -> int:
    achados = validar(_carregar(pasta))
    for nivel in ("erro", "aviso", "nao_verificavel"):
        for a in (x for x in achados if x.nivel == nivel):
            print(a)
    print(f"\nResumo: {resumo(achados)}")
    return 1 if any(a.nivel == "erro" for a in achados) else 0


def cmd_areas(pasta: Path) -> int:
    print(quadro_areas(_carregar(pasta)))
    return 0


def cmd_planta(pasta: Path) -> int:
    from .planta2d import desenhar  # matplotlib só quando necessário
    for p in desenhar(_carregar(pasta), pasta / "saidas"):
        print(f"gerado: {p}")
    return 0


def cmd_pendencias(pasta: Path) -> int:
    texto = pendencias(_carregar(pasta))
    (pasta / "pendencias.md").write_text(texto, encoding="utf-8")
    print(texto)
    return 0


def cmd_layout(pasta: Path, arquivo: Path | None, recorte: str | None) -> int:
    """Valida um layout.yaml contra a geometria e desenha a planta com móveis."""
    from .layout import carregar_criterios, carregar_layout, resumo_ocupacao, validar_layout
    from .planta2d import desenhar
    if arquivo is None:
        sys.exit("ERRO: informe o arquivo de layout (ex.: --layout projetos/x/propostas/a/layout.yaml)")
    geo = _carregar(pasta)
    try:
        layout = carregar_layout(arquivo)
    except ValidationError as e:
        print(f"ERRO de esquema em {arquivo}:", file=sys.stderr)
        for err in e.errors():
            print(f"  - {'.'.join(str(p) for p in err['loc'])}: {err['msg']}", file=sys.stderr)
        return 2
    crit = carregar_criterios(pasta)
    achados = validar_layout(geo, layout, crit)
    print(f"Layout: {layout.nome}  (critérios: decisão {crit.decisao})")
    for nivel in ("erro", "aviso", "nao_verificavel"):
        for a in (x for x in achados if x.nivel == nivel):
            print(a)
    print(f"\nResumo: {resumo(achados)}")
    print(resumo_ocupacao(geo, layout))
    for p in desenhar(geo, arquivo.parent / "saidas", layout, crit, recorte, nome="planta-layout"):
        print(f"gerado: {p}")
    return 1 if any(a.nivel == "erro" for a in achados) else 0


def cmd_cena(pasta: Path, arquivo: Path | None, ambientes: list[str],
             acabamentos: Path | None = None, pasta_arqs: Path = Path("arquitetos")) -> int:
    """Gera saidas/cena.json para o Blender (geometria + layout + câmeras dos ambientes pedidos)."""
    import json

    from .cena import cameras_ambiente, gerar_cena
    from .layout import carregar_layout
    geo = _carregar(pasta)
    layout = carregar_layout(arquivo or pasta / "layout.yaml") if (arquivo or (pasta / "layout.yaml").exists()) else None
    cena = gerar_cena(geo, layout)
    pasta_prop = arquivo.parent if arquivo else pasta
    acab_arq = acabamentos or (pasta_prop / "acabamentos.yaml")
    if acab_arq.exists():
        from .acabamentos import aplicar_acabamentos, carregar_acabamentos, validar_acabamentos
        from .estilo import carregar_arquitetos, carregar_selecao, escolha_para, resolver
        acab = carregar_acabamentos(acab_arq)
        sel_arq = acab_arq.parent / "estilo.yaml"
        if not sel_arq.exists():
            sel_arq = pasta / "estilo.yaml"
        esc = escolha_para(carregar_selecao(sel_arq), acab.ambiente) if sel_arq.exists() else None
        if esc is None:
            sys.exit(f"ERRO: {acab_arq} precisa de um estilo.yaml com arquiteto para '{acab.ambiente}'")
        resolvido = resolver(carregar_arquitetos(pasta_arqs), *esc)
        erros = validar_acabamentos(acab, resolvido, geo, cena)
        for e in erros:
            print(f"ERRO acabamentos: {e}")
        if erros:
            return 1
        aplicar_acabamentos(cena, acab, resolvido, geo)
        print(f"acabamentos: {acab_arq} (estilo {sel_arq}): {len(cena['revestimentos'])} revestimentos, "
              f"{len(cena['luzes'])} luzes")
    for amb in ambientes:
        cena["cameras"] += cameras_ambiente(geo, amb, moveis=cena["moveis"])
    destino = (arquivo.parent if arquivo else pasta) / "saidas" / "cena.json"  # proposta -> saídas da proposta
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(cena, ensure_ascii=False), encoding="utf-8")
    print(f"paredes {len(cena['paredes'])}, recortes {len(cena['recortes'])}, vidros {len(cena['vidros'])}, "
          f"pisos {len(cena['pisos'])}, tetos {len(cena['tetos'])}, móveis {len(cena['moveis'])}, "
          f"câmeras {len(cena['cameras'])}")
    for s in cena["suposicoes"]:
        print(f"suposição: {s}")
    print(f"gerado: {destino}")
    return 0


def cmd_estilo(pasta: Path, arquivo: Path | None, pasta_arqs: Path, ambiente: str | None) -> int:
    """Lista os arquitetos e resolve a seleção de estilo (casa toda / ambiente / proposta)."""
    from .estilo import (carregar_arquitetos, carregar_selecao, escolha_para, resolver,
                         texto_resolvido, validar_selecao)
    try:
        arqs = carregar_arquitetos(pasta_arqs)
    except (ValidationError, ValueError) as e:
        print(f"ERRO nos arquitetos: {e}", file=sys.stderr)
        return 2
    if not arqs:
        sys.exit(f"ERRO: nenhum arquiteto em {pasta_arqs}/<id>/arquiteto.yaml")
    print("Arquitetos disponíveis:")
    for a in arqs.values():
        print(f"  {a.id:<26} {a.nome} — {a.estilo} [{a.estado}]")
    arquivo = arquivo or pasta / "estilo.yaml"
    if not arquivo.exists():
        print(f"\nSem seleção: {arquivo} não existe (nenhum arquiteto escolhido ainda).")
        return 0
    try:
        sel = carregar_selecao(arquivo)
    except ValidationError as e:
        print(f"ERRO de esquema em {arquivo}:", file=sys.stderr)
        for err in e.errors():
            print(f"  - {'.'.join(str(p) for p in err['loc'])}: {err['msg']}", file=sys.stderr)
        return 2
    erros = validar_selecao(sel, arqs, {a.id for a in _carregar(pasta).ambientes})
    for e in erros:
        print(f"ERRO: {e}")
    if erros:
        return 1
    alvos = [ambiente] if ambiente else ([None] if sel.padrao else []) + list(sel.ambientes)
    for alvo in alvos:
        esc = escolha_para(sel, alvo)
        if esc is None:
            print(f"\n{alvo}: sem arquiteto (nem padrão nem escolha do ambiente)")
            continue
        print()
        print(texto_resolvido(resolver(arqs, *esc), arqs))
    return 0


def cmd_referencias(caminho: Path, pasta_arqs: Path) -> int:
    """Valida os YAML de referência de uma pasta (ou de todas as bibliotecas em arquitetos/)."""
    from .estilo import carregar_arquitetos, carregar_vocabulario
    from .referencias import carregar_pasta, cobertura, pastas_de_referencias, validar_referencias
    vocab = carregar_vocabulario(pasta_arqs)
    ids = set(carregar_arquitetos(pasta_arqs)) if pasta_arqs.exists() else set()
    erros = 0
    for pasta in pastas_de_referencias(caminho):
        refs, achados = carregar_pasta(pasta)
        achados += validar_referencias(refs, vocab, ids, str(pasta))
        cob = cobertura(refs)
        print()
        print(f"## {pasta}: {len(refs)} referência(s)")
        print("  por tipo: " + ", ".join(f"{t} {n}" for t, n in cob.items()))
        for a in sorted(achados, key=lambda a: a.nivel):
            print(f"  {a}")
        erros += sum(a.nivel == "erro" for a in achados)
    print()
    print(f"Erros: {erros}")
    return 1 if erros else 0


def cmd_paleta(imagem: Path, n_cores: int, arquiteto: str | None, pasta_arqs: Path, gravar: bool) -> int:
    """Extrai a paleta de uma imagem (median cut) e, opcionalmente, compara com uma persona."""
    from .estilo import carregar_arquitetos
    from .referencias import extrair_paleta, gravar_paleta, mais_proxima
    if not imagem.is_file():
        sys.exit(f"ERRO: imagem {imagem} não encontrada")
    cores = extrair_paleta(imagem, n_cores)
    arq = None
    if arquiteto:
        arqs = carregar_arquitetos(pasta_arqs)
        if arquiteto not in arqs:
            sys.exit(f"ERRO: arquiteto '{arquiteto}' não existe ({', '.join(arqs)})")
        arq = arqs[arquiteto]
    print(f"Paleta de {imagem.name} ({n_cores} cores, median cut):")
    for c in cores:
        extra = ""
        if arq:
            cid, de = mais_proxima(c.hex, arq)
            extra = f"   ≈ {cid} (ΔE {de})"
        print(f"  {c.hex}  {c.fracao:6.1%}{extra}")
    if arq:
        print("ΔE (CIE76): ~2 quase igual; <10 parecida; >10 claramente diferente.")
    if gravar:
        sidecar = imagem.with_suffix(".yaml")
        if not sidecar.exists():
            sys.exit(f"ERRO: {sidecar} não existe — crie o YAML da referência antes de gravar a paleta")
        gravar_paleta(sidecar, cores, f"archtools paleta --cores {n_cores}")
        print(f"gravado: {sidecar} (analise.paleta)")
    return 0


COMANDOS = {"validar": cmd_validar, "areas": cmd_areas,
            "planta": cmd_planta, "pendencias": cmd_pendencias, "layout": None, "cena": None,
            "estilo": None, "referencias": None, "paleta": None}


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="archtools", description=__doc__)
    p.add_argument("comando", choices=COMANDOS)
    p.add_argument("projeto", type=Path,
                   help="pasta do projeto (contém geometria.yaml); em 'referencias', a pasta de "
                        "referências ou arquitetos/; em 'paleta', a imagem")
    p.add_argument("--layout", type=Path, help="(layout) arquivo layout.yaml")
    p.add_argument("--recorte", help="(layout) id do ambiente para dar zoom na planta")
    p.add_argument("--cameras", nargs="*", default=[], help="(cena) ids de ambientes para gerar câmeras")
    p.add_argument("--estilo", type=Path, help="(estilo) seleção (padrão: <projeto>/estilo.yaml)")
    p.add_argument("--arquitetos", type=Path, default=Path("arquitetos"), help="(estilo) pasta dos arquitetos")
    p.add_argument("--ambiente", help="(estilo) resolver só este ambiente")
    p.add_argument("--acabamentos", type=Path, help="(cena) acabamentos.yaml (padrão: junto do layout)")
    p.add_argument("--cores", type=int, default=6, help="(paleta) número de cores")
    p.add_argument("--arquiteto", help="(paleta) comparar com a paleta desta persona")
    p.add_argument("--gravar", action="store_true", help="(paleta) gravar em analise.paleta do YAML da imagem")
    args = p.parse_args(argv)
    if args.comando == "layout":
        return cmd_layout(args.projeto, args.layout, args.recorte)
    if args.comando == "cena":
        return cmd_cena(args.projeto, args.layout, args.cameras, args.acabamentos, args.arquitetos)
    if args.comando == "referencias":
        return cmd_referencias(args.projeto, args.arquitetos)
    if args.comando == "paleta":
        return cmd_paleta(args.projeto, args.cores, args.arquiteto, args.arquitetos, args.gravar)
    if args.comando == "estilo":
        return cmd_estilo(args.projeto, args.estilo, args.arquitetos, args.ambiente)
    return COMANDOS[args.comando](args.projeto)


if __name__ == "__main__":
    sys.exit(main())
