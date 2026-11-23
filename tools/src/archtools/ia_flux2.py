"""Acabamento fotográfico com FLUX.2 [max] (edição com imagens, fal.ai) — imagens ILUSTRATIVAS.

Fluxo da P5 (decidido em 2026-11-23, depois dos testes com Gemini, FLUX.1 e FLUX.2):

1. Os produtos aparecem na IA como o Blender os desenha: cada item com `produto:` tem que ter
   `modelo` 3D detalhado (P4). Fotos de produto NÃO vão para a IA (ela copiava o fundo das fotos e
   inventava objetos). Sem modelo → `sem_modelo` acusa e a rodada não começa.
2. Para cada vista vão: o render Cycles (@Image1) + o mapa de PROFUNDIDADE exato do Blender
   (@Image2, `--profundidade`) + o texto montado das MÁSCARAS do Blender (`--mascaras`): onde fica
   cada parede e cada objeto, em % da imagem, com a descrição real (`ia.objetos`).
3. VISTA MESTRA: a primeira vista (`ia.mestra`, ex.: porta-dia) é gerada sozinha. As outras vistas
   de dia recebem a mestra como foto aprovada do MESMO quarto (aparência, não enquadramento).
   As vistas de NOITE recebem a imagem de DIA da MESMA câmera (composição igual; só a luz muda):
   com a mestra, a IA movia móveis à noite (render escuro pesa pouco).
4. Sementes `ia.sementes` (ex.: [21, 7]): a segunda só roda se a aderência da primeira ficar abaixo
   de `ia.limite`. A aderência mede só contornos — a ESCOLHA FINAL é visual (usuário), com
   `selecionar`, que grava as escolhidas em `<saida>/ia/` + `selecao.json`.

Custo (fal, 2026-11-23): US$ 0,07 o 1º MP + 0,03 por MP extra, contando as imagens enviadas
(≈ US$ 0,16 a mestra, ≈ 0,22 as demais, por semente). Chave: FAL_KEY ou ~/.archtools/fal.key.
"""
from __future__ import annotations

import base64
import io
import json
import os
import shutil
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

import yaml

from .ia import itens_na_camera, selar

MODELO = "fal-ai/flux-2-max/edit"
BLENDER = "blender"      # <saida>/blender/: renders, mascaras/, profundidade/ e modelo.blend do Blender
IA = "ia"                # <saida>/ia/: imagens de IA escolhidas (+ ia-candidatas/ durante a escolha)
ARQUIVO_CHAVE = Path.home() / ".archtools" / "fal.key"
TAMANHO = (1536, 864)    # múltiplos de 16, 16:9
PARCIAL = 0.6            # fração visível abaixo da qual o item é "só uma parte aparece"
LUZ = {"dia": "Daytime, soft natural daylight through the window.",
       "noite": "Night: the window is dark, the room is lit by warm 2700K lamps, cozy and dim."}
REALISMO = (
    "IMPORTANT: the result must look like a REAL PHOTOGRAPH, not a 3D render: a real outdoor view through the window "
    "when it is daytime (sky, trees, neighbouring buildings), natural light falloff and soft bounced light, visible "
    "fabric weave and wood grain, slight real-world imperfections, natural camera exposure and color.")
SUPERFICIES = {"teto": "the ceiling", "piso": "the floor", "janela": "the window glass",
               "fora": "the doorway opening, showing the space beyond", "parede": "a wall"}


# ---------------------------------------------------------------- fal
def chave() -> str:
    k = os.environ.get("FAL_KEY", "").strip()
    if not k and ARQUIVO_CHAVE.exists():
        k = ARQUIVO_CHAVE.read_text(encoding="utf-8").strip()
    if not k:
        raise RuntimeError(f"sem chave da fal: defina FAL_KEY ou crie {ARQUIVO_CHAVE}")
    return k


def _post(modelo: str, corpo: dict, k: str, timeout: int = 600, tentativas: int = 3) -> dict:
    req = urllib.request.Request("https://fal.run/" + modelo, data=json.dumps(corpo).encode(), method="POST",
                                 headers={"Authorization": "Key " + k, "Content-Type": "application/json"})
    for t in range(tentativas):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except (ConnectionError, TimeoutError, urllib.error.URLError) as e:
            if isinstance(e, urllib.error.HTTPError) and e.code < 500:  # saldo, chave, pedido inválido
                raise RuntimeError(f"fal {e.code}: {e.read().decode(errors='replace')[:300]}") from e
            if t == tentativas - 1:
                raise
            time.sleep(5 * (t + 1))


