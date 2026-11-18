"""CLI: archtools <comando> <pasta-do-projeto>"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from .relatorios import pendencias, quadro_areas
from .schema import carregar_geometria
from .validacao import resumo, validar

COMANDO = "archtools"  # linha de comando atual (vai para os manifestos)


def _manifesto(pasta: Path, saidas, entradas) -> None:
    from .manifesto import registrar
    registrar(pasta, list(saidas), [e for e in entradas if e is not None], COMANDO)


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
    gerados = desenhar(_carregar(pasta), pasta / "saidas")
    for p in gerados:
        print(f"gerado: {p}")
    _manifesto(pasta / "saidas", gerados, [pasta / "geometria.yaml"])
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
    from .layout import ambiente_do_arquivo
    try:
        cat = _catalogo(pasta)
        layout = carregar_layout(arquivo, cat, ambiente_do_arquivo(arquivo))
    except ValueError as e:
        if not isinstance(e, ValidationError):
            print(f"ERRO: {e}", file=sys.stderr)
            return 2
        raise
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
    gerados = desenhar(geo, arquivo.parent / "saidas", layout, crit, recorte, nome="planta-layout")
    for p in gerados:
        print(f"gerado: {p}")
    _manifesto(arquivo.parent / "saidas", gerados, [pasta / "geometria.yaml", arquivo, pasta / "criterios.yaml"])
    return 1 if any(a.nivel == "erro" for a in achados) else 0


def _catalogo(pasta: Path) -> dict:
    from .catalogo import carregar_catalogo, pastas_catalogo
    return carregar_catalogo(pastas_catalogo(pasta))


def _arquivos_catalogo(pasta: Path, layout) -> list[Path]:
    from .catalogo import pastas_catalogo
    usados = {m.produto for m in (layout.moveis if layout else []) if m.produto}
    return [f for d in pastas_catalogo(pasta) for f in d.glob("*.yaml") if f.stem in usados]


def _aplicar_conceito(cena: dict, geo, pasta: Path, arq: Path, pasta_arqs: Path, entradas: list,
                      ambiente_padrao: str | None) -> list[str]:
    """Valida e aplica um conceito.yaml (ou acabamentos.yaml antigo) à cena. Devolve erros."""
    from .acabamentos import aplicar_acabamentos, carregar_acabamentos, validar_acabamentos
    from .estilo import carregar_arquitetos, carregar_selecao, escolha_para, resolver
    if arq.name == "conceito.yaml":
        from .conceito import (avisos_cor_real, carregar_conceito, escolha_do_conceito,
                               validar_referencias_aprovadas)
        c = carregar_conceito(arq, ambiente_padrao)
        esc = escolha_do_conceito(c, pasta)
        if esc is None:
            return [f"{arq}: sem `estilo` e sem `padrao` em {pasta / 'estilo.yaml'}"]
        acab, alvo = c.acabamentos(), c.ambiente
        erros = validar_referencias_aprovadas(c, pasta, pasta_arqs)
        for a in avisos_cor_real(c, cena):
            print(f"AVISO conceito: {a}")
        if c.estilo is None:
            entradas.append(pasta / "estilo.yaml")
    else:  # formato antigo: acabamentos.yaml + estilo.yaml
        acab = carregar_acabamentos(arq)
        sel_arq = arq.parent / "estilo.yaml"
        if not sel_arq.exists():
            sel_arq = pasta / "estilo.yaml"
        par = escolha_para(carregar_selecao(sel_arq), acab.ambiente) if sel_arq.exists() else None
        if par is None:
            return [f"{arq} precisa de um estilo.yaml com arquiteto para '{acab.ambiente}'"]
        esc, alvo, erros = par[1], acab.ambiente, []
        entradas.append(sel_arq)
    resolvido = resolver(carregar_arquitetos(pasta_arqs), alvo, esc)
    entradas += [arq, pasta_arqs / "tags.yaml"] + [pasta_arqs / a / "arquiteto.yaml"
                                                    for a in [esc.principal, *esc.acentos]]
    erros += validar_acabamentos(acab, resolvido, geo, cena)
    if not erros:
        aplicar_acabamentos(cena, acab, resolvido, geo)
        print(f"conceito: {arq} ({esc.principal}{' + ' + ', '.join(esc.acentos) if esc.acentos else ''})")
    return erros


def cmd_cena(pasta: Path, arquivo: Path | None, ambientes: list[str],
             acabamentos: Path | None = None, pasta_arqs: Path = Path("arquitetos")) -> int:
    """Gera cena.json para o Blender.

    Sem --layout: layouts aprovados de todos os ambientes + `ambientes/<id>/conceito.yaml` de cada um
    -> saidas/cena.json do projeto. Com --layout de uma proposta: esse layout + o conceito.yaml
    (ou acabamentos.yaml antigo) ao lado dele -> saidas/ da proposta."""
    import json

    from .cena import cameras_ambiente, gerar_cena
    from .layout import ambiente_do_arquivo, carregar_layout, carregar_layout_projeto, layouts_do_projeto
    geo = _carregar(pasta)
    try:
        cat = _catalogo(pasta)
        if arquivo is not None:
            layout, arqs_layout = carregar_layout(arquivo, cat, ambiente_do_arquivo(arquivo)), [arquivo]
        else:
            layout, arqs_layout = carregar_layout_projeto(pasta, cat), layouts_do_projeto(pasta)
    except ValueError as e:
        if isinstance(e, ValidationError):
            raise
        sys.exit(f"ERRO: {e}")
    cena = gerar_cena(geo, layout)
    entradas = [pasta / "geometria.yaml", *arqs_layout, *_arquivos_catalogo(pasta, layout)]

    if acabamentos is not None:
        conceitos = [(acabamentos, None)]
    elif arquivo is not None:
        c = next((arquivo.parent / n for n in ("conceito.yaml", "acabamentos.yaml")
                  if (arquivo.parent / n).exists()), None)
        conceitos = [(c, ambiente_do_arquivo(arquivo))] if c else []
    else:
        conceitos = [(f, f.parent.name) for f in sorted(pasta.glob("ambientes/*/conceito.yaml"))]
    erros = []
    for arq, amb in conceitos:
        erros += _aplicar_conceito(cena, geo, pasta, arq, pasta_arqs, entradas, amb)
    for e in erros:
        print(f"ERRO conceito: {e}")
    if erros:
        return 1

    from .materiais import neutros
    faltam = neutros(cena)
    if faltam:
        cena["suposicoes"].append("sem aparência definida (cinza de marcação): " + ", ".join(faltam))
    for amb in ambientes:
        cena["cameras"] += cameras_ambiente(geo, amb, moveis=cena["moveis"])
    destino = (arquivo.parent if arquivo else pasta) / "saidas" / "cena.json"  # proposta -> saídas da proposta
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(cena, ensure_ascii=False), encoding="utf-8")
    print(f"paredes {len(cena['paredes'])}, recortes {len(cena['recortes'])}, vidros {len(cena['vidros'])}, "
          f"pisos {len(cena['pisos'])}, tetos {len(cena['tetos'])}, móveis {len(cena['moveis'])}, "
          f"câmeras {len(cena['cameras'])}")
    for s_ in cena["suposicoes"]:
        print(f"suposição: {s_}")
    _manifesto(destino.parent, [destino], entradas)
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


def cmd_status(pasta: Path) -> int:
    """Fase dos ambientes, aprovações (e alterações sem decisão), saídas desatualizadas, pendências."""
    from .status import relatorio
    texto, problemas = relatorio(pasta, _carregar(pasta))
    print(texto)
    return 1 if problemas else 0


def cmd_aprovacao(pasta: Path, numero: str | None, arquivos: list[str], base: list[str]) -> int:
    """Imprime o cabeçalho YAML de uma decisão nova, com os hashes atuais dos arquivos aprovados."""
    from .decisoes import bloco_aprovacao, carregar
    if not arquivos:
        sys.exit("ERRO: informe --arquivos (relativos ao projeto), ex.: --arquivos layout.yaml")
    if numero is None:
        nums = [int(d.numero) for d in carregar(pasta)]
        numero = f"{max(nums, default=0) + 1:04d}"
    try:
        print(bloco_aprovacao(pasta, numero, arquivos, base), end="")
    except FileNotFoundError as e:
        sys.exit(f"ERRO: {e}")
    return 0


COMANDOS = {"validar": cmd_validar, "areas": cmd_areas,
            "planta": cmd_planta, "pendencias": cmd_pendencias, "layout": None, "cena": None,
            "estilo": None, "referencias": None, "paleta": None,
            "status": None, "aprovacao": None}


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
    p.add_argument("--numero", help="(aprovacao) número da decisão (padrão: próximo)")
    p.add_argument("--arquivos", nargs="*", default=[], help="(aprovacao) arquivos aprovados, relativos ao projeto")
    p.add_argument("--base", nargs="*", default=[], help="(aprovacao) arquivos de base, relativos ao projeto")
    args = p.parse_args(argv)
    global COMANDO
    COMANDO = "archtools " + " ".join(sys.argv[1:] if argv is None else argv)
    if args.comando == "layout":
        return cmd_layout(args.projeto, args.layout, args.recorte)
    if args.comando == "cena":
        return cmd_cena(args.projeto, args.layout, args.cameras, args.acabamentos, args.arquitetos)
    if args.comando == "status":
        return cmd_status(args.projeto)
    if args.comando == "aprovacao":
        return cmd_aprovacao(args.projeto, args.numero, args.arquivos, args.base)
    if args.comando == "referencias":
        return cmd_referencias(args.projeto, args.arquitetos)
    if args.comando == "paleta":
        return cmd_paleta(args.projeto, args.cores, args.arquiteto, args.arquitetos, args.gravar)
    if args.comando == "estilo":
        return cmd_estilo(args.projeto, args.estilo, args.arquitetos, args.ambiente)
    return COMANDOS[args.comando](args.projeto)


if __name__ == "__main__":
    sys.exit(main())
