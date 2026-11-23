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
    assert partes["encosto"]["bbox"] == [0, 680, 200, 2320] and partes["encosto"]["z1"] == 900  # costas em -x, entre os braços
    assert partes["braco-esquerdo"]["bbox"] == [0, 2320, 940, 2470]  # olhando para +x, esquerda = +y
    assert partes["braco-direito"]["bbox"] == [0, 530, 940, 680]
    assert partes["braco-direito"]["z1"] == 650


def test_sofa_em_blocos_e_almofadas_arredondadas(geo):
    sofa = Movel(id="sofa", nome="Sofá", ambiente="sala", categoria="sofa", x=470, y=1500, frente="+x",
                 largura=M(1890), profundidade=M(890), altura=M(720), altura_assento=M(400), blocos_assento=2,
                 prof_encosto=M(300), braco_largura=M(270), braco_altura=M(700), bracos=["esquerdo", "direito"],
                 almofadas_encosto=2)
    partes = {p["parte"]: p for p in gerar_cena(geo, Layout(nome="t", moveis=[sofa]))["moveis"][0]["partes"]}
    assert (partes["assento-1"]["z0"], partes["assento-1"]["z1"], partes["assento-2"]["z1"]) == (0, 200, 400)
    y0, y1 = 1500 - 945, 1500 + 945
    e1, e2 = partes["encosto-1"]["bbox"], partes["encosto-2"]["bbox"]
    from archtools.cena import FOLGA_ALMOFADAS
    assert e1[1] == y0 + 270 and e2[3] == y1 - 270 and e2[1] - e1[3] == FOLGA_ALMOFADAS  # entre os braços
    assert e1[2] - e1[0] == 300 and partes["encosto-1"]["z1"] == 720
    assert partes["braco-direito"]["raio"] == pytest.approx(0.45 * 270)
    assert all(p["raio"] > 0 for p in partes.values())


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


def test_cor_real_por_peca_e_textura(geo):
    cad = Movel(id="cad", nome="Cadeira", ambiente="sala", categoria="cadeira", x=2000, y=1500, frente="+y",
                largura=M(700), profundidade=M(700), altura=M(1290), modelo="cadeira_escritorio",
                cor_real={"estofado": "#6B666F", "estrutura": "#ACA6A9"})
    partes = gerar_cena(geo, Layout(nome="t", moveis=[cad]))["moveis"][0]["partes"]
    est = {pt["material"]: pt["acabamento"] for pt in partes}
    assert est["estofado"]["hex"] == "#6B666F" and est["estofado"]["textura"]["tipo"] == "tecido"
    assert est["estrutura"]["hex"] == "#ACA6A9" and est["estrutura"]["textura"]["tipo"] == "metal"
    sofa = Movel(id="s", nome="s", ambiente="sala", categoria="sofa", x=2000, y=1500, frente="+y",
                 largura=M(1800), profundidade=M(900), altura=M(700), cor_real="#2E2B2A", textura="tecido")
    pt = gerar_cena(geo, Layout(nome="t", moveis=[sofa]))["moveis"][0]["partes"][0]
    assert pt["acabamento"]["hex"] == "#2E2B2A" and pt["acabamento"]["textura"]["tipo"] == "tecido"


def test_cameras_nomeadas_em_coordenadas_locais(geo, tmp_path):
    from archtools.cena import cameras_nomeadas
    f = tmp_path / "cameras.yaml"
    f.write_text("cameras:\n  - {id: sofa, pos: [100, 200, 1100], alvo: [3000, 3000, 900], lente: 16}\n",
                 encoding="utf-8")
    c = cameras_nomeadas(geo, "quarto", f)[0]
    assert c["id"] == "quarto-sofa" and c["lente"] == 16 and c["nomeada"]
    assert c["pos"] == [100, 200, 1100] and c["alvo"] == [3000, 3000, 900]  # quarto do exemplo: sem `posicao`


def test_veio_da_madeira_segue_o_lado_maior():
    from archtools.materiais import orientar_veios, textura
    tex = textura("madeira")
    cena = {"moveis": [{"partes": [{"bbox": [0, 0, 300, 1800], "z0": 0, "z1": 18, "acabamento": {"textura": tex}},
                                   {"bbox": [0, 0, 1800, 300], "z0": 0, "z1": 18, "acabamento": {"textura": tex}},
                                   # porta voltada para x (face no plano x = cte): veio vertical
                                   {"bbox": [0, 0, 18, 450], "z0": 0, "z1": 700, "acabamento": {"textura": tex}}]}]}
    orientar_veios(cena)
    assert [pt["acabamento"]["textura"]["direcao"] for pt in cena["moveis"][0]["partes"]] == ["y", "x", "x"]
    assert tex["direcao"] == "x"  # o preset compartilhado não é alterado


def test_texturas_de_imagem_quando_existem(tmp_path):
    from PIL import Image
    from archtools.materiais import aplicar_imagens, textura
    (tmp_path / "texturas.yaml").write_text(
        "texturas:\n  - {id: madeira_escura, asset: W1, tamanho_mm: 1000, uso: t}\n"
        "  - {id: linho, asset: L1, tamanho_mm: 400, uso: t}\n", encoding="utf-8")
    (tmp_path / "W1").mkdir()
    for suf in ("_Color.jpg", "_Roughness.jpg", "_NormalGL.jpg"):
        Image.new("RGB", (8, 8), (128, 128, 128)).save(tmp_path / "W1" / f"W1_1K-JPG{suf}")
    cena = {"moveis": [{"partes": [
        {"material": None, "acabamento": {"textura": textura("madeira")}},
        {"material": "cortina", "acabamento": {"textura": textura("tecido")}},
        {"material": None, "acabamento": {}}]}], "revestimentos": []}
    faltam = aplicar_imagens(cena, tmp_path)
    p0, p1, p2 = cena["moveis"][0]["partes"]
    assert p0["acabamento"]["textura"]["imagem"]["asset"] == "W1"
    assert p0["acabamento"]["textura"]["imagem"]["media"] == pytest.approx(128 / 255, abs=0.01)
    assert "imagem" not in p1["acabamento"]["textura"] and faltam == ["linho"]  # cortina -> linho, ausente
    assert "textura" not in p2["acabamento"]


def test_sofa_com_armacao_tubular_cromada(geo):
    sofa = Movel(id="sofa", nome="Sofá", ambiente="sala", categoria="sofa", x=470, y=1500, frente="+x",
                 largura=M(1890), profundidade=M(890), altura=M(720), altura_assento=M(400), blocos_assento=2,
                 braco_largura=M(270), braco_altura=M(700), bracos=["esquerdo", "direito"], armacao="tubular")
    partes = gerar_cena(geo, Layout(nome="t", moveis=[sofa]))["moveis"][0]["partes"]
    tubos = [p for p in partes if p.get("material") == "cromado"]
    assert len(tubos) == 2 and all(p["forma"] == "tubo" and len(p["tubo"]["pontos"]) == 4 for p in tubos)  # um laço por lado
    x0, y0, x1, y1 = 470 - 445, 1500 - 945, 470 + 445, 1500 + 945
    assert all(x0 <= p["bbox"][0] and p["bbox"][2] <= x1 and y0 <= p["bbox"][1] and p["bbox"][3] <= y1 for p in tubos)