def _baixar(url: str) -> bytes:
    if url.startswith("data:"):
        return base64.b64decode(url.split(",", 1)[1])
    with urllib.request.urlopen(url, timeout=180) as r:
        return r.read()


def _uri(img, tamanho=TAMANHO) -> str:
    from PIL import Image
    im = (img if hasattr(img, "convert") else Image.open(img)).convert("RGB").resize(tamanho)
    b = io.BytesIO()
    im.save(b, "JPEG", quality=92)
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()


def custo(n_entradas: int, tamanho=TAMANHO) -> float:
    """US$ de um pedido ao FLUX.2 [max]: 0,07 o 1º MP + 0,03 por MP extra (entradas + saída)."""
    mp = (n_entradas + 1) * tamanho[0] * tamanho[1] / 1e6
    return round(0.07 + 0.03 * max(0, round(mp + 0.499) - 1), 2)


# ---------------------------------------------------------------- medidas
def aderencia(render, img, lado: int = 384) -> float:
    """Fração dos contornos fortes do render que reaparecem (com folga de ~1% da largura) nos
    contornos do resultado. 1 = estrutura no mesmo lugar; perto de 0 = espaço refeito.
    Não percebe objeto inventado em cima de contorno existente: serve de filtro, não de escolha."""
    from PIL import ImageFilter, ImageOps
    tam = (lado, round(lado * render.height / render.width))

    def bordas(im, limiar):
        g = ImageOps.autocontrast(im.convert("L").resize(tam).filter(ImageFilter.GaussianBlur(1)))
        return g.filter(ImageFilter.FIND_EDGES).point(lambda v: 255 if v > limiar else 0)

    r = bordas(render, 70)
    a = bordas(img, 40).filter(ImageFilter.MaxFilter(7))
    rp, ap = r.load(), a.load()
    tot = hit = 0
    for y in range(2, tam[1] - 2):
        for x in range(2, tam[0] - 2):
            if rp[x, y]:
                tot += 1
                hit += ap[x, y] > 0
    return round(hit / tot, 3) if tot else 0.0


def regioes(ids_png: Path, cores: dict, ambiente: str, lado: int = 384) -> dict:
    """{chave: (area, x0, x1, y0, y1)} em frações da imagem, a partir da imagem de máscaras (já sem o
    que está escondido atrás de outro objeto). Arquitetura de fora do ambiente vira "@fora"."""
    from PIL import Image
    im = Image.open(ids_png).convert("RGB")
    w, h = lado, round(lado * im.height / im.width)
    im = im.resize((w, h), Image.NEAREST)
    alvo = {tuple(c): k for k, c in cores.items()}
    cache, acc = {}, {}
    px = im.load()
    for y in range(h):
        for x in range(w):
            c = px[x, y]
            if c not in cache:
                best = min(alvo, key=lambda a: sum(abs(i - j) for i, j in zip(a, c)))
                k = alvo[best] if sum(abs(i - j) for i, j in zip(best, c)) <= 6 else None
                if k and k.startswith("@") and not k.startswith(f"@{ambiente}:"):
                    k = "@fora"
                cache[c] = k
            k = cache[c]
            if k is None:
                continue
            a = acc.setdefault(k, [0, x, x, y, y])
            a[0] += 1
            a[1], a[2], a[3], a[4] = min(a[1], x), max(a[2], x), min(a[3], y), max(a[4], y)
    return {k: (a[0] / (w * h), a[1] / w, (a[2] + 1) / w, a[3] / h, (a[4] + 1) / h) for k, a in acc.items()}


def _faixa(r) -> str:
    area, x0, x1, y0, y1 = r
    return f"x {x0:.0%}-{x1:.0%}, y {y0:.0%}-{y1:.0%} ({area:.1%} of the image)"


def sem_modelo(cena: dict, ids=None) -> list[str]:
    """Itens de produto (`produto:`) sem modelo 3D detalhado (`modelo` ou `partes`) — a IA
    receberia uma caixa e inventaria o produto. `ids`: limitar a estes itens."""
    return [m["id"] for m in cena["moveis"]
            if m.get("produto") and not (m.get("modelo") or m.get("partes")) and (ids is None or m["id"] in ids)]


