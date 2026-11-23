"""Exporta a cena 3D (cena.json) a partir de geometria.yaml + layout.yaml.

Toda a geometria é calculada aqui (Python testado). O script do Blender só lê o JSON e monta
os objetos — não decide nenhuma medida.

Conteúdo (mm, coordenadas globais, z para cima):
- paredes:     prismas (triângulos da base + anéis) entre z0 e z1
- recortes:    prismas a subtrair das paredes (portas, janelas, vãos)
- vidros:      placas finas nas janelas
- pisos/tetos: superfícies trianguladas (tetos podem ser ocultados nas vistas de cima)
- cercamentos: prismas finos (tela)
- moveis:      caixas (bbox no piso + z0/z1)
- cameras:     posições/alvos (mm), lente; uma vista de cima ortográfica por ambiente; câmeras
               nomeadas de `ambientes/<id>/cameras.yaml` (mesmas vistas para comparar propostas)

Suposições marcadas em `suposicoes` (vão para o JSON e para o relatório do render).
"""

from __future__ import annotations

import math
from pathlib import Path

import shapely
from shapely.geometry import LineString, MultiPolygon, Polygon, box
from shapely.ops import unary_union

from .geometria import de_medida, paredes, pe_direito, poligono_global, segmento_abertura
from .layout import Layout, _global, pegada_local
from .materiais import TEXTURA_DA_PECA, de_hex, de_peca, superficie
from .schema import Geometria

ESPESSURA_EXTERNA = 150  # mm — estimada no desenho (0,14–0,16 m); não medida
ESPESSURA_LAJE = 100


def _poligonos(g) -> list[Polygon]:
    if g.is_empty:
        return []
    if isinstance(g, Polygon):
        return [g]
    if isinstance(g, MultiPolygon):
        return list(g.geoms)
    return [p for p in getattr(g, "geoms", []) if isinstance(p, Polygon)]


def _prisma(pol: Polygon, z0: float, z1: float, **extra) -> dict:
    tris = shapely.constrained_delaunay_triangles(pol)
    return {
        "tris": [[list(c) for c in t.exterior.coords[:3]] for t in tris.geoms],
        "aneis": [[list(c) for c in pol.exterior.coords[:-1]]]
        + [[list(c) for c in r.coords[:-1]] for r in pol.interiors],
        "z0": z0, "z1": z1, **extra,
    }


def _superficie(pol: Polygon, z: float, **extra) -> dict:
    tris = shapely.constrained_delaunay_triangles(pol)
    return {"tris": [[list(c) for c in t.exterior.coords[:3]] for t in tris.geoms], "z": z, **extra}


