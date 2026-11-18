"""Passo 1 do roteiro: materiais explícitos no cena.json, manifestos, decisões com hash e status."""

import json
import shutil
from pathlib import Path

import pytest

from archtools.cena import gerar_cena
from archtools.cli import main
from archtools.decisoes import aprovacoes, bloco_aprovacao, carregar
from archtools.manifesto import hash_arquivo, registrar, verificar
from archtools.materiais import NEUTRO, neutros
from archtools.schema import carregar_geometria

EXEMPLO = Path(__file__).parent / "fixtures" / "exemplo"


@pytest.fixture
def proj(tmp_path, monkeypatch):
    """Cópia do projeto de exemplo; o cwd vira tmp_path (manifestos usam caminhos relativos)."""
    destino = tmp_path / "projetos" / "exemplo"
    shutil.copytree(EXEMPLO, destino)
    monkeypatch.chdir(tmp_path)
    return Path("projetos/exemplo")


# ------------------------------------------------------------------ materiais

def test_toda_superficie_tem_acabamento_e_nao_ha_cor_inventada():
    cena = gerar_cena(carregar_geometria(EXEMPLO))
    for grupo in ("paredes", "vidros", "pisos", "tetos", "cercamentos"):
        for item in cena[grupo]:
            assert item["acabamento"]["origem"] == "neutro", (grupo, item["id"])
    assert any("tons neutros" in s for s in cena["suposicoes"])


def test_movel_sem_produto_vai_neutro_e_entra_no_relatorio():
    from archtools.layout import Layout
    lay = Layout.model_validate({"nome": "t", "moveis": [{
        "id": "sofa", "nome": "Sofá", "ambiente": "sala", "categoria": "sofa", "x": 1500, "y": 1000, "frente": "+y",
        "largura": {"valor": 2000, "status": "estimado", "fonte": "t"},
        "profundidade": {"valor": 900, "status": "estimado", "fonte": "t"},
        "altura": {"valor": 800, "status": "estimado", "fonte": "t"}}]})
    geo = carregar_geometria(EXEMPLO)
    if "sala" not in {a.id for a in geo.ambientes}:
        pytest.skip("fixture sem ambiente 'sala'")
    cena = gerar_cena(geo, lay)
    assert cena["moveis"][0]["partes"][0]["acabamento"]["origem"] == "neutro"
    assert neutros(cena) == ["sofa"]


def test_cinza_de_marcacao_nao_e_cor_de_paleta():
    assert NEUTRO["origem"] == "neutro" and NEUTRO["hex"].startswith("#")


def test_blender_nao_tem_tabela_de_cores():
    script = (Path(__file__).parents[2] / "blender" / "construir_cena.py").read_text(encoding="utf-8")
    assert "CORES = {" not in script and "ACABAMENTO = {" not in script


# ------------------------------------------------------------------ manifestos

def test_hash_ignora_crlf(tmp_path):
    a, b = tmp_path / "a.yaml", tmp_path / "b.yaml"
    a.write_bytes(b"x: 1\r\ny: 2\r\n")
    b.write_bytes(b"x: 1\ny: 2\n")
    assert hash_arquivo(a) == hash_arquivo(b)


def test_saida_fica_desatualizada_em_cadeia(proj):
    saidas = proj / "saidas"
    saidas.mkdir()
    geo = proj / "geometria.yaml"
    cena = saidas / "cena.json"
    cena.write_text("{}", encoding="utf-8")
    registrar(saidas, [cena], [geo], "teste")
    (saidas / "3d").mkdir()
    png = saidas / "3d" / "vista.png"
    png.write_bytes(b"png")
    registrar(saidas / "3d", [png], [cena], "teste")
    (saidas / "3d" / "sobra.png").write_bytes(b"velho")

    estado = {s.arquivo: s for s in verificar(proj)}
    assert estado["projetos/exemplo/saidas/cena.json"].estado == "ok"
    assert estado["projetos/exemplo/saidas/3d/vista.png"].estado == "ok"
    assert estado["projetos/exemplo/saidas/3d/sobra.png"].estado == "sem_manifesto"

    geo.write_text(geo.read_text(encoding="utf-8") + "\n# mudou\n", encoding="utf-8")
    estado = {s.arquivo: s for s in verificar(proj)}
    assert estado["projetos/exemplo/saidas/cena.json"].estado == "desatualizada"
    vista = estado["projetos/exemplo/saidas/3d/vista.png"]
    assert vista.estado == "desatualizada" and "cena.json está desatualizada" in vista.motivos[0]


def test_comandos_gravam_manifesto(proj):
    assert main(["planta", str(proj)]) == 0
    man = json.loads((proj / "saidas" / "manifest.json").read_text(encoding="utf-8"))
    info = man["saidas"]["planta.png"]
    assert "projetos/exemplo/geometria.yaml" in info["entradas"]
    assert info["comando"].startswith("archtools planta")
    assert main(["cena", str(proj)]) == 0
    man = json.loads((proj / "saidas" / "manifest.json").read_text(encoding="utf-8"))
    assert "cena.json" in man["saidas"]


# ------------------------------------------------------------------ decisões e status

def _decisao(proj, nome, texto):
    (proj / "decisoes").mkdir(exist_ok=True)
    (proj / "decisoes" / nome).write_text(texto, encoding="utf-8")


def test_decisao_antiga_le_estado_do_texto(proj):
    _decisao(proj, "0001-a.md", "# 0001 — A\n\n- **Estado:** aceita (substitui 0000)\n")
    _decisao(proj, "0002-b.md", "# 0002 — B\n\n- **Estado:** substituída por 0003\n")
    decs = carregar(proj)
    assert [d.estado for d in decs] == ["aceita", "substituida"]
    assert all(d.cabecalho is None for d in decs)


def test_aprovacao_detecta_alteracao_sem_decisao(proj):
    cab = bloco_aprovacao(proj, "0001", ["geometria.yaml"])
    _decisao(proj, "0001-geo.md", cab + "# 0001 — Geometria\n")
    assert [a.estado for a in aprovacoes(proj, carregar(proj))] == ["ok"]
    g = proj / "geometria.yaml"
    g.write_text(g.read_text(encoding="utf-8") + "\n# editado\n", encoding="utf-8")
    assert [a.estado for a in aprovacoes(proj, carregar(proj))] == ["alterado"]


def test_status_e_aprovacao_pela_cli(proj, capsys):
    assert main(["pendencias", str(proj)]) == 0
    capsys.readouterr()
    assert main(["aprovacao", str(proj), "--arquivos", "geometria.yaml"]) == 0
    cab = capsys.readouterr().out
    assert cab.startswith("---\nnumero: '0001'") and "sha256:" in cab
    _decisao(proj, "0001-geo.md", cab + "# 0001 — Geometria\n")
    assert main(["status", str(proj)]) == 0
    out = capsys.readouterr().out
    assert "OK        geometria.yaml (decisão 0001)" in out
    assert "pendencias.md em dia" in out
    assert "P2a briefing" in out