# ---------------------------------------------------------------- prompt
def montar(cfg: dict, ambiente: str, cam: str, per: str, render, profundidade, mapa: dict, ids_png: Path,
           cena: dict, area_min: float = 0.0015) -> tuple[str, list[str]]:
    """(prompt, [imagens]) de uma vista: render + profundidade + regiões das máscaras."""
    ia_cfg = cfg.get("ia") or {}
    objetos, paredes = ia_cfg.get("objetos") or {}, ia_cfg.get("paredes") or {}
    sup_txt = {**SUPERFICIES, **(ia_cfg.get("superficies") or {})}
    cid = f"{ambiente}-{cam}"
    reg = regioes(ids_png, mapa, ambiente)
    borda = {i["id"]: i.get("fracao", 1) for i in itens_na_camera(cena, cid, ambiente)}
    imgs = [_uri(render), _uri(profundidade)]
    visiveis = sorted(((k, r) for k, r in reg.items() if not k.startswith("@") and r[0] >= area_min and k in objetos),
                      key=lambda kr: -kr[1][0])
    sup = []
    for k, r in sorted(reg.items(), key=lambda kr: -kr[1][0]):
        if not k.startswith("@") or r[0] < area_min:
            continue
        tipo = "fora" if k == "@fora" else k.split(":", 1)[1]
        if tipo.startswith("parede-"):
            txt = paredes.get(tipo.split("-")[1], "a wall") + (f" ({sup_txt['parede_acabamento']})"
                                                               if sup_txt.get("parede_acabamento") else "")
        else:
            txt = sup_txt.get(tipo, tipo)
        sup.append(f"- {txt}: {_faixa(r)}")
    obj = [f"- {objetos[k]}: {_faixa(r)}"
           + (" - only a part of it is in the frame (cut by the image border)" if borda.get(k, 1) < PARCIAL else "")
           for k, r in visiveis]
    prompt = (
        f"@Image1 is a 3D render of {ia_cfg.get('comodo', 'my real room')}. Turn @Image1 into a real photograph of "
        "EXACTLY the same view: same camera, crop, zoom and perspective. Every region below must stay where it is in "
        "@Image1 (coordinates are measured from the 3D model: x from the left edge, y from the top edge, in % of the "
        "image). Do not zoom out, do not move, mirror, add or remove anything. Many objects in @Image1 are simplified "
        "3D shapes: replace each one, in its own region, with the real object described.\n"
        "@Image2 is the exact DEPTH MAP of @Image1 computed from the 3D model (white = near, dark = far): the result "
        "must follow this geometry exactly - every wall, opening and object edge in the same place, with the same "
        "size and perspective. Do not copy its grey look.\n"
        + LUZ.get(per, "") + "\n"
        "Room surfaces in @Image1:\n" + "\n".join(sup) + "\n"
        "Objects in @Image1 (largest first):\n" + "\n".join(obj) + "\n"
        "Result: photorealistic interior photograph, real materials, natural light, full-frame camera, no text, "
        "no people, screens switched off.")
    return prompt, imgs


def _referencia(n: int, mesma_camera: bool) -> str:
    if mesma_camera:
        return (f"@Image{n} is an APPROVED real photograph of this SAME room taken from this SAME camera position "
                "during the DAY: keep exactly its composition, framing and the position of every object, and make "
                "every piece of furniture, fabric, wood tone, wall color, plant and book look exactly like in it. "
                "Change ONLY the time of day to NIGHT with the lighting described here (window dark, light only from "
                "the lamps).\n")
    return (f"@Image{n} is an APPROVED real photograph of this SAME room from another camera angle: every piece of "
            "furniture, fabric, wood tone, wall color, plant, book and object must look exactly like in it. Do NOT "
            "copy its camera angle, composition or time of day - camera and layout come only from @Image1 and "
            "@Image2, and the lighting is the one described here.\n")


# ---------------------------------------------------------------- rodada
def _config(pasta: Path, ambiente: str) -> dict:
    arq = pasta / "ambientes" / ambiente / "render_final.yaml"
    if not arq.exists():
        raise RuntimeError(f"{arq} não existe (P5: crie o render_final.yaml do ambiente)")
    return yaml.safe_load(arq.read_text(encoding="utf-8")) or {}


BLENDER_EXE = r"C:\Program Files\Blender Foundation\Blender 5.3\blender.exe"


def comandos_blender(pasta: Path, ambiente: str) -> list[str]:
    """As três chamadas do Blender da P5 (render, profundidade, máscaras), sempre para <saida>/blender/."""
    cfg = _config(pasta, ambiente)
    base = (pasta / cfg.get("saida", "saidas/final") / BLENDER).as_posix()
    cams = " ".join(f"{ambiente}-{c}" for c in cfg.get("cameras", []))
    pers = cfg.get("periodos", ["dia"])
    per = "ambos" if len(pers) > 1 else pers[0]
    ini = f'& "{BLENDER_EXE}" --background --python blender/construir_cena.py -- {(pasta / "saidas/cena.json").as_posix()}'
    return [f"{ini} {base} --cameras {cams} --res {cfg.get('resolucao', '1920x1080')} --motor {cfg.get('motor', 'cycles')}"
            f" --amostras {cfg.get('amostras', 192)} --periodo {per}",
            f"{ini} {base}/profundidade --cameras {cams} --res {TAMANHO[0]}x{TAMANHO[1]} --profundidade",
            f"{ini} {base}/mascaras --cameras {cams} --res {TAMANHO[0]}x{TAMANHO[1]} --mascaras"]