def gerar_cena(geo: Geometria, layout: Layout | None = None) -> dict:
    pd_padrao = de_medida(geo.pe_direito_padrao).valor or 2800
    suposicoes = [f"espessura das paredes externas = {ESPESSURA_EXTERNA} mm (estimada no desenho)",
                  "acabamentos de piso/parede/teto desconhecidos: tons neutros de cinza (origem 'neutro', não é proposta)",
                  "orientação solar desconhecida: sol genérico entrando pelas janelas do fundo"]
    if de_medida(geo.pe_direito_padrao).valor is None:
        suposicoes.append("pé-direito desconhecido: 2800 mm provisório")

    internos = {a.id: poligono_global(a)[0] for a in geo.ambientes
                if a.tipo == "interno" and poligono_global(a)[0] is not None}
    miolo = unary_union(list(internos.values()))
    envoltoria = miolo.buffer(ESPESSURA_EXTERNA, join_style="mitre")
    massa = envoltoria.difference(miolo)

    cena: dict = {"versao": 1, "unidade": "mm", "pe_direito": pd_padrao, "suposicoes": suposicoes,
                  "paredes": [], "recortes": [], "vidros": [], "pisos": [], "tetos": [],
                  "cercamentos": [], "moveis": [], "cameras": []}

    for i, p in enumerate(_poligonos(massa)):
        cena["paredes"].append(_prisma(p, 0, pd_padrao, id=f"parede-{i}", acabamento=superficie("parede")))

    # aberturas: recorte atravessando a parede + vidro nas janelas
    ambientes = {a.id: a for a in geo.ambientes}
    for ab in geo.aberturas:
        amb = ambientes.get(ab.ambiente)
        if amb is None or amb.tipo != "interno":
            continue
        ps = paredes(amb)
        if ab.parede >= len(ps):
            continue
        seg = segmento_abertura(ab, ps[ab.parede])
        alt = de_medida(ab.altura).valor
        if seg is None or alt is None:
            continue
        a, b, _ = seg
        z0 = (de_medida(ab.peitoril).valor or 0) if ab.tipo == "janela" else 0
        faixa = LineString([a, b]).buffer(ESPESSURA_EXTERNA + 60, cap_style="flat")
        cena["recortes"].append(_prisma(faixa, z0, min(z0 + alt, pd_padrao + 1), id=ab.id, tipo=ab.tipo))
        if ab.tipo == "janela":
            pol, _ = poligono_global(amb)
            ux, uy = (b[0] - a[0]), (b[1] - a[1])
            n = math.hypot(ux, uy)
            nx, ny = -uy / n, ux / n
            meio = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            if pol.contains(shapely.Point(meio[0] + nx * 10, meio[1] + ny * 10)):
                nx, ny = -nx, -ny  # aponta para fora
            off = ESPESSURA_EXTERNA * 0.4
            vidro = LineString([(a[0] + nx * off, a[1] + ny * off), (b[0] + nx * off, b[1] + ny * off)]).buffer(
                6, cap_style="flat")
            cena["vidros"].append(_prisma(vidro, z0, z0 + alt, id=f"vidro-{ab.id}", acabamento=superficie("vidro")))

    # pisos (todos os ambientes) e tetos (internos + varanda coberta; forros com pé-direito próprio)
    for amb in geo.ambientes:
        pol, _ = poligono_global(amb)
        if pol is None:
            continue
        cena["pisos"].append(_superficie(pol, 0, id=f"piso-{amb.id}", tipo=amb.tipo, ambiente=amb.id,
                                          acabamento=superficie("piso_externo" if amb.tipo == "externo" else "piso")))
        pd_amb = pe_direito(amb, geo).valor or pd_padrao
        if amb.tipo in ("interno", "varanda") and pd_amb < pd_padrao:
            cena["tetos"].append(_superficie(pol, pd_amb, id=f"forro-{amb.id}", ambiente=amb.id,
                                              acabamento=superficie("teto")))
        if amb.tipo == "varanda":
            cena["tetos"].append(_prisma(pol, pd_padrao, pd_padrao + ESPESSURA_LAJE, id=f"laje-{amb.id}",
                                          acabamento=superficie("teto")))
    for i, p in enumerate(_poligonos(envoltoria)):
        cena["tetos"].append(_prisma(p, pd_padrao, pd_padrao + ESPESSURA_LAJE, id=f"laje-{i}",
                                      acabamento=superficie("teto")))

    for c in geo.cercamentos:
        pts = [(p.x, p.y) for p in c.pontos if p.x is not None]
        alt = de_medida(c.altura).valor
        if len(pts) >= 2 and alt:
            for i, p in enumerate(_poligonos(LineString(pts).buffer(20, cap_style="flat", join_style="mitre"))):
                cena["cercamentos"].append(_prisma(p, 0, alt, id=f"{c.id}-{i}", acabamento=superficie("cercamento")))

    if layout is not None:
        for m in layout.moveis:
            amb = ambientes.get(m.ambiente)
            p = _global(pegada_local(m), amb) if amb else None
            if p is None:
                continue
            z0 = m.elevacao.valor or 0
            z1 = z0 + (m.altura.valor or 0)
            partes = _partes(m, p.bounds, z0, z1)
            for pt in partes:  # cor conhecida do produto; senão, neutro (pendência no relatório)
                aplicar_cor_real(pt, m)
            cena["moveis"].append({"id": m.id, "nome": m.nome, "categoria": m.categoria, "ambiente": m.ambiente,
                                   "bbox": list(p.bounds), "z0": z0, "z1": z1, "frente": m.frente,
                                   "modelo": m.modelo, "produto": m.produto, "cor_real": m.cor_real,
                                   "partes": partes})
    return cena


