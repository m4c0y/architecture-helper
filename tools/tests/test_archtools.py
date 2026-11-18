from pathlib import Path

import pytest
from pydantic import ValidationError

from archtools.geometria import area_m2, paredes
from archtools.planta2d import desenhar
from archtools.relatorios import pendencias, quadro_areas
from archtools.schema import Geometria, Medida, Status, carregar_geometria
from archtools.validacao import validar

EXEMPLO = Path(__file__).parent / "fixtures" / "exemplo"


@pytest.fixture
def geo() -> Geometria:
    return carregar_geometria(EXEMPLO)


def _niveis(achados, nivel):
    return [a for a in achados if a.nivel == nivel]


# --- esquema: proíbe inventar medidas


def test_desconhecido_nao_aceita_valor():
    with pytest.raises(ValidationError):
        Medida(valor=2600, status="desconhecido")


def test_confirmado_exige_valor_e_fonte():
    with pytest.raises(ValidationError):
        Medida(valor=None, status="confirmado", fonte="x")
    with pytest.raises(ValidationError):
        Medida(valor=2600, status="confirmado")


def test_campo_desconhecido_no_yaml_e_rejeitado(geo):
    dados = geo.model_dump()
    dados["campo_inventado"] = 1
    with pytest.raises(ValidationError):
        Geometria.model_validate(dados)


# --- cálculos com propagação de status


def test_area_confirmada(geo):
    a = area_m2(geo.ambientes[0])
    assert a.valor == pytest.approx(14.0)
    assert a.status is Status.confirmado


def test_area_herda_status_estimado(geo):
    a = area_m2(geo.ambientes[1])
    assert a.valor == pytest.approx(9.0)
    assert a.status is Status.estimado


def test_comprimento_parede(geo):
    ps = paredes(geo.ambientes[0])
    assert [p.comprimento.valor for p in ps] == [4000, 3500, 4000, 3500]


# --- validações


def test_exemplo_sem_erros(geo):
    achados = validar(geo)
    assert _niveis(achados, "erro") == []
    # peitoril desconhecido torna a altura da janela não verificável
    assert any("janela-quarto" in a.onde for a in _niveis(achados, "nao_verificavel"))


def test_abertura_maior_que_parede(geo):
    geo.aberturas[0].largura = Medida(valor=4000, status="confirmado", fonte="t")
    erros = _niveis(validar(geo), "erro")
    assert any("ultrapassa a parede" in e.mensagem for e in erros)


def test_ambientes_sobrepostos(geo):
    geo.ambientes[1].vertices[0].x = 3000
    geo.ambientes[1].vertices[3].x = 3000
    erros = _niveis(validar(geo), "erro")
    # quarto tem vértices estimados → o achado herda 'estimado'
    assert any("sobrepõem-se" in e.mensagem and e.base is Status.estimado for e in erros)


def test_porta_acima_do_pe_direito(geo):
    geo.aberturas[0].altura = Medida(valor=2700, status="confirmado", fonte="t")
    assert any("pé-direito" in e.mensagem for e in _niveis(validar(geo), "erro"))


def test_ponto_fixo_fora_do_ambiente(geo):
    geo.pontos_fixos[0].posicao.x = 9000
    erros = _niveis(validar(geo), "erro")
    assert any("tomada-1" in e.onde and e.base is Status.estimado for e in erros)


def test_parede_inexistente(geo):
    geo.aberturas[0].parede = 9
    assert any("parede 9" in e.mensagem for e in _niveis(validar(geo), "erro"))


def test_projeto_vazio_nao_quebra():
    geo = Geometria(projeto="vazio", origem="x",
                    pe_direito_padrao=Medida(status="desconhecido"))
    achados = validar(geo)
    assert _niveis(achados, "erro") == []
    assert "Total" not in quadro_areas(geo)


# --- posição do ambiente separada das dimensões internas


def _quarto_relativo(geo, status_pos="estimado"):
    """Reescreve o quarto com posicao + vértices relativos, todos confirmados."""
    from archtools.schema import Ponto
    q = geo.ambientes[1]
    q.posicao = Ponto(x=4150, y=0, status=status_pos, fonte="t")
    q.vertices = [Ponto(x=x, y=y, status="confirmado", fonte="t")
                  for x, y in [(0, 0), (3000, 0), (3000, 3000), (0, 3000)]]
    return q


