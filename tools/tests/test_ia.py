"""Acabamento com IA: montagem da requisição, leitura da resposta e selo — sem chamar a API."""

import base64
import io

from PIL import Image

from archtools import ia


def _png(w=64, h=36, cor=(40, 60, 50)):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), cor).save(buf, "PNG")
    return buf.getvalue()


def test_prompt_preserva_layout_e_periodo():
    p = ia.montar_prompt("Dark green walls.", "noite")
    assert "Never keep a placeholder shape" in p and "Do not zoom out" in p and "nothing" in p
    assert "Dark green walls." in p and "warm lamps" in p


def test_corpo_e_resposta():
    corpo = ia.corpo_requisicao(_png(), "x")
    partes = corpo["contents"][0]["parts"]
    assert partes[0]["text"] == "x" and partes[1]["inline_data"]["mime_type"] == "image/jpeg"
    assert corpo["generationConfig"]["responseModalities"] == ["IMAGE"]
    resp = {"candidates": [{"content": {"parts": [{"text": "ok"},
                                                  {"inlineData": {"data": base64.b64encode(b"img").decode()}}]}}]}
    assert ia.imagem_da_resposta(resp) == b"img"


def test_rodar_grava_ilustrativas_com_selo(tmp_path):
    amb = tmp_path / "ambientes" / "sala"
    amb.mkdir(parents=True)
    (amb / "render_final.yaml").write_text("cameras: [a]\nperiodos: [dia, noite]\nsaida: saidas/final\n"
                                           "ia: {descricao: 'teste'}\n", encoding="utf-8")
    fin = tmp_path / "saidas" / "final"
    (fin / "blender").mkdir(parents=True)
    (fin / "blender" / "sala-a-dia.png").write_bytes(_png())  # noite ausente: pulada
    chamadas = []
    gerados, entradas = ia.rodar(tmp_path, "sala", chamada=lambda img, p, m, k, **kw: chamadas.append(p) or _png(400, 225, (200, 200, 200)), k="SEGREDO")
    assert [g.name for g in gerados] == ["sala-a-dia-ia.png", "relatorio.json"] and len(chamadas) == 1
    im = Image.open(gerados[0])
    assert im.getpixel((im.width - 8, im.height - 8)) == (0, 0, 0)  # selo "ILUSTRATIVA (IA)" no canto
    assert im.getpixel((5, 5)) == (200, 200, 200)
    assert "SEGREDO" not in (fin / "ia" / "relatorio.json").read_text(encoding="utf-8")  # chave nunca gravada


def test_referencias_vao_depois_do_render():
    corpo = ia.corpo_requisicao(_png(), "x", referencias=[("the real sofa", _png(800, 800))], tamanho="2K")
    partes = corpo["contents"][0]["parts"]
    assert [("text" in p) for p in partes] == [True, False, True, False]
    assert partes[2]["text"] == "Reference image: the real sofa"
    assert corpo["generationConfig"]["imageConfig"]["imageSize"] == "2K"


def test_itens_na_camera_projetam_no_lado_certo():
    cena = {"cameras": [{"id": "c", "pos": [0, 0, 1000], "alvo": [0, 5000, 1000], "lente": 18}],
            "moveis": [{"id": "dir", "nome": "Pegboard", "ambiente": "a", "bbox": [900, 2900, 1100, 3100], "z0": 900, "z1": 1100},
                       {"id": "meio", "nome": "Mesa", "ambiente": "a", "bbox": [-100, 2900, 100, 3100], "z0": 0, "z1": 200},
                       {"id": "atras", "nome": "Sofá", "ambiente": "a", "bbox": [-100, -1100, 100, -900], "z0": 0, "z1": 900}]}
    itens = {i["id"]: i for i in ia.itens_na_camera(cena, "c")}
    assert "atras" not in itens  # atrás da câmera
    assert itens["dir"]["x"] > 0.6 and abs(itens["dir"]["y"] - 0.5) < 0.05
    assert itens["meio"]["x"] == 0.5 and itens["meio"]["y"] > 0.5  # abaixo do horizonte
    p = ia.montar_prompt(None, "dia", list(itens.values()))
    assert "- Pegboard: middle right" in p or "- Pegboard: middle center-right" in p


def test_fotos_dos_produtos_visiveis_vao_como_referencia(tmp_path):
    (tmp_path / "catalogo" / "produtos").mkdir(parents=True)
    (tmp_path / "catalogo" / "produtos" / "cad.yaml").write_text("id: cad\nfotos: [referencias/cad.jpg]\n",
                                                                 encoding="utf-8")
    fotos = ia.fotos_dos_produtos(tmp_path)
    assert fotos == {"cad": [tmp_path / "referencias" / "cad.jpg"]}
    cena = {"moveis": [{"id": "cadeira", "produto": "cad"}, {"id": "mesa", "produto": None}]}
    itens = [{"id": "cadeira", "nome": "Cadeira", "x": 0.5, "y": 0.7}, {"id": "mesa", "nome": "Mesa", "x": 0.6, "y": 0.7}]
    refs = ia.referencias_da_camera(cena, itens, fotos)
    assert len(refs) == 1 and "'Cadeira'" in refs[0][0] and refs[0][1].name == "cad.jpg"


def test_referencia_ligada_a_item_so_vai_quando_ele_aparece(tmp_path):
    import json as _json
    amb = tmp_path / "ambientes" / "sala"
    amb.mkdir(parents=True)
    (tmp_path / "ref.jpg").write_bytes(_png())
    (amb / "render_final.yaml").write_text(
        "cameras: [a]\nperiodos: [dia]\nia:\n  referencias:\n    - {item: rack, imagem: ref.jpg, descricao: estilo}\n",
        encoding="utf-8")
    (tmp_path / "saidas" / "final" / "blender").mkdir(parents=True)
    (tmp_path / "saidas" / "final" / "blender" / "sala-a-dia.png").write_bytes(_png())
    cena = {"cameras": [{"id": "sala-a", "pos": [0, 0, 1000], "alvo": [0, 5000, 1000], "lente": 18}],
            "moveis": [{"id": "rack", "nome": "Rack", "ambiente": "sala", "produto": None,
                        "bbox": [-100, 2900, 100, 3100], "z0": 0, "z1": 600}]}
    (tmp_path / "saidas" / "cena.json").write_text(_json.dumps(cena), encoding="utf-8")
    vistas = []
    ia.rodar(tmp_path, "sala", chamada=lambda img, p, m, k, referencias=(), **kw: vistas.append(referencias) or _png(), k="x")
    assert len(vistas[0]) == 1 and "'Rack'" in vistas[0][0][0]
