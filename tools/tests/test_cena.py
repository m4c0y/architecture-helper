"""Exportação da cena 3D (cena.json) sobre o exemplo fictício."""

import json
from pathlib import Path

import pytest
from shapely.geometry import Polygon
from shapely.ops import unary_union

from archtools.cena import ESPESSURA_EXTERNA, cameras_ambiente, gerar_cena
from archtools.layout import Layout, Movel
from archtools.schema import Medida, carregar_geometria

EXEMPLO = Path(__file__).parent / "fixtures" / "exemplo"


def M(v):
    return Medida(valor=v, status="confirmado", fonte="t")


@pytest.fixture
def geo():
    g = carregar_geometria(EXEMPLO)
    g.aberturas[1].peitoril = M(1100)
    return g


def mesa():
    return Movel(id="mesa", nome="Mesa", ambiente="sala", categoria="mesa", x=2000, y=3150, frente="-y",
                 largura=M(1600), profundidade=M(700), altura=M(750))


def test_paredes_cobrem_envoltoria_menos_ambientes(geo):
    cena = gerar_cena(geo)
    area_tris = sum(Polygon(t).area for p in cena["paredes"] for t in p["tris"])
    # sala 4000x3500 e quarto 3000x3000 separados por 150 -> envoltória com paredes de 150
    salas = unary_union([Polygon([(0, 0), (4000, 0), (4000, 3500), (0, 3500)]),
                         Polygon([(4150, 0), (7150, 0), (7150, 3000), (4150, 3000)])])
    esperado = salas.buffer(ESPESSURA_EXTERNA, join_style="mitre").difference(salas).area
    assert area_tris == pytest.approx(esperado, rel=1e-6)
    assert all(p["z1"] == 2600 for p in cena["paredes"])  # pé-direito do exemplo


def test_recortes_e_vidros(geo):
    cena = gerar_cena(geo)
    ids = {r["id"]: r for r in cena["recortes"]}
    assert set(ids) == {"porta-sala", "janela-quarto"}
    assert ids["janela-quarto"]["z0"] == 1100 and ids["janela-quarto"]["z1"] == 2300
    assert ids["porta-sala"]["z0"] == 0 and ids["porta-sala"]["z1"] == 2100
    assert [v["id"] for v in cena["vidros"]] == ["vidro-janela-quarto"]


def test_mesa_vira_tampo_e_pernas(geo):
    cena = gerar_cena(geo, Layout(nome="t", moveis=[mesa()]))
    partes = cena["moveis"][0]["partes"]
    assert len(partes) == 5
    assert partes[0]["z0"] == 720 and partes[0]["z1"] == 750


def test_sofa_em_partes(geo):
    sofa = Movel(id="sofa", nome="Sofá", ambiente="sala", categoria="sofa", x=470, y=1500, frente="+x",
                 largura=M(1940), profundidade=M(940), altura=M(900),
                 altura_assento=M(460), prof_encosto=M(200), braco_largura=M(150), braco_altura=M(650),
                 bracos=["esquerdo", "direito"])
    partes = {p["parte"]: p for p in gerar_cena(geo, Layout(nome="t", moveis=[sofa]))["moveis"][0]["partes"]}
    # pegada: x 0..940, y 530..2470
    assert partes["assento"]["bbox"] == [0, 530, 940, 2470] and partes["assento"]["z1"] == 460
    assert partes["encosto"]["bbox"] == [0, 530, 200, 2470] and partes["encosto"]["z1"] == 900  # costas em -x
    assert partes["braco-esquerdo"]["bbox"] == [0, 2320, 940, 2470]  # olhando para +x, esquerda = +y
    assert partes["braco-direito"]["bbox"] == [0, 530, 940, 680]
    assert partes["braco-direito"]["z1"] == 650


def test_sofa_sem_forma_continua_caixa(geo):
    s = Movel(id="s", nome="S", ambiente="sala", categoria="sofa", x=1000, y=1000, frente="+x",
              largura=M(800), profundidade=M(700), altura=M(460))
    assert len(gerar_cena(geo, Layout(nome="t", moveis=[s]))["moveis"][0]["partes"]) == 1


def test_camera_sai_de_dentro_do_movel(geo):
    cena = gerar_cena(geo, Layout(nome="t", moveis=[
        Movel(id="armario", nome="A", ambiente="sala", categoria="armario", x=300, y=300, frente="+y",
              largura=M(600), profundidade=M(600), altura=M(2000))]))
    cams = {c["id"]: c for c in cameras_ambiente(geo, "sala", moveis=cena["moveis"])}
    x, y, _ = cams["sala-so"]["pos"]
    assert x > 700 and y > 700  # avançou pela diagonal para fora do armário
    assert "sala-planta" in cams


def test_cena_serializa_em_json(geo):
    json.dumps(gerar_cena(geo, Layout(nome="t", moveis=[mesa()])))
