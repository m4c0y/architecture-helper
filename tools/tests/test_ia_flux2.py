import base64
import io
import json

import pytest
import yaml
from PIL import Image

from archtools import ia_flux2


def _png(cor, tam=(64, 36)) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", tam, cor).save(b, "PNG")
    return b.getvalue()


CFG = {"cameras": ["porta", "mesa"], "periodos": ["dia", "noite"], "saida": "saidas/final",
       "ia": {"mestra": "porta-dia", "sementes": [21, 7], "limite": 0.85, "fixas": "SOFA: grey.",
              "objetos": {"sofa": "a grey sofa"}, "paredes": {"0": "the door wall"}}}


def test_ordem_mestra_primeiro_e_noite_usa_o_dia_da_mesma_camera():
    ordem = ia_flux2.ordem_das_vistas(CFG, "q")
    assert ordem[0] == ("q-porta-dia", "porta", "dia", None)
    refs = {nome: ref for nome, _, _, ref in ordem}
    assert refs["q-mesa-dia"] == "q-porta-dia"
    assert refs["q-porta-noite"] == "q-porta-dia" and refs["q-mesa-noite"] == "q-mesa-dia"
    assert [n for n, *_ in ordem].index("q-mesa-dia") < [n for n, *_ in ordem].index("q-mesa-noite")


def test_comandos_do_blender_gravam_na_pasta_blender(tmp_path):
    (tmp_path / "ambientes/q").mkdir(parents=True)
    (tmp_path / "ambientes/q/render_final.yaml").write_text(yaml.safe_dump(CFG), encoding="utf-8")
    render, prof, masc = ia_flux2.comandos_blender(tmp_path, "q")
    assert "saidas/final/blender --cameras q-porta q-mesa" in render and "--periodo ambos" in render
    assert "saidas/final/blender/profundidade" in prof and prof.endswith("--profundidade")
    assert "saidas/final/blender/mascaras" in masc and masc.endswith("--mascaras")


def test_produto_sem_modelo_e_acusado():
    cena = {"moveis": [{"id": "sofa", "produto": "x", "partes": {"base": 1}},
                       {"id": "cadeira", "produto": "y"},
                       {"id": "mesa"},
                       {"id": "rack", "produto": "z", "modelo": "rack_vinis"}]}
    assert ia_flux2.sem_modelo(cena) == ["cadeira"]
    assert ia_flux2.sem_modelo(cena, {"sofa"}) == []


def test_custo_conta_as_imagens_enviadas():
    assert ia_flux2.custo(2) == 0.16   # mestra: render + profundidade (+ saída) ≈ 4 MP
    assert ia_flux2.custo(3) == 0.22   # + referência


def _projeto(tmp_path, cena_moveis):
    (tmp_path / "ambientes/q").mkdir(parents=True)
    (tmp_path / "ambientes/q/render_final.yaml").write_text(yaml.safe_dump(CFG), encoding="utf-8")
    (tmp_path / "saidas").mkdir()
    (tmp_path / "saidas/cena.json").write_text(json.dumps({"moveis": cena_moveis}), encoding="utf-8")
    f = tmp_path / "saidas/final/blender"
    (f / "mascaras").mkdir(parents=True)
    (f / "profundidade").mkdir()
    mapas = {}
    for cam in CFG["cameras"]:
        (f / "mascaras" / f"q-{cam}-ids.png").write_bytes(_png((10, 20, 30)))
        (f / "profundidade" / f"q-{cam}-profundidade.png").write_bytes(_png((128, 128, 128)))
        mapas[f"q-{cam}"] = {"sofa": [10, 20, 30]}
        for per in CFG["periodos"]:
            (f / f"q-{cam}-{per}.png").write_bytes(_png((90, 90, 90)))
    (f / "mascaras/mascaras.json").write_text(json.dumps(mapas), encoding="utf-8")
    return f


def test_rodar_e_selecionar(tmp_path, monkeypatch):
    monkeypatch.setattr(ia_flux2, "itens_na_camera", lambda *a, **k: [{"id": "sofa"}])
    f = _projeto(tmp_path, [{"id": "sofa", "produto": "x", "modelo": "sofa"}])
    pedidos = []

    def chamada(corpo):
        pedidos.append(corpo)
        url = "data:image/png;base64," + base64.b64encode(_png((90, 90, 90))).decode()
        return {"images": [{"url": url}]}

    monkeypatch.setattr(ia_flux2, "aderencia", lambda r, i: 0.9)
    rel = ia_flux2.rodar(tmp_path, "q", k="x", chamada=chamada)
    assert len(pedidos) == 4                       # uma semente por vista (0.9 >= limite)
    assert len(pedidos[0]["image_urls"]) == 2      # mestra: render + profundidade
    assert all(len(p["image_urls"]) == 3 for p in pedidos[1:])
    assert "SOFA: grey." in pedidos[0]["prompt"] and "a grey sofa" in pedidos[0]["prompt"]
    assert "SAME camera position" in pedidos[-1]["prompt"]   # noite: referência = dia da mesma câmera
    assert rel["vistas"]["q-mesa-noite"]["referencia"] == "q-mesa-dia"
    assert rel["custo_estimado_usd"] == pytest.approx(0.16 + 3 * 0.22)

    final = ia_flux2.selecionar(tmp_path, "q", {"q-mesa-noite": "q-mesa-noite-s21.png"}, limpar=True)
    sel = json.loads((final / "selecao.json").read_text(encoding="utf-8"))
    assert sorted(p.name for p in final.glob("*.png")) == ["q-mesa-dia.png", "q-mesa-noite.png",
                                                            "q-porta-dia.png", "q-porta-noite.png"]
    assert sel["vistas"]["q-mesa-noite"]["escolha"] == "usuário"
    assert final == f.parent / "ia" and not (f.parent / "ia-candidatas").exists()


def test_rodar_recusa_produto_sem_modelo(tmp_path, monkeypatch):
    monkeypatch.setattr(ia_flux2, "itens_na_camera", lambda *a, **k: [{"id": "cadeira"}])
    _projeto(tmp_path, [{"id": "cadeira", "produto": "y"}])
    with pytest.raises(RuntimeError, match="cadeira"):
        ia_flux2.rodar(tmp_path, "q", k="x", chamada=lambda c: pytest.fail("não devia chamar a fal"))