def aplicar_cor_real(pt: dict, m) -> None:
    """Acabamento da peça: material do modelo; cor real do produto (por peça, ou hex único nas peças
    sem cor própria); senão, neutro. A textura vem do produto, do material da peça ou do preset dele."""
    mat = pt.get("material")
    pt["acabamento"] = de_peca(mat)
    real = m.cor_real
    hex_ = real.get(mat) if isinstance(real, dict) else (real if pt["acabamento"]["origem"] == "neutro" else None)
    if hex_:
        tex = TEXTURA_DA_PECA.get(mat) if isinstance(real, dict) else (m.textura or TEXTURA_DA_PECA.get(mat))
        pt["acabamento"] = de_hex(hex_, f"{m.produto or m.id}-{mat or 'real'}", tex=tex)


def _faixa(bb, lado: str, espessura: float):
    """Faixa de `espessura` mm encostada no lado ('+x', '-x', '+y', '-y') do retângulo bb."""
    x0, y0, x1, y1 = bb
    return {"+x": [x1 - espessura, y0, x1, y1], "-x": [x0, y0, x0 + espessura, y1],
            "+y": [x0, y1 - espessura, x1, y1], "-y": [x0, y0, x1, y0 + espessura]}[lado]


OPOSTO = {"+x": "-x", "-x": "+x", "+y": "-y", "-y": "+y"}
ESQUERDA = {"+x": "+y", "-x": "-y", "+y": "-x", "-y": "+x"}  # de quem olha na direção da frente


# Arredondamento das peças de estofado (só aparência no Blender; fração da menor dimensão da peça)
RAIO_BLOCO = 0.2   # blocos de assento
RAIO_ROLO = 0.45   # braços (rolos)
RAIO_ENCOSTO = 0.28  # almofadas de encosto: blocos de cantos macios, não rolos (foto do Flowin)
FOLGA_ALMOFADAS = 4  # mm entre almofadas de encosto vizinhas: encostadas, leem como uma peça só
TUBO = 22  # mm: diâmetro do tubo da armação tubular (aparência)


def _armacao(m, bb, z0: float, za: float, zb: float, lados: dict) -> list[dict]:
    """Armação tubular cromada aparente em cada lateral com braço: dois montantes (perto da frente e
    do fundo) da metade da base até o meio do braço, ligados por uma travessa na metade da base."""
    partes = []
    zm = z0 + (za - z0) / 2
    zt = za + 0.5 * (zb - za)
    prof = 0 if m.frente[1] == "x" else 1  # índice do eixo da profundidade no bbox
    for lado, eixo in lados.items():
        f = _faixa(bb, eixo, TUBO)
        a, b = f[prof] + 0.12 * (f[prof + 2] - f[prof]), f[prof + 2] - 0.12 * (f[prof + 2] - f[prof])
        lat = (f[1 - prof] + f[3 - prof]) / 2  # centro da faixa no eixo lateral

        def ponto(pp, z):
            return [pp, lat, z] if prof == 0 else [lat, pp, z]
        # laço: montante da frente, travessa no alto (dentro do rolo), montante do fundo, travessa embaixo
        pts = [ponto(a, zm), ponto(a, zt), ponto(b, zt), ponto(b, zm)]
        p = list(f)
        p[prof], p[prof + 2] = a - TUBO / 2, b + TUBO / 2
        partes.append({"bbox": p, "z0": zm - TUBO / 2, "z1": zt + TUBO / 2, "material": "cromado", "forma": "tubo",
                       "parte": f"armacao-{lado}", "tubo": {"pontos": pts, "raio": TUBO / 2, "fechado": True}})
    return partes


def _aparar(bb, lado: str, d: float):
    """Recua em `d` mm o lado ('+x', '-x', '+y', '-y') do retângulo bb."""
    x0, y0, x1, y1 = bb
    return {"+x": [x0, y0, x1 - d, y1], "-x": [x0 + d, y0, x1, y1],
            "+y": [x0, y0, x1, y1 - d], "-y": [x0, y0 + d, x1, y1]}[lado]


def _raio(bb, z0, z1, fracao):
    return round(fracao * min(bb[2] - bb[0], bb[3] - bb[1], z1 - z0), 1)