def test_posicao_estimada_nao_rebaixa_area(geo):
    from archtools.geometria import poligono_global
    q = _quarto_relativo(geo)
    assert area_m2(q).status is Status.confirmado
    pol, st = poligono_global(q)
    assert st is Status.estimado
    assert pol.bounds == (4150, 0, 7150, 3000)


def test_sobreposicao_herda_status_da_posicao(geo):
    q = _quarto_relativo(geo)
    q.posicao.x = 3000
    erros = _niveis(validar(geo), "erro")
    assert any("sobrepõem-se" in e.mensagem and e.base is Status.estimado for e in erros)


def test_posicao_desconhecida_e_nao_verificavel(geo):
    from archtools.schema import Ponto
    q = _quarto_relativo(geo)
    q.posicao = Ponto(status="desconhecido")
    achados = validar(geo)
    assert any(a.onde == "ambiente 'quarto'" and "posição" in a.mensagem
               for a in _niveis(achados, "nao_verificavel"))
    assert area_m2(q).valor == pytest.approx(9.0)


def test_ponto_fixo_relativo_ao_ambiente(geo):
    from archtools.schema import PontoFixo, Ponto
    _quarto_relativo(geo)
    geo.pontos_fixos.append(PontoFixo(id="t-q", tipo="tomada", ambiente="quarto",
                                      posicao=Ponto(x=100, y=0, status="confirmado", fonte="t")))
    assert not any("t-q" in e.onde for e in _niveis(validar(geo), "erro"))


def test_planta_com_posicao_relativa(geo, tmp_path):
    _quarto_relativo(geo)
    assert all(p.exists() for p in desenhar(geo, tmp_path))


# --- tipos de ambiente e cercamentos


def _com_jardim(geo):
    from archtools.schema import Ambiente, Cercamento, Ponto
    c = lambda x, y: Ponto(x=x, y=y, status="confirmado", fonte="t")  # noqa: E731
    geo.ambientes.append(Ambiente(id="jardim", nome="Jardim", tipo="externo",
                                  vertices=[c(0, 3600), c(7150, 3600), c(7150, 5600), c(0, 5600)]))
    geo.cercamentos.append(Cercamento(id="tela", tipo="tela", altura=Medida(valor=1800, status="confirmado", fonte="t"),
                                      pontos=[c(0, 3600), c(0, 5600), c(7150, 5600), c(7150, 3600)]))
    return geo


def test_totais_separados_por_tipo(geo):
    q = quadro_areas(_com_jardim(geo))
    assert "**Total ambientes internos** | | **~23.00 m² (estimado)**" in q
    assert "**Total áreas descobertas** | | **14.30 m²**" in q
    assert "| externo | 14.30 m² |" in q and "| n/a |" in q


def test_tipo_invalido_rejeitado():
    from archtools.schema import Ambiente
    with pytest.raises(ValidationError):
        Ambiente(id="x", nome="x", tipo="garagem")


def test_cercamento_exige_dois_pontos():
    from archtools.schema import Cercamento, Ponto
    with pytest.raises(ValidationError):
        Cercamento(id="t", tipo="tela", altura=Medida(status="desconhecido"),
                   pontos=[Ponto(x=0, y=0, status="confirmado", fonte="t")])


def test_planta_e_pendencias_com_cercamento(geo, tmp_path):
    _com_jardim(geo)
    assert all(p.exists() for p in desenhar(geo, tmp_path))
    assert "cercamento `tela`" not in pendencias(geo)  # tudo confirmado -> sem pendência


# --- relatórios e planta


def test_quadro_areas_marca_estimados(geo):
    q = quadro_areas(geo)
    assert "14.00 m²" in q
    assert "~9.00 m² (estimado)" in q
    assert "~23.00 m² (estimado)" in q  # total herda o status mais fraco


def test_pendencias_lista_desconhecidos_e_estimados(geo):
    texto = pendencias(geo)
    assert "janela-quarto" in texto and "peitoril" in texto
    assert "proporção do desenho" in texto


def test_planta_gera_arquivos(geo, tmp_path):
    saidas = desenhar(geo, tmp_path)
    assert all(p.exists() and p.stat().st_size > 0 for p in saidas)
