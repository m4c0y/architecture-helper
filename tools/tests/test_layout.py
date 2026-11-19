"""Validações de layout sobre o exemplo fictício (sala 4000 x 3500, porta na parede 0)."""

from pathlib import Path

import pytest

from archtools.layout import Layout, Movel, carregar_criterios, validar_layout
from archtools.planta2d import desenhar
from archtools.schema import Medida, carregar_geometria

EXEMPLO = Path(__file__).parent / "fixtures" / "exemplo"


def M(v):
    return Medida(valor=v, status="confirmado", fonte="t")


def movel(id_, x, y, w, d, h=800, frente="+y", elev=0, folga=None, amb="sala"):
    return Movel(id=id_, nome=id_, ambiente=amb, categoria="outro", x=x, y=y, frente=frente,
                 largura=M(w), profundidade=M(d), altura=M(h), elevacao=M(elev), folga_frontal=folga)


@pytest.fixture
def geo():
    g = carregar_geometria(EXEMPLO)
    g.aberturas[1].peitoril = M(1100)  # janela do quarto com peitoril conhecido
    return g


@pytest.fixture
def crit():
    return carregar_criterios(EXEMPLO)


def erros(geo, crit, *moveis):
    return [a for a in validar_layout(geo, Layout(nome="t", moveis=list(moveis)), crit) if a.nivel == "erro"]


def test_layout_valido(geo, crit):
    # mesa encostada na parede do fundo, cadeira para baixo (frente -y)
    assert erros(geo, crit, movel("mesa", 2000, 3150, 1600, 700, frente="-y", folga="atras_cadeira")) == []


def test_fora_do_ambiente(geo, crit):
    assert any("sai do ambiente" in e.mensagem for e in erros(geo, crit, movel("m", 3900, 1500, 600, 600)))


def test_colisao_e_suspenso(geo, crit):
    sofa = movel("sofa", 2000, 1800, 2000, 900, h=850)
    assert any("colidem" in e.mensagem for e in erros(geo, crit, sofa, movel("rack", 2000, 1800, 1000, 400)))
    prateleira = movel("prat", 2000, 1800, 1000, 300, h=40, elev=1800)
    assert erros(geo, crit, sofa, prateleira) == []


def test_gaveteiro_sob_a_mesa(geo, crit):
    # mesa 1600 x 700, h 750 (sem modelo = tampo de 30 + pernas de 50 recuadas 40): x 1200..2800, y 2800..3500
    mesa = movel("mesa", 2000, 3150, 1600, 700, h=750, frente="-y")
    mesa.categoria = "mesa"
    baixo = movel("gav", 2000, 3150, 450, 500, h=700, frente="-y")        # sob o tampo, longe das pernas
    assert not any("colidem" in e.mensagem for e in erros(geo, crit, mesa, baixo))
    alto = movel("gav", 2000, 3150, 450, 500, h=730, frente="-y")         # encosta no tampo (720..750)
    assert any("colidem" in e.mensagem for e in erros(geo, crit, mesa, alto))
    na_perna = movel("gav", 1200 + 40 + 200, 3150 + 350 - 40 - 200, 450, 500, h=700, frente="-y")  # cobre uma perna
    assert any("colidem" in e.mensagem for e in erros(geo, crit, mesa, na_perna))


def test_folga_invadida(geo, crit):
    mesa = movel("mesa", 2000, 3150, 1600, 700, frente="-y", folga="atras_cadeira")
    caixa = movel("caixa", 2000, 2500, 400, 400)
    es = erros(geo, crit, mesa, caixa)
    assert any("invadida por 'caixa'" in e.mensagem for e in es)


def test_colisao_pequena_e_detectada_mas_encosto_nao(geo, crit):
    a = movel("a", 1000, 1000, 1000, 1000)          # x 500..1500
    b = movel("b", 1500 + 35, 1000, 100, 90)         # sobrepõe 15 mm em x -> colisão real
    assert any("colidem" in e.mensagem for e in erros(geo, crit, a, b))
    c = movel("c", 1500 + 50, 1000, 100, 90)         # encostado (0 mm) -> ok
    assert not any("colidem" in e.mensagem for e in erros(geo, crit, a, c))


def test_folga_estreita_centrada(geo, crit):
    mesa = movel("mesa", 2000, 3150, 1600, 700, frente="-y", folga="atras_cadeira")
    caixa = movel("caixa", 1350, 2500, 300, 300)  # x 1200..1500: atrás da ponta da mesa, fora do centro
    assert any("invadida" in e.mensagem for e in erros(geo, crit, mesa, caixa))
    mesa.folga_largura = 900  # cadeira no meio: folga x 1550..2450
    assert not any("invadida" in e.mensagem for e in erros(geo, crit, mesa, caixa))


def test_cadeira_associada_ocupa_folga_da_mesa(geo, crit):
    mesa = movel("mesa", 2000, 3150, 1600, 700, frente="-y", folga="atras_cadeira")
    cad = Movel(id="cad", nome="cad", ambiente="sala", categoria="cadeira", x=2000, y=2450, frente="+y",
                largura=M(680), profundidade=M(680), altura=M(1250))
    assert any("invadida" in e.mensagem for e in erros(geo, crit, mesa, cad)) is False  # cadeira não bloqueia
    outro = movel("caixa", 2000, 2450, 680, 680)  # um móvel comum no mesmo lugar invade
    assert any("invadida" in e.mensagem for e in erros(geo, crit, mesa, outro))


def test_giro_da_porta(geo, crit):
    # porta-sala: parede 0, de x=300 a 1100, dobradiça no início, abre para dentro
    assert any("giro da porta" in e.mensagem for e in erros(geo, crit, movel("m", 600, 400, 400, 400)))


def test_frente_inacessivel(geo, crit):
    barreira = movel("barreira", 2000, 1500, 4000, 200)  # parede de móveis cortando a sala
    mesa = movel("mesa", 2000, 3150, 1600, 700, frente="-y", folga="atras_cadeira")
    assert any("inacessível" in e.mensagem for e in erros(geo, crit, barreira, mesa))


def test_aviso_janela(geo, crit):
    # quarto (vértices globais 4150..7150): janela na parede 2 (topo, y=3000), x 5050..6250
    estante = movel("estante", 5650, 2800, 800, 400, h=1900, frente="-y", amb="quarto")
    achados = validar_layout(geo, Layout(nome="t", moveis=[estante]), crit)
    assert any(a.nivel == "aviso" and "janela-quarto" in a.mensagem for a in achados)


def test_planta_com_layout(geo, crit, tmp_path):
    lay = Layout(nome="t", moveis=[movel("mesa", 2000, 3150, 1600, 700, frente="-y", folga="atras_cadeira")])
    saidas = desenhar(geo, tmp_path, lay, crit, recorte="sala", nome="x")
    assert all(p.exists() for p in saidas)