def _sofa(m, bb, z0: float, z1: float) -> list[dict]:
    """Estofado: base em `blocos_assento` camadas + braços (faixas laterais, profundidade toda) +
    encosto entre os braços, dividido em `almofadas_encosto`. Peças com `raio` de arredondamento."""
    za = z0 + m.altura_assento.valor
    n = m.blocos_assento or 1
    hb = (za - z0) / n
    partes = []
    for i in range(n):
        b0, b1 = z0 + i * hb, z0 + (i + 1) * hb
        partes.append({"bbox": list(bb), "z0": b0, "z1": b1, "parte": "assento" if n == 1 else f"assento-{i + 1}",
                       "raio": _raio(bb, b0, b1, RAIO_BLOCO), "forma": "almofada"})
    bw = m.braco_largura.valor if m.braco_largura is not None and m.braco_largura.valor else 0
    zb = z0 + (m.braco_altura.valor if m.braco_altura and m.braco_altura.valor else z1 - z0)
    lados = {}
    for lado in (m.bracos if bw else []):
        eixo = ESQUERDA[m.frente] if lado == "esquerdo" else OPOSTO[ESQUERDA[m.frente]]
        lados[lado] = eixo
        fb = _faixa(bb, eixo, bw)
        partes.append({"bbox": fb, "z0": za, "z1": zb, "parte": f"braco-{lado}", "raio": _raio(fb, za, zb, RAIO_ROLO),
                       "forma": "rolo", "eixo": m.frente[1]})  # rolo deitado ao longo da profundidade
    if m.prof_encosto is not None and m.prof_encosto.valor:
        enc = _faixa(bb, OPOSTO[m.frente], m.prof_encosto.valor)
        for eixo in lados.values():
            enc = _aparar(enc, eixo, bw)
        k = m.almofadas_encosto or 1
        lat = 0 if ESQUERDA[m.frente][1] == "x" else 1  # índice do eixo lateral no bbox
        a, b = enc[lat], enc[lat + 2]
        passo = (b - a - FOLGA_ALMOFADAS * (k - 1)) / k
        for j in range(k):
            e = list(enc)
            e[lat], e[lat + 2] = a + j * (passo + FOLGA_ALMOFADAS), a + j * (passo + FOLGA_ALMOFADAS) + passo
            partes.append({"bbox": e, "z0": za, "z1": z1, "parte": "encosto" if k == 1 else f"encosto-{j + 1}",
                           "raio": _raio(e, za, z1, RAIO_ENCOSTO if k > 1 else RAIO_BLOCO), "forma": "almofada"})
    if m.armacao == "tubular" and lados:
        partes += _armacao(m, bb, z0, za, zb, lados)
    return partes


def _partes(m, bb, z0: float, z1: float) -> list[dict]:
    """Volumes simples. Produto com `modelo` = peças do modelo paramétrico; mesa = tampo + 4 pernas;
    sofá com forma = assento + encosto + braços; demais = caixa única."""
    if m.modelo:
        from .modelos import MODELOS, para_global
        pecas = MODELOS[m.modelo](m.largura.valor, m.profundidade.valor, m.altura.valor)
        return [para_global(pc, m.frente, bb, z0) for pc in pecas]
    if m.categoria == "sofa" and m.altura_assento is not None and m.altura_assento.valor:
        return _sofa(m, bb, z0, z1)
    if m.categoria != "mesa":
        return [{"bbox": list(bb), "z0": z0, "z1": z1}]
    from .layout import MESA_PERNA, MESA_RECUO, MESA_TAMPO
    x0, y0, x1, y1 = bb
    tampo, perna, rec = MESA_TAMPO, MESA_PERNA, MESA_RECUO
    partes = [{"bbox": [x0, y0, x1, y1], "z0": z1 - tampo, "z1": z1}]
    for px in (x0 + rec, x1 - rec - perna):
        for py in (y0 + rec, y1 - rec - perna):
            partes.append({"bbox": [px, py, px + perna, py + perna], "z0": z0, "z1": z1 - tampo})
    return partes


