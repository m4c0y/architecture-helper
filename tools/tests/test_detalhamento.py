"""Fase P4: detalhamento.yaml troca só o modelo 3D de itens aprovados."""

from archtools.detalhamento import aplicar_detalhamento
from archtools.layout import Layout, Movel
from archtools.schema import Medida
from archtools.status import fase_ambiente


def M(v):
    return Medida(valor=v, status="estimado", fonte="t")


def _layout():
    return Layout(nome="t", moveis=[Movel(id="rack", nome="Rack", ambiente="sala", categoria="aparador", x=1000,
                                          y=1000, frente="+y", largura=M(1200), profundidade=M(400), altura=M(600))])


def test_troca_o_modelo_e_aponta_erros(tmp_path):
    d = tmp_path / "ambientes" / "sala"
    d.mkdir(parents=True)
    (d / "detalhamento.yaml").write_text("itens:\n  rack: {modelo: rack_vinis}\n  fantasma: {modelo: tapete}\n",
                                         encoding="utf-8")
    lay = _layout()
    usados, erros = aplicar_detalhamento(lay, tmp_path)
    assert lay.moveis[0].modelo == "rack_vinis" and lay.moveis[0].largura.valor == 1200  # medidas intactas
    assert usados == [d / "detalhamento.yaml"] and len(erros) == 1 and "fantasma" in erros[0]


def test_modelo_inexistente_e_erro(tmp_path):
    d = tmp_path / "ambientes" / "sala"
    d.mkdir(parents=True)
    (d / "detalhamento.yaml").write_text("itens:\n  rack: {modelo: nao_existe}\n", encoding="utf-8")
    _, erros = aplicar_detalhamento(_layout(), tmp_path)
    assert "não existe" in erros[0]


def test_fase_p4():
    assert fase_ambiente(True, True, True, True) == "P4 detalhamento"
    assert fase_ambiente(True, True, True, False) == "P3 preview e refinamento"
    assert fase_ambiente(True, True, True, True, True) == "P5 render final"