def ordem_das_vistas(cfg: dict, ambiente: str) -> list[tuple[str, str, str, str | None]]:
    """[(nome, câmera, período, referência)]: mestra primeiro, depois as de dia (referência = mestra),
    depois as de noite (referência = a de dia da mesma câmera, ou a mestra se não houver dia)."""
    ia_cfg = cfg.get("ia") or {}
    cams, pers = cfg.get("cameras", []), cfg.get("periodos", ["dia"])
    m_cam, m_per = (ia_cfg.get("mestra") or f"{cams[0]}-{pers[0]}").rsplit("-", 1)
    mestra = f"{ambiente}-{m_cam}-{m_per}"
    ordem = [(mestra, m_cam, m_per, None)]
    for per in sorted(pers, key=lambda p: p != "dia"):
        for cam in cams:
            nome = f"{ambiente}-{cam}-{per}"
            if nome == mestra:
                continue
            dia = f"{ambiente}-{cam}-dia"
            ref = dia if per != "dia" and "dia" in pers else mestra
            ordem.append((nome, cam, per, ref))
    return ordem


def rodar(pasta: Path, ambiente: str, vistas: list[str] | None = None, k: str | None = None,
          chamada=None) -> dict:
    """Gera as vistas do render final com FLUX.2 [max] em `<saida>/ia-candidatas/`, a partir das imagens
    do Blender em `<saida>/blender/` (renders, `mascaras/`, `profundidade/`).
    `vistas`: refazer só estas (ex.: ["dorm2-mesa-noite"]); as referências vêm das escolhidas em
    `<saida>/ia/` ou das candidatas já geradas. Devolve o relatório (também em relatorio.json)."""
    from PIL import Image, ImageOps
    cfg = _config(pasta, ambiente)
    ia_cfg = cfg.get("ia") or {}
    saida = pasta / cfg.get("saida", "saidas/final")
    origem, destino, escolhidas = saida / BLENDER, saida / "ia-candidatas", saida / IA
    cena = json.loads((pasta / "saidas" / "cena.json").read_text(encoding="utf-8"))
    faltam = sem_modelo(cena, {i["id"] for c in cfg.get("cameras", [])
                              for i in itens_na_camera(cena, f"{ambiente}-{c}", ambiente)})
    if faltam:
        raise RuntimeError("produtos sem modelo 3D detalhado (P4, detalhamento.yaml): " + ", ".join(faltam))
    mapas = origem / "mascaras" / "mascaras.json"
    if not mapas.exists() or not (origem / "profundidade").exists():
        raise RuntimeError(f"faltam máscaras/profundidade em {origem}: rode o Blender com --mascaras e --profundidade "
                           f"(saída {origem}/mascaras e {origem}/profundidade)")
    mapas = json.loads(mapas.read_text(encoding="utf-8"))
    sementes = ia_cfg.get("sementes", [21, 7])
    limite = ia_cfg.get("limite", 0.85)
    fixas = " ".join((ia_cfg.get("fixas") or "").split())
    destino.mkdir(parents=True, exist_ok=True)
    rel_arq = destino / "relatorio.json"
    rel = json.loads(rel_arq.read_text(encoding="utf-8")) if rel_arq.exists() else {"vistas": {}, "custo_estimado_usd": 0}
    k = k or chave()
    chamada = chamada or (lambda corpo: _post(MODELO, corpo, k))
    gasto = 0.0

    def imagem(nome):
        for arq in (escolhidas / f"{nome}.png", destino / rel["vistas"].get(nome, {}).get("melhor", "-")):
            if arq.exists():
                return Image.open(arq).convert("RGB")
        return None

    for nome, cam, per, ref in ordem_das_vistas(cfg, ambiente):
        if vistas and nome not in vistas:
            continue
        cid = f"{ambiente}-{cam}"
        render = Image.open(origem / f"{nome}.png").convert("RGB")
        prof = ImageOps.autocontrast(Image.open(origem / "profundidade" / f"{cid}-profundidade.png").convert("L"),
                                     cutoff=1).convert("RGB")
        prompt, imgs = montar(cfg, ambiente, cam, per, render, prof, mapas[cid],
                              origem / "mascaras" / f"{cid}-ids.png", cena)
        extra = ""
        if ref is not None:
            img_ref = imagem(ref)
            if img_ref is None:
                raise RuntimeError(f"{nome}: falta a imagem de referência {ref} (gere-a antes)")
            imgs.append(_uri(img_ref))
            extra = _referencia(len(imgs), mesma_camera=ref.startswith(cid + "-"))
        prompt = prompt.replace("Result: photorealistic interior photograph",
                                extra + fixas + "\n" + REALISMO + "\nResult: photorealistic interior photograph")
        (destino / f"{nome}.prompt.txt").write_text(prompt, encoding="utf-8")
        notas = []
        for s in sementes:
            r = chamada({"prompt": prompt, "image_urls": imgs, "seed": s, "output_format": "png",
                         "image_size": {"width": TAMANHO[0], "height": TAMANHO[1]}, "safety_tolerance": "2"})
            gasto += custo(len(imgs))
            dado = _baixar(r["images"][0]["url"])
            nota = aderencia(render, Image.open(io.BytesIO(dado)).convert("RGB"))
            arq = destino / f"{nome}-s{s}.png"
            arq.write_bytes(selar(dado))
            notas.append({"arquivo": arq.name, "seed": s, "aderencia": nota})
            print(f"  {nome} s{s}: aderência {nota:.2f} (custo da rodada ~US$ {gasto:.2f})", flush=True)
            if nota >= limite:
                break
        melhor = max(notas, key=lambda n: n["aderencia"])
        rel["vistas"][nome] = {"melhor": melhor["arquivo"], "variacoes": notas, "referencia": ref,
                               "imagens_enviadas": len(imgs)}
    rel.update({"gerado_em": datetime.now().isoformat(timespec="seconds"), "modelo": MODELO,
                "mestra": ordem_das_vistas(cfg, ambiente)[0][0],
                "custo_estimado_usd": round(rel.get("custo_estimado_usd", 0) + gasto, 2),
                "aviso": "imagens ILUSTRATIVAS (IA); o render do Blender é a referência de medidas e cores"})
    rel_arq.write_text(json.dumps(rel, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"custo estimado desta rodada: US$ {gasto:.2f} (acumulado US$ {rel['custo_estimado_usd']:.2f})")
    return rel


def selecionar(pasta: Path, ambiente: str, escolhas: dict[str, str] | None = None, limpar: bool = False) -> Path:
    """Copia a candidata escolhida de cada vista (padrão: a de maior aderência; `escolhas` troca:
    {"dorm2-mesa-noite": "dorm2-mesa-noite-s21.png"}) para `<saida>/ia/<vista>.png` e grava
    `selecao.json`. `limpar`: apaga `ia-candidatas/` depois."""
    cfg = _config(pasta, ambiente)
    saida = pasta / cfg.get("saida", "saidas/final")
    cand, final = saida / "ia-candidatas", saida / IA
    rel = json.loads((cand / "relatorio.json").read_text(encoding="utf-8"))
    escolhas = escolhas or {}
    final.mkdir(parents=True, exist_ok=True)
    sel_arq = final / "selecao.json"
    sel = json.loads(sel_arq.read_text(encoding="utf-8")) if sel_arq.exists() else {"vistas": {}}
    for nome, v in rel["vistas"].items():
        arq = escolhas.get(nome, v["melhor"])
        nota = next((n for n in v["variacoes"] if n["arquivo"] == arq), None)
        if nota is None:
            raise RuntimeError(f"{nome}: {arq} não está entre as candidatas")
        shutil.copyfile(cand / arq, final / f"{nome}.png")
        sel["vistas"][nome] = {"arquivo": f"{nome}.png", "origem": arq, "seed": nota["seed"],
                               "aderencia": nota["aderencia"], "referencia": v.get("referencia") or "nenhuma (mestra)",
                               "escolha": "usuário" if nome in escolhas else "maior aderência"}
    sel.update({"selecionado_em": datetime.now().isoformat(timespec="seconds"), "modelo": rel.get("modelo"),
                "mestra": rel.get("mestra"),
                "custo_estimado_usd": round(sel.get("custo_consolidado", 0) + rel.get("custo_estimado_usd", 0), 2),
                "aviso": rel.get("aviso")})
    sel_arq.write_text(json.dumps(sel, ensure_ascii=False, indent=1), encoding="utf-8")
    if limpar:  # o custo das candidatas passa a ser consolidado (a próxima rodada começa do zero)
        sel["custo_consolidado"] = sel["custo_estimado_usd"]
        sel_arq.write_text(json.dumps(sel, ensure_ascii=False, indent=1), encoding="utf-8")
        shutil.rmtree(cand)
    return final