def cameras_nomeadas(geo: Geometria, amb_id: str, arquivo) -> list[dict]:
    """Câmeras fixas de um ambiente (`ambientes/<id>/cameras.yaml`), em coordenadas LOCAIS:

        cameras:
          - {id: sofa, pos: [400, 300, 1100], alvo: [1400, 2900, 900], lente: 16, nota: "do sofá para a mesa"}

    O id final é '<ambiente>-<id>'. Posição e alvo são escolhas de enquadramento (sem status).
    """
    import yaml
    from .geometria import deslocamento
    amb = next(a for a in geo.ambientes if a.id == amb_id)
    d, _ = deslocamento(amb)
    if d is None:
        return []
    dados = yaml.safe_load(Path(arquivo).read_text(encoding="utf-8")) or {}
    cams = []
    for c in dados.get("cameras") or []:
        falta = {"id", "pos", "alvo"} - set(c)
        if falta:
            raise ValueError(f"{arquivo}: câmera sem {sorted(falta)}")
        g = lambda p: [p[0] + d[0], p[1] + d[1], p[2]]  # noqa: E731
        cams.append({"id": f"{amb_id}-{c['id']}", "pos": g(c["pos"]), "alvo": g(c["alvo"]),
                     "lente": c.get("lente", 18), "tipo": "perspectiva", "nomeada": True})
    return cams


def _livre(pos, moveis) -> bool:
    x, y, z = pos
    return not any(m["bbox"][0] - 100 <= x <= m["bbox"][2] + 100 and m["bbox"][1] - 100 <= y <= m["bbox"][3] + 100
                   and m["z0"] <= z <= m["z1"] for m in moveis)


def cameras_ambiente(geo: Geometria, amb_id: str, altura_olho=1600, recuo=250, moveis=()) -> list[dict]:
    """Quatro vistas de canto (olho a 1,60 m mirando o canto oposto a 1,00 m) + vista de cima.

    Se o canto estiver ocupado por um móvel na altura do olho, a câmera avança pela diagonal
    (passos de 100 mm, até 1,2 m) até sair do móvel; se não conseguir, a vista é omitida.
    """
    amb = next(a for a in geo.ambientes if a.id == amb_id)
    pol, _ = poligono_global(amb)
    x0, y0, x1, y1 = pol.bounds
    cantos = {"so": (x0, y0), "se": (x1, y0), "ne": (x1, y1), "no": (x0, y1)}
    opostos = {"so": "ne", "se": "no", "ne": "so", "no": "se"}
    cams = []
    for nome, (cx, cy) in cantos.items():
        ox, oy = cantos[opostos[nome]]
        sx, sy = math.copysign(1, ox - cx), math.copysign(1, oy - cy)
        for r in range(recuo, 1201, 100):
            pos = [cx + sx * r, cy + sy * r, altura_olho]
            if _livre(pos, moveis):
                cams.append({"id": f"{amb_id}-{nome}", "pos": pos,
                             "alvo": [ox - sx * recuo, oy - sy * recuo, 1000], "lente": 14, "tipo": "perspectiva"})
                break
    # closes dos produtos com modelo 3D: câmera à frente do móvel (até 1,8 m, dentro do ambiente)
    passo = {"+x": (1, 0), "-x": (-1, 0), "+y": (0, 1), "-y": (0, -1)}
    for m in moveis:
        if m.get("ambiente") != amb_id or not m.get("modelo") or m.get("categoria") == "decor":
            continue
        bx0, by0, bx1, by1 = m["bbox"]
        mx, my, mz = (bx0 + bx1) / 2, (by0 + by1) / 2, (m["z0"] + m["z1"]) / 2
        dx, dy = passo[m["frente"]]
        dist = 1800
        while dist > 600 and not pol.buffer(-150).contains(shapely.Point(mx + dx * dist, my + dy * dist)):
            dist -= 100
        cams.append({"id": f"{amb_id}-close-{m['id']}", "pos": [mx + dx * dist, my + dy * dist, altura_olho],
                     "alvo": [mx, my, mz], "lente": 24, "tipo": "perspectiva"})
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    cams.append({"id": f"{amb_id}-planta", "pos": [cx, cy, 8000], "alvo": [cx, cy, 0],
                 "escala_orto": max(x1 - x0, y1 - y0) + 1600, "tipo": "ortografica", "sem_teto": True})
    return cams
