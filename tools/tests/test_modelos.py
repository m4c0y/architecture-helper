"""Modelos paramétricos de produtos: peças dentro da pegada e orientação correta."""

import pytest

from archtools.modelos import MODELOS, para_global

BB = [1000, 2000, 1400, 3500]  # pegada 400 (x) x 1500 (y)


@pytest.mark.parametrize("nome,dims", [("estante_industrial", (800, 400, 1900)),
                                       ("frigobar_retro", (480, 550, 820)),
                                       ("rack_vinil_norvege", (1500, 400, 780)),
                                       ("vaso_planta", (500, 500, 1200)),
                                       ("monitor_ultrawide", (810, 250, 485)),
                                       ("cadeira_escritorio", (680, 680, 1250))])
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
