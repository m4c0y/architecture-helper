"""Arquitetos (personas de estilo) e combinação principal + acentos."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from archtools.cli import main
from archtools.estilo import (Arquiteto, Escolha, Selecao, carregar_arquitetos, escolha_para,
                              resolver, validar_selecao)

RAIZ = Path(__file__).resolve().parents[2]
EXEMPLO = Path(__file__).parent / "fixtures" / "exemplo"


def arq(id_, cores, evitar_tags=(), materiais=(), luminarias=()):
    return {
        "id": id_, "nome": id_, "estilo": id_, "estado": "rascunho", "fonte": "teste", "resumo": "r",
        "paleta": [{"id": c, "nome": c, "hex": "#112233", "papel": p, "uso": "u", "tags": t}
                   for c, p, t in cores],
        "materiais": [{"id": m, "nome": m, "onde": ["moveis"], "uso": "u", "tags": t} for m, t in materiais],
        "iluminacao": {"temperatura_k": {"geral": 2700 if id_ == "a" else 4000}, "estrategia": "e"},
        "luminarias": [{"id": lu, "tipo": "pendente", "descricao": "d", "temperatura_k": 2700, "tags": t}
                       for lu, t in luminarias],
        "regras": {"fazer": ["f"], "evitar": ["e"], "evitar_tags": list(evitar_tags)},
    }


@pytest.fixture
def arqs():
    a = Arquiteto.model_validate(arq("a", [("neutro", "base", []), ("verde", "destaque", [])],
                                     evitar_tags=["latao"], materiais=[("carvalho", [])]))
    b = Arquiteto.model_validate(arq("b", [("creme", "base", []), ("mostarda", "destaque", []),
                                           ("dourado", "destaque", ["latao"])],
                                     materiais=[("nogueira", []), ("latao", ["latao"])],
                                     luminarias=[("globo", ["latao"]), ("tripe", [])]))
    return {"a": a, "b": b}


def test_principal_define_base_e_luz(arqs):
    r = resolver(arqs, "dorm2", Escolha(principal="a", acentos=["b"]))
    assert r.iluminacao.temperatura_k["geral"] == 2700
    assert [i.dado.id for i in r.paleta if i.papel == "principal"] == ["neutro", "verde"]


def test_acento_contribui_so_destaques(arqs):
    r = resolver(arqs, "dorm2", Escolha(principal="a", acentos=["b"]))
    do_acento = [i.dado.id for i in r.paleta if i.origem == "b"]
    assert do_acento == ["mostarda"]  # 'creme' é base de b: não entra; 'dourado' é conflito


def test_conflito_exclui_item_do_acento(arqs):
    r = resolver(arqs, "dorm2", Escolha(principal="a", acentos=["b"]))
    assert {(c.categoria, c.item) for c in r.conflitos} == {
        ("cor", "dourado"), ("material", "latao"), ("luminária", "globo")}
    assert [i.dado.id for i in r.luminarias] == ["tripe"]
    assert "latao" not in [i.dado.id for i in r.materiais]


def test_sem_acento_sem_conflito(arqs):
    r = resolver(arqs, "padrao", Escolha(principal="b"))
    assert r.conflitos == [] and len(r.paleta) == 3


def test_ambiente_sobrepoe_padrao():
    sel = Selecao(padrao=Escolha(principal="a"), ambientes={"quarto": Escolha(principal="b")})
    assert escolha_para(sel, "quarto")[1].principal == "b"
    assert escolha_para(sel, "sala")[1].principal == "a"
    assert escolha_para(Selecao(), "sala") is None


def test_validacoes_de_esquema():
    with pytest.raises(ValidationError):
        Escolha(principal="a", acentos=["a"])
    with pytest.raises(ValidationError, match="hex"):
        Arquiteto.model_validate(arq("x", [("c", "base", [])]) | {
            "paleta": [{"id": "c", "nome": "c", "hex": "azul", "papel": "base", "uso": "u"}]})
    with pytest.raises(ValidationError, match="base"):
        Arquiteto.model_validate(arq("x", [("c", "destaque", [])]))


def test_validar_selecao(arqs):
    sel = Selecao(padrao=Escolha(principal="z"), ambientes={"inexistente": Escolha(principal="a")})
    erros = validar_selecao(sel, arqs, {"sala", "quarto"})
    assert any("'z' não existe" in e for e in erros)
    assert any("inexistente" in e for e in erros)


def test_arquitetos_do_repositorio_carregam():
    arqs = carregar_arquitetos(RAIZ / "arquitetos")
    assert set(arqs) == {"industrial", "brasileiro_contemporaneo", "japandi", "mid_century",
                         "minimalista", "rustico_moderno"}
    secoes = ["## Filosofia", "## Como penso um ambiente", "## Móveis", "## Proporções e composição",
              "## Decoração", "## Elementos arquitetônicos", "## Combina com", "## Erros comuns",
              "## Referências que a biblioteca precisa", "## Perguntas que faço ao usuário"]
    for a in arqs.values():
        persona = (RAIZ / "arquitetos" / a.id / "persona.md").read_text(encoding="utf-8")
        faltam = [s for s in secoes if s not in persona]
        assert not faltam, f"{a.id}/persona.md sem {faltam}"
        assert (RAIZ / "arquitetos" / a.id / "referencias").is_dir()


def test_cli_estilo(tmp_path, capsys):
    sel = tmp_path / "estilo.yaml"
    sel.write_text(yaml.safe_dump({"ambientes": {"sala": {"principal": "japandi", "acentos": ["mid_century"]}}}),
                   encoding="utf-8")
    assert main(["estilo", str(EXEMPLO), "--estilo", str(sel), "--arquitetos", str(RAIZ / "arquitetos")]) == 0
    out = capsys.readouterr().out
    assert "## sala: Estúdio Ma + Estúdio Atômico (acento)" in out
    assert "conflito: cor 'mostarda' de mid_century" in out
