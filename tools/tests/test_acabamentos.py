"""Acabamentos/luzes de uma proposta de estilo aplicados ao cena.json (exemplo fictício)."""

from pathlib import Path

import pytest

from archtools.acabamentos import (Acabamentos, aplicar_acabamentos, hex_para_linear, kelvin_para_linear,
                                   validar_acabamentos)
from archtools.cena import gerar_cena
from archtools.estilo import Arquiteto, Escolha, resolver
from archtools.layout import Layout, Movel
from archtools.schema import Medida, carregar_geometria

EXEMPLO = Path(__file__).parent / "fixtures" / "exemplo"


def M(v):
    return Medida(valor=v, status="estimado", fonte="t")


def arq(id_, cores, luminarias=(), evitar_tags=(), k_tarefa=3500):
    return Arquiteto.model_validate({
        "id": id_, "nome": id_, "estilo": id_, "estado": "rascunho", "fonte": "t", "resumo": "r",
        "paleta": [{"id": c, "nome": c, "hex": hx, "papel": p, "uso": "u", "tags": t} for c, hx, p, t in cores],
        "materiais": [],
        "iluminacao": {"temperatura_k": {"geral": 2700, "tarefa": k_tarefa}, "estrategia": "e"},
        "luminarias": [{"id": lid, "tipo": tp, "descricao": "d", "temperatura_k": k, "tags": t}
                       for lid, tp, k, t in luminarias],
        "regras": {"fazer": [], "evitar": [], "evitar_tags": list(evitar_tags)},
    })


@pytest.fixture
def ctx():
    geo = carregar_geometria(EXEMPLO)
    a = arq("a", [("branco", "#FFFFFF", "base", []), ("verde", "#2F4A3A", "apoio", [])],
            luminarias=[("globo", "pendente", 2700, []), ("mesa", "mesa", 4000, [])], evitar_tags=["latao"])
    b = arq("b", [("creme", "#EFE6D2", "base", []), ("latao", "#B08D57", "destaque", ["latao"]),
                  ("mostarda", "#C9962B", "destaque", [])])
    r = resolver({"a": a, "b": b}, "sala", Escolha(principal="a", acentos=["b"]))
    layout = Layout(nome="t", moveis=[
        Movel(id="sofa", nome="Sofá", ambiente="sala", categoria="sofa", x=500, y=1500, frente="+x",
              largura=M(2000), profundidade=M(900), altura=M(850)),
        Movel(id="pend", nome="Pendente", ambiente="sala", categoria="outro", x=2000, y=1750, frente="+y",
              largura=M(300), profundidade=M(300), altura=M(300), elevacao=M(2100), modelo="pendente_esfera"),
        Movel(id="lmesa", nome="Luminária", ambiente="sala", categoria="outro", x=3000, y=3000, frente="-y",
              largura=M(150), profundidade=M(150), altura=M(450), modelo="luminaria_articulada"),
    ])
    return geo, r, gerar_cena(geo, layout)


def acab(**kw):
    base = {"ambiente": "sala", "fonte": "teste", "paredes": {"padrao": "branco", "1": "verde"}, "teto": "branco",
            "moveis": {"sofa": {"cor": "mostarda"}, "pend": {"cor": "branco"}},
            "luzes": {"pend": {"luminaria": "globo", "intensidade_w": 40},
                      "lmesa": {"luminaria": "mesa", "camada": "tarefa", "tipo": "spot", "intensidade_w": 20}}}
    base.update(kw)
    return Acabamentos.model_validate(base)


def test_conversoes_de_cor():
    assert hex_para_linear("#FFFFFF") == [1.0, 1.0, 1.0, 1.0]
    assert hex_para_linear("#000000") == [0.0, 0.0, 0.0, 1.0]
    r, g, b = kelvin_para_linear(2700)
    assert r == 1.0 and r > g > b  # luz quente
    r, g, b = kelvin_para_linear(6500)
    assert min(r, g, b) > 0.85  # ~branco


def test_valido_sem_erros(ctx):
    geo, r, cena = ctx
    assert validar_acabamentos(acab(), r, geo, cena) == []


def test_erros_de_validacao(ctx):
    geo, r, cena = ctx
    a = acab(paredes={"padrao": "latao", "9": "branco"}, teto="roxo",
             moveis={"fantasma": {"cor": "branco"}, "pend": {"pecas": {"madeira": "branco"}}},
             luzes={"pend": {"luminaria": "arco", "intensidade_w": 10}})
    erros = "\n".join(validar_acabamentos(a, r, geo, cena))
    assert "'latao' foi excluída por conflito" in erros
    assert "'9' não é 'padrao' nem índice" in erros
    assert "'roxo' não está na paleta" in erros
    assert "moveis.fantasma: não existe" in erros
    assert "'madeira' não é material" in erros
    assert "luminária 'arco' não está no estilo" in erros


def test_paineis_de_pintura_por_parede(ctx):
    geo, r, cena = ctx
    aplicar_acabamentos(cena, acab(), r, geo)
    pinturas = {rv["id"]: rv for rv in cena["revestimentos"] if rv["id"].startswith("pintura-sala")}
    assert len(pinturas) == 4  # sala retangular
    assert pinturas["pintura-sala-1"]["cor_id"] == "verde"
    assert pinturas["pintura-sala-0"]["cor_id"] == "branco" and pinturas["pintura-sala-0"]["recortar"]
    # painel fica DENTRO da sala (0..4000 x 0..3500)
    xs = [x for anel in pinturas["pintura-sala-1"]["aneis"] for x, _ in anel]
    assert 3990 < min(xs) and max(xs) < 4000
    assert any(rv["id"] == "teto-sala" for rv in cena["revestimentos"])


def test_moveis_e_luzes(ctx):
    geo, r, cena = ctx
    aplicar_acabamentos(cena, acab(), r, geo)
    sofa = next(m for m in cena["moveis"] if m["id"] == "sofa")
    assert all(p["acabamento"]["cor_id"] == "mostarda" for p in sofa["partes"])
    luzes = {lz["movel"]: lz for lz in cena["luzes"]}
    assert luzes["pend"]["pos"][2] == pytest.approx(2250)  # centro da esfera (2100..2400)
    assert luzes["pend"]["temperatura_k"] == 2700 and luzes["pend"]["emissor"]
    assert luzes["pend"]["origem"] == "a"
    # camada 'tarefa' do principal (3500 K) prevalece sobre os 4000 K da luminária
    assert luzes["lmesa"]["temperatura_k"] == 3500 and luzes["lmesa"]["tipo"] == "spot"
    pend = next(m for m in cena["moveis"] if m["id"] == "pend")
    assert pend["partes"][-1]["z1"] == cena["pe_direito"]  # fio até a laje
    assert cena["estilo"]["principal"] == "a"
