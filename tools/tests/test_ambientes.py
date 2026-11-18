"""Passo 2: catálogo de produtos, layouts por ambiente, conceito.yaml e fases no status."""

import json
import shutil
from pathlib import Path

import pytest
import yaml

from archtools.catalogo import carregar_catalogo
from archtools.cli import main
from archtools.layout import carregar_layout, carregar_layout_projeto

EXEMPLO = Path(__file__).parent / "fixtures" / "exemplo"
RAIZ = Path(__file__).resolve().parents[2]

PRODUTO = {"id": "sofa-teste", "nome": "Sofá de teste", "categoria": "sofa", "fonte": "anúncio (teste)",
           "largura": {"valor": 1800, "status": "estimado", "fonte": "anúncio"},
           "profundidade": {"valor": 900, "status": "estimado", "fonte": "anúncio"},
           "altura": {"valor": 800, "status": "estimado", "fonte": "anúncio"},
           "cor_real": "#556b2f"}


def _y(p: Path, dados) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(dados, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return p


@pytest.fixture
def proj(tmp_path, monkeypatch):
    destino = tmp_path / "projetos" / "exemplo"
    shutil.copytree(EXEMPLO, destino)
    shutil.copytree(RAIZ / "arquitetos", tmp_path / "arquitetos")
    monkeypatch.chdir(tmp_path)
    p = Path("projetos/exemplo")
    _y(p / "catalogo" / "produtos" / "sofa-teste.yaml", PRODUTO)
    return p


def _sofa(**extra):
    return {"id": "sofa", "nome": "Sofá", "produto": "sofa-teste", "x": 1500, "y": 1000, "frente": "+y", **extra}


def test_item_herda_do_catalogo_e_layout_prevalece(proj):
    cat = carregar_catalogo([proj / "catalogo" / "produtos"])
    assert cat["sofa-teste"].cor_real == "#556B2F"
    arq = _y(proj / "ambientes" / "sala" / "layout.yaml", {"nome": "sala", "moveis": [
        _sofa(), {**_sofa(id="sofa2", x=1500, y=2500), "altura": {"valor": 700, "status": "confirmado",
                                                                   "fonte": "trena"}}]})
    lay = carregar_layout(arq, cat, "sala")
    s1, s2 = lay.moveis
    assert (s1.ambiente, s1.categoria, s1.largura.valor, s1.cor_real) == ("sala", "sofa", 1800, "#556B2F")
    assert s2.altura.valor == 700 and s2.altura.status.value == "confirmado"


def test_produto_fora_do_catalogo_e_ambiente_errado(proj):
    arq = _y(proj / "ambientes" / "sala" / "layout.yaml", {"nome": "s", "moveis": [_sofa(produto="nao-existe")]})
    with pytest.raises(ValueError, match="não está no catálogo"):
        carregar_layout(arq, {}, "sala")
    arq = _y(proj / "ambientes" / "sala" / "layout.yaml", {"nome": "s", "moveis": [_sofa(ambiente="quarto")]})
    with pytest.raises(ValueError, match="arquivo é do ambiente 'sala'"):
        carregar_layout(arq, carregar_catalogo([proj / "catalogo" / "produtos"]), "sala")


def test_layouts_combinados_e_id_repetido(proj):
    cat = carregar_catalogo([proj / "catalogo" / "produtos"])
    _y(proj / "ambientes" / "sala" / "layout.yaml", {"nome": "s", "moveis": [_sofa()]})
    _y(proj / "ambientes" / "quarto" / "layout.yaml", {"nome": "q", "moveis": [_sofa(id="sofa-q", x=1200, y=1200)]})
    lay = carregar_layout_projeto(proj, cat)
    assert {m.ambiente for m in lay.moveis} == {"sala", "quarto"}
    _y(proj / "ambientes" / "quarto" / "layout.yaml", {"nome": "q", "moveis": [_sofa(x=1200, y=1200)]})
    with pytest.raises(ValueError, match="repetido"):
        carregar_layout_projeto(proj, cat)


def test_cena_usa_cor_real_e_conceito_do_ambiente(proj, capsys):
    _y(proj / "ambientes" / "sala" / "layout.yaml", {"nome": "s", "moveis": [_sofa()]})
    _y(proj / "ambientes" / "sala" / "conceito.yaml", {
        "fonte": "teste", "estilo": {"principal": "industrial"},
        "referencias": [{"id": "loft-sala-jantar-01", "biblioteca": "industrial"}],
        "superficies": {"paredes": {"padrao": "off_white"}, "teto": "off_white"},
        "itens": {"sofa": {"cor": "couro_conhaque"}}})
    assert main(["cena", str(proj)]) == 0
    out = capsys.readouterr().out
    assert "AVISO conceito: itens.sofa: produto com cor real" in out
    cena = json.loads((proj / "saidas" / "cena.json").read_text(encoding="utf-8"))
    assert cena["estilo"]["principal"] == "industrial"
    assert cena["moveis"][0]["partes"][0]["acabamento"]["origem"] == "estilo"  # conceito recoloriu (com aviso)
    man = json.loads((proj / "saidas" / "manifest.json").read_text(encoding="utf-8"))["saidas"]["cena.json"]
    assert "projetos/exemplo/ambientes/sala/conceito.yaml" in man["entradas"]
    assert "projetos/exemplo/catalogo/produtos/sofa-teste.yaml" in man["entradas"]


def test_cena_sem_conceito_usa_cor_real_do_produto(proj):
    _y(proj / "ambientes" / "sala" / "layout.yaml", {"nome": "s", "moveis": [_sofa()]})
    assert main(["cena", str(proj)]) == 0
    cena = json.loads((proj / "saidas" / "cena.json").read_text(encoding="utf-8"))
    ac = cena["moveis"][0]["partes"][0]["acabamento"]
    assert (ac["origem"], ac["hex"]) == ("produto", "#556B2F")


def test_conceito_com_referencia_inexistente_falha(proj, capsys):
    _y(proj / "ambientes" / "sala" / "layout.yaml", {"nome": "s", "moveis": [_sofa()]})
    _y(proj / "ambientes" / "sala" / "conceito.yaml", {
        "fonte": "t", "estilo": {"principal": "industrial"}, "referencias": [{"id": "nao-existe"}]})
    assert main(["cena", str(proj)]) == 1
    assert "referencias: 'nao-existe'" in capsys.readouterr().out


def test_status_fases_por_pasta_de_ambiente(proj, capsys):
    (proj / "ambientes" / "quarto").mkdir(parents=True)
    (proj / "ambientes" / "quarto" / "briefing.md").write_text("# Briefing\n", encoding="utf-8")
    _y(proj / "ambientes" / "sala" / "layout.yaml", {"nome": "s", "moveis": [_sofa()]})
    _y(proj / "propostas" / "sala-a" / "layout.yaml", {"nome": "a", "ambiente": "sala", "moveis": []})
    main(["status", str(proj)])
    out = capsys.readouterr().out
    assert "sala               P2b conceito (layout aprovado, conceito pendente)  [1 itens no layout; 1 proposta(s) em aberto]" in out
    assert "quarto             P2b/P2c conceito e layout (briefing feito)" in out
    assert "ambientes/sala/layout.yaml" in out  # sem aprovação registrada com hash
