from pathlib import Path

import pytest
import yaml
from PIL import Image

from archtools.cli import main
from archtools.estilo import carregar_arquitetos
from archtools.referencias import (carregar_pasta, cobertura, delta_e, extrair_paleta, gravar_paleta,
                                   mais_proxima, validar_referencias)

RAIZ = Path(__file__).resolve().parents[2]


def _imagem(caminho: Path) -> Path:
    """3/4 tijolo (#9C4F36), 1/4 grafite (#2B2B2B)."""
    im = Image.new("RGB", (100, 100), "#9C4F36")
    im.paste(Image.new("RGB", (25, 100), "#2B2B2B"), (75, 0))
    im.save(caminho)
    return caminho


def _sidecar(pasta: Path, nome: str, **extra) -> Path:
    dados = {"id": nome, "arquivo": f"{nome}.png", "origem": "teste", "licenca": "CC0",
             "tipo": "ambiente", **extra}
    f = pasta / f"{nome}.yaml"
    f.write_text(yaml.safe_dump(dados, allow_unicode=True), encoding="utf-8")
    return f


def test_paleta_deterministica_e_fracoes(tmp_path):
    img = _imagem(tmp_path / "a.png")
    cores = extrair_paleta(img, n_cores=4)
    assert cores == extrair_paleta(img, n_cores=4)  # determinística
    assert cores[0].hex == "#9C4F36" and cores[0].fracao == pytest.approx(0.75, abs=0.01)
    assert cores[1].hex == "#2B2B2B" and cores[1].fracao == pytest.approx(0.25, abs=0.01)


def test_paleta_arredondada_soma_pouco_acima_de_1():
    """6 frações arredondadas a 3 casas podem somar 1,001 — não é erro."""
    from archtools.referencias import PaletaExtraida
    PaletaExtraida(script="x", cores=[{"hex": "#000000", "fracao": f} for f in
                                      (0.167, 0.167, 0.167, 0.167, 0.167, 0.166)])
    with pytest.raises(ValueError, match="somam mais que 1"):
        PaletaExtraida(script="x", cores=[{"hex": "#000000", "fracao": 0.6}, {"hex": "#FFFFFF", "fracao": 0.5}])


def test_paleta_de_imagem_ruidosa_grava(tmp_path):
    """Imagem com muitas cores (6 grupos) — a soma arredondada precisa validar."""
    import random
    rnd = random.Random(1)
    im = Image.new("RGB", (120, 120))
    im.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)) for _ in range(120 * 120)])
    im.save(tmp_path / "a.png")
    sc = _sidecar(tmp_path, "a")
    for n in range(2, 9):
        gravar_paleta(sc, extrair_paleta(tmp_path / "a.png", n), f"n={n}")


def test_delta_e_e_cor_mais_proxima():
    assert delta_e("#FFFFFF", "#FFFFFF") == 0
    assert delta_e("#000000", "#FFFFFF") == pytest.approx(100, abs=0.5)
    industrial = carregar_arquitetos(RAIZ / "arquitetos")["industrial"]
    assert mais_proxima("#9D5037", industrial)[0] == "tijolo"


def test_pasta_achados(tmp_path):
    _imagem(tmp_path / "ok.png")
    _imagem(tmp_path / "solta.png")  # sem YAML
    _sidecar(tmp_path, "ok")
    _sidecar(tmp_path, "falta")  # YAML sem imagem
    (tmp_path / "errado.yaml").write_text(yaml.safe_dump(
        {"id": "outro", "arquivo": "ok.png", "origem": "x", "licenca": "CC0", "tipo": "ambiente"}), encoding="utf-8")
    refs, achados = carregar_pasta(tmp_path)
    msgs = [str(a) for a in achados]
    assert any("solta.png" in m and "sem YAML" in m for m in msgs)
    assert any("'falta.png' não existe" in m for m in msgs)
    assert any("id 'outro' difere" in m for m in msgs)
    assert cobertura(refs)["ambiente"] == 3


def test_licenca_obrigatoria(tmp_path):
    _imagem(tmp_path / "a.png")
    (tmp_path / "a.yaml").write_text(yaml.safe_dump(
        {"id": "a", "arquivo": "a.png", "origem": "x", "tipo": "ambiente"}), encoding="utf-8")
    _, achados = carregar_pasta(tmp_path)
    assert any(a.nivel == "erro" and "licenca" in a.msg for a in achados)


def test_tags_e_influencias(tmp_path):
    _imagem(tmp_path / "a.png")
    _sidecar(tmp_path, "a", analise={
        "por": "teste",
        "influencias": [{"estilo": "industrial", "peso": "alto"}, {"estilo": "escandinavo", "peso": "baixo"}],
        "elementos": [{"tipo": "revestimento", "descricao": "tijolo", "tags": ["tijolo", "tijolinho"]}]})
    refs, _ = carregar_pasta(tmp_path)
    achados = validar_referencias(refs, {"tijolo"}, {"industrial"}, "x")
    assert any(a.nivel == "erro" and "tijolinho" in a.msg for a in achados)
    assert any(a.nivel == "aviso" and "escandinavo" in a.msg for a in achados)
    assert any("sem paleta" in a.msg for a in achados)


def test_gravar_paleta(tmp_path):
    img = _imagem(tmp_path / "a.png")
    sc = _sidecar(tmp_path, "a", usuario={"gosto": ["tijolo"], "confirmado_em": "2026-11-18"})
    gravar_paleta(sc, extrair_paleta(img, 4), "archtools paleta --cores 4")
    refs, achados = carregar_pasta(tmp_path)
    assert refs["a"].analise.paleta.cores[0].hex == "#9C4F36"
    assert refs["a"].usuario.gosto == ["tijolo"]  # preserva o resto
    assert not [a for a in achados if a.nivel == "erro"]


def test_vocabulario_recusa_tag_desconhecida(tmp_path):
    origem = RAIZ / "arquitetos" / "industrial" / "arquiteto.yaml"
    (tmp_path / "industrial").mkdir()
    (tmp_path / "industrial" / "arquiteto.yaml").write_text(origem.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "tags.yaml").write_text("tags: {metal_preto: x}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="fora do vocabulário"):
        carregar_arquitetos(tmp_path)


def test_cli_referencias_do_repositorio():
    assert main(["referencias", str(RAIZ / "arquitetos"), "--arquitetos", str(RAIZ / "arquitetos")]) == 0


def test_cli_paleta(tmp_path, capsys):
    img = _imagem(tmp_path / "a.png")
    assert main(["paleta", str(img), "--cores", "4", "--arquiteto", "industrial",
                 "--arquitetos", str(RAIZ / "arquitetos")]) == 0
    assert "≈ tijolo" in capsys.readouterr().out
