"""Modelos paramétricos de produtos: peças dentro da pegada e orientação correta."""

import pytest

from archtools.modelos import MODELOS, para_global

BB = [1000, 2000, 1400, 3500]  # pegada 400 (x) x 1500 (y)


@pytest.mark.parametrize("nome,dims", [("estante_industrial", (800, 400, 1900)),
                                       ("frigobar_retro", (480, 550, 820)),
                                       ("rack_vinil_norvege", (1500, 400, 780)),
                                       ("vaso_planta", (500, 500, 1200)),
                                       ("monitor_ultrawide", (810, 250, 485)),
                                       ("cadeira_escritorio", (680, 680, 1250)),
                                       ("tapete", (2000, 1400, 10)), ("quadro", (600, 30, 800)),
                                       ("livros", (700, 220, 240)), ("almofada", (450, 150, 450)),
                                       ("cortina", (1400, 120, 1600)),
                                       ("armario_aereo", (1800, 350, 700)),
                                       ("toca_discos", (450, 350, 130)), ("caixa_som", (180, 220, 300)),
                                       ("cacto", (150, 150, 400)), ("persiana_romana", (1300, 50, 600)),
                                       ("rack_vinis", (1200, 400, 600)), ("tv_parede", (1230, 60, 710)),
                                       ("monstera", (500, 500, 1200)),
                                       ("porta_celeiro", (800, 40, 2240)), ("pegboard", (600, 150, 600))])
def test_pecas_dentro_da_caixa(nome, dims):
    w, d, h = dims
    for p in MODELOS[nome](w, d, h):
        assert -40 <= p["u"][0] <= p["u"][1] <= w + 1e-6
        assert -40 <= p["v"][0] <= p["v"][1] <= d + 1e-6  # frente pode avançar puxadores/portas
        assert 0 <= p["z"][0] <= p["z"][1] <= h + 1e-6


def test_mapeamento_das_frentes():
    peca = {"u": [0, 100], "v": [0, 50], "z": [0, 10], "material": "x"}  # canto frontal-esquerdo
    # frente -x (móvel na parede +x, olhado de oeste): esquerda de quem olha = +y, frente = x0
    assert para_global(peca, "-x", BB, 0)["bbox"] == [1000, 3400, 1050, 3500]
    # frente +x: esquerda = -y, frente = x1
    assert para_global(peca, "+x", BB, 0)["bbox"] == [1350, 2000, 1400, 2100]
    # frente -y: esquerda = -x, frente = y0
    assert para_global(peca, "-y", BB, 0)["bbox"] == [1000, 2000, 1100, 2050]
    # frente +y: esquerda = +x, frente = y1
    assert para_global(peca, "+y", BB, 0)["bbox"] == [1300, 3450, 1400, 3500]


def test_formas_redondas_preservadas():
    pecas = [para_global(p, "-y", BB, 0) for p in MODELOS["vaso_planta"](500, 500, 1200)]
    assert {p["forma"] for p in pecas} == {"cilindro", "esfera"}


def test_rack_gaveta_a_esquerda_e_pes():
    pecas = MODELOS["rack_vinil_norvege"](1500, 400, 780)
    pes = [p for p in pecas if p["material"] == "madeira_pes"]
    assert len(pes) == 6 and all(p["z"] == [0, 179] for p in pes)
    frente_gaveta = [p for p in pecas if p["material"] == "nogueira" and p["v"][1] == 0 and p["u"][1] <= 750]
    assert frente_gaveta, "gaveta deve ficar na metade esquerda"


def test_superficies_de_apoio_da_estante():
    from archtools.modelos import superficies_apoio
    niveis = superficies_apoio("estante_industrial", 800, 400, 1800)
    pecas = MODELOS["estante_industrial"](800, 400, 1800)
    topos = sorted(p["z"][1] for p in pecas if p["material"] == "madeira_clara")
    assert niveis == topos and len(niveis) == 5
    assert superficies_apoio(None, 1200, 400, 600) == [600]


def test_livros_preenchem_sem_passar_da_largura():
    pecas = MODELOS["livros"](700, 220, 240)
    assert len(pecas) > 15 and max(p["u"][1] for p in pecas) <= 700
    assert {p["material"] for p in pecas} == {"livro_a", "livro_b", "livro_c"}


def test_armario_aereo_portas_e_cava():
    pecas = MODELOS["armario_aereo"](1800, 350, 700)
    portas = sorted((p for p in pecas if p["material"] == "porta"), key=lambda p: p["u"][0])
    assert len(portas) == 4 and portas[0]["u"][0] == 0 and portas[-1]["u"][1] == pytest.approx(1800)
    assert portas[1]["u"][0] - portas[0]["u"][1] == pytest.approx(3)  # friso
    assert all(p["z"] == [30, 700] for p in portas)  # cava de 30 mm por baixo


def test_planta_pendente_desce_pela_frente():
    from archtools.modelos import PENDENTE_QUEDA
    pecas = MODELOS["planta_pendente"](250, 250, 300)
    ramos = [p for p in pecas if p["z"][0] < 0]
    abaixo = [pt for p in ramos if p["forma"] == "tubo" for pt in p["tubo"]["pontos"] if pt[2] < 0]
    abaixo += [p["v"][1] and [0, p["v"][1], -1] for p in ramos if p["forma"] != "tubo"]
    assert ramos and all(pt[1] <= 0 for pt in abaixo)  # abaixo do apoio, só à frente dele (não atravessa)
    folhas = [p for p in pecas if p["forma"] == "folha"]
    assert len(folhas) > 40 and all(len(p["folha"]["rot"]) == 3 for p in folhas)
    assert MODELOS["planta_pendente"](250, 250, 300) == pecas  # semente fixa: mesma planta
    assert min(p["z"][0] for p in ramos) >= -PENDENTE_QUEDA * 300 - 1e-6
    assert len(ramos) > 10  # fios com folhas espaçadas, não um bloco único


def test_rack_vinis_tem_capas_dentro_dos_nichos():
    pecas = MODELOS["rack_vinis"](1200, 400, 600)
    capas = [p for p in pecas if p["material"].startswith("disco_")]
    assert len(capas) > 100 and all(p["z"][1] <= 600 - 18 for p in capas)


def test_folha_gira_com_a_frente_do_movel():
    from archtools.modelos import para_global
    folha = {"u": [98, 102], "v": [-2, 2], "z": [48, 52], "material": "folhagem", "forma": "folha",
             "folha": {"base": [100, 0, 50], "tam": [40, 60], "rot": [-120.0, 0.0, 10.0]}}
    g = para_global(folha, "+x", BB, 1000)
    assert g["folha"]["rot"] == [-120.0, 0.0, 100.0] and g["folha"]["base"][2] == 1050
    x0, y0, x1, y1 = BB
    assert g["folha"]["base"][:2] == [x1, y0 + 100]  # frente +x: u -> +y, v = 0 na face x1
