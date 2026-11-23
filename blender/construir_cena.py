"""Monta e renderiza a cena do apartamento no Blender a partir de cena.json.

NÃO calcula geometria: só transforma os prismas/caixas do JSON (mm) em objetos (m).

Uso (headless):
  "C:\\Program Files\\Blender Foundation\\Blender 5.3\\blender.exe" --background --python blender/construir_cena.py -- \
      <cena.json> <pasta_saida> [--cameras id1 id2 ...] [--res 1280x720] [--motor eevee|cycles] [--amostras 32]
      [--periodo dia|noite|ambos] [--exposicao 0.0]

Se o cena.json tiver `luzes` (proposta de estilo): "dia" = sol + céu, luminárias apagadas;
"noite" = só as luminárias da proposta. Arquivos: <camera>-<periodo>.png.
"""

import argparse
import datetime
import hashlib
import json
import math
import os
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

MM = 0.001
# Luz do dia (parâmetros de render, não medidas): força do céu, do sol e exposição por período.
# Um interior só recebe luz pela janela e pela porta: de dia ele pede +EV, como numa foto de interiores.
CEU_DIA, SOL_DIA = 1.0, 4.0
# O Eevee deixa a luz do céu vazar pelas paredes (sem sonda de luz assada) e já sai claro; o Cycles
# só leva luz pela janela/porta, como na realidade.
EXPOSICAO = {"CYCLES": {"dia": 3.5, "noite": 0.0}, "EEVEE": {"dia": 0.0, "noite": 0.0}}

# NENHUMA cor de projeto aqui: toda superfície/peça chega do cena.json com `acabamento`
# (resolvido pelo archtools: produto, estilo, natural ou neutro). Sem acabamento = erro de
# exportação; é desenhado no cinza de marcação abaixo e listado em relatorio.json.
MARCACAO = {"cor_id": "sem-acabamento", "hex": "#959595", "rgba": [0.3, 0.3, 0.3, 1.0],
            "metal": 0.0, "rugosidade": 0.7, "origem": "neutro"}
SEM_ACABAMENTO = []


def args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("cena")
    p.add_argument("saida")
    p.add_argument("--cameras", nargs="*", default=None)
    p.add_argument("--res", default="1280x720")
    p.add_argument("--motor", default="eevee")
    p.add_argument("--amostras", type=int, default=32)
    p.add_argument("--periodo", default="dia", choices=["dia", "noite", "ambos"])
    p.add_argument("--exposicao", type=float, default=None,
                   help="EV; padrão: CEU_EXPOSICAO do período (interior de dia pede mais exposição)")
    p.add_argument("--ceu", type=float, default=None, help="força do céu de dia (padrão CEU_DIA)")
    p.add_argument("--profundidade", action="store_true",
                   help="em vez das imagens, gera o mapa de profundidade exato por câmera (perto = branco)")
    p.add_argument("--mascaras", action="store_true",
                   help="em vez das imagens, gera uma imagem de identificação por câmera (cor única por móvel)")
    return p.parse_args(argv)


_ACAB = {}


def acabamento(d, nome):
    """Acabamento de um elemento do cena.json (chave `acabamento` ou campos no próprio item)."""
    a = d.get("acabamento") or (d if "hex" in d else None)
    if a is None:
        SEM_ACABAMENTO.append(nome)
        return MARCACAO
    return a


def _socket(colecao, ident):
    return next(s for s in colecao if s.identifier == ident)


def aplicar_textura(m, bsdf, a):
    """Monta os nós do preset `a["textura"]` (tipo + parâmetros vindos do archtools; mm).

    Só traduz parâmetros em nós: a cor base é a do acabamento; variações claras/escuras são
    derivadas dela pelo `contraste`. Coordenadas = objeto (= mundo, em m), escala física real."""
    t = a.get("textura")
    if not t or t["tipo"] == "liso":
        return
    nt, L = m.node_tree, m.node_tree.links
    coord = nt.nodes.new("ShaderNodeTexCoord").outputs["Object"]
    base = list(a["rgba"][:3])
    k = t.get("contraste", 0.1)
    escuro = [c * (1 - k) for c in base] + [1.0]
    claro = [min(1.0, c * (1 + k)) for c in base] + [1.0]

    def no(tipo, **props):
        n = nt.nodes.new(tipo)
        for chave, v in props.items():
            setattr(n, chave, v)
        return n

    def rampa(fac, c0=escuro, c1=claro):
        r = no("ShaderNodeValToRGB")
        r.color_ramp.elements[0].color, r.color_ramp.elements[1].color = c0, c1
        L.new(fac, r.inputs["Fac"])
        return r.outputs["Color"]

    def relevo(altura, forca):
        b = no("ShaderNodeBump")
        b.inputs["Strength"].default_value = forca
        if "Distance" in b.inputs:
            b.inputs["Distance"].default_value = 0.002
        L.new(altura, b.inputs["Height"])
        L.new(b.outputs["Normal"], bsdf.inputs["Normal"])

    def ruido(escala_mm, detalhe=4.0):
        n = no("ShaderNodeTexNoise")
        n.inputs["Scale"].default_value = 1000.0 / escala_mm
        n.inputs["Detail"].default_value = detalhe
        L.new(coord, n.inputs["Vector"])
        return n.outputs["Fac"]

    def veio(escala_mm, direcao="x"):
        w = no("ShaderNodeTexWave", wave_type="BANDS", bands_direction="Y" if direcao == "x" else "X")
        w.inputs["Scale"].default_value = 1000.0 / escala_mm
        w.inputs["Distortion"].default_value = 3.0
        w.inputs["Detail"].default_value = 3.0
        L.new(coord, w.inputs["Vector"])
        return w.outputs["Fac"]

    if t.get("imagem"):
        textura_imagem(nt, L, bsdf, a, t, coord, no)
        return
    tipo = t["tipo"]
    if tipo == "pintura":
        relevo(ruido(t["escala"]), t["relevo"])
    elif tipo == "madeira":
        L.new(rampa(veio(t["escala"], t.get("direcao", "x"))), bsdf.inputs["Base Color"])
    elif tipo == "reguas":
        br = no("ShaderNodeTexBrick", offset=0.5, offset_frequency=1)
        br.inputs["Scale"].default_value = 1.0
        br.inputs["Brick Width"].default_value = t["comprimento"] * MM
        br.inputs["Row Height"].default_value = t["largura"] * MM
        br.inputs["Mortar Size"].default_value = t["junta"] * MM
        br.inputs["Color1"].default_value = escuro
        br.inputs["Color2"].default_value = claro
        br.inputs["Mortar"].default_value = [c * 0.6 for c in base] + [1.0]
        L.new(coord, br.inputs["Vector"])
        mix = no("ShaderNodeMix", data_type="RGBA", blend_type="MULTIPLY")
        _socket(mix.inputs, "Factor_Float").default_value = 0.35
        L.new(br.outputs["Color"], _socket(mix.inputs, "A_Color"))
        L.new(rampa(veio(t["veio"]), [0.8, 0.8, 0.8, 1], [1, 1, 1, 1]), _socket(mix.inputs, "B_Color"))
        L.new(_socket(mix.outputs, "Result_Color"), bsdf.inputs["Base Color"])
        relevo(br.outputs["Fac"], 0.3)
    elif tipo == "cotele":
        L.new(rampa(ruido(20 * t["escala"], 2.0)), bsdf.inputs["Base Color"])
        relevo(nervuras(nt, L, coord, t, no), t["relevo"])
    elif tipo == "tecido":
        L.new(rampa(ruido(20 * t["escala"], 2.0)), bsdf.inputs["Base Color"])
        relevo(ruido(t["escala"], 8.0), t["relevo"])
    elif tipo == "couro":
        v = no("ShaderNodeTexVoronoi")
        v.inputs["Scale"].default_value = 1000.0 / t["escala"]
        L.new(coord, v.inputs["Vector"])
        relevo(v.outputs["Distance"], t["relevo"])
        L.new(rampa(ruido(40 * t["escala"], 2.0)), bsdf.inputs["Base Color"])
    elif tipo == "metal":
        r = no("ShaderNodeMapRange")
        r.inputs["To Min"].default_value = max(0.0, a["rugosidade"] - t["variacao"])
        r.inputs["To Max"].default_value = min(1.0, a["rugosidade"] + t["variacao"])
        L.new(ruido(t["escala"]), r.inputs["Value"])
        L.new(r.outputs["Result"], bsdf.inputs["Roughness"])
    elif tipo in ("folhagem", "papel"):
        L.new(rampa(ruido(t["escala"], 3.0)), bsdf.inputs["Base Color"])


_IMAGENS = {}


def nervuras(nt, L, coord, t, no):
    """Altura das nervuras do cotelê: seno de (profundidade + z) com passo `nervura` mm -> linhas
    paralelas à largura no topo e na frente do estofado (eixo da profundidade = t["eixo"])."""
    sep = no("ShaderNodeSeparateXYZ")
    L.new(coord, sep.inputs["Vector"])
    soma = no("ShaderNodeMath", operation="ADD")
    L.new(sep.outputs["X" if t.get("eixo", "x") == "x" else "Y"], soma.inputs[0])
    L.new(sep.outputs["Z"], soma.inputs[1])
    f = no("ShaderNodeMath", operation="MULTIPLY")
    f.inputs[1].default_value = 2 * math.pi * 1000.0 / t["nervura"]
    L.new(soma.outputs["Value"], f.inputs[0])
    sen = no("ShaderNodeMath", operation="SINE")
    L.new(f.outputs["Value"], sen.inputs[0])
    return sen.outputs["Value"]


def _imagem(caminho, cor):
    if caminho not in _IMAGENS:
        img = bpy.data.images.load(caminho, check_existing=True)
        img.colorspace_settings.name = "sRGB" if cor else "Non-Color"
        _IMAGENS[caminho] = img
    return _IMAGENS[caminho]


def textura_imagem(nt, L, bsdf, a, t, coord, no):
    """Textura de imagem CC0 (fase P4). A cor é a do acabamento (archtools): a imagem de cor entra só
    como variação de tom (luminância / média da imagem, puxada para 1 pelo `contraste`), mais rugosidade
    e normal. Projeção em caixa nas coordenadas do objeto (m), escala física `tamanho_mm`."""
    im = t["imagem"]
    mp = no("ShaderNodeMapping")
    esc = 1000.0 / im["tamanho_mm"]
    mp.inputs["Scale"].default_value = (esc, esc, esc)
    if t.get("direcao") == "y":  # veio/réguas ao longo de y
        mp.inputs["Rotation"].default_value = (0, 0, math.pi / 2)
    L.new(coord, mp.inputs["Vector"])

    def mapa(chave, cor):
        n = no("ShaderNodeTexImage", projection="BOX", interpolation="Linear")
        n.projection_blend = 0.25
        n.image = _imagem(im[chave], cor)
        L.new(mp.outputs["Vector"], n.inputs["Vector"])
        return n

    # tom: cor_base * (1 + k * (lum/media - 1)), k = intensidade da variação
    k = {"madeira": 1.0, "reguas": 0.8, "pintura": 0.5}.get(t["tipo"], 0.7)
    bw = no("ShaderNodeRGBToBW")
    L.new(mapa("cor", True).outputs["Color"], bw.inputs["Color"])
    var = no("ShaderNodeMath", operation="MULTIPLY_ADD")  # lum * (k/media) + (1 - k)
    var.inputs[1].default_value = k / max(im["media"], 0.05)
    var.inputs[2].default_value = 1 - k
    L.new(bw.outputs["Val"], var.inputs[0])
    mix = no("ShaderNodeMix", data_type="RGBA", blend_type="MULTIPLY")
    _socket(mix.inputs, "Factor_Float").default_value = 1.0
    _socket(mix.inputs, "A_Color").default_value = a["rgba"]
    comb = no("ShaderNodeCombineColor")
    for i in range(3):
        L.new(var.outputs["Value"], comb.inputs[i])
    L.new(comb.outputs["Color"], _socket(mix.inputs, "B_Color"))
    L.new(_socket(mix.outputs, "Result_Color"), bsdf.inputs["Base Color"])
    # rugosidade: a do acabamento, modulada pelo mapa (média ~0,5 -> fator 1)
    rg = no("ShaderNodeMath", operation="MULTIPLY")
    rg.inputs[1].default_value = 2.0 * a["rugosidade"]
    L.new(mapa("rugosidade", False).outputs["Color"], rg.inputs[0])
    lim = no("ShaderNodeClamp")
    L.new(rg.outputs["Value"], lim.inputs["Value"])
    L.new(lim.outputs["Result"], bsdf.inputs["Roughness"])
    nm = no("ShaderNodeNormalMap")
    nm.inputs["Strength"].default_value = {"pintura": 0.3, "reguas": 0.5}.get(t["tipo"], 1.0)
    L.new(mapa("normal", False).outputs["Color"], nm.inputs["Color"])
    if t.get("nervura"):
        bp = no("ShaderNodeBump")
        bp.inputs["Strength"].default_value = 0.5
        if "Distance" in bp.inputs:
            bp.inputs["Distance"].default_value = 0.0015
        L.new(nervuras(nt, L, coord, t, no), bp.inputs["Height"])
        L.new(nm.outputs["Normal"], bp.inputs["Normal"])
        L.new(bp.outputs["Normal"], bsdf.inputs["Normal"])
    else:
        L.new(nm.outputs["Normal"], bsdf.inputs["Normal"])


def material_acabamento(a, emissor_rgb=None):
    """Material a partir de um `acabamento` do cena.json (cor linear + metálico + rugosidade [+ alfa]
    [+ textura procedural])."""
    chave = (a["hex"], a["metal"], a["rugosidade"], a.get("alfa"), tuple(emissor_rgb or ()),
             json.dumps(a.get("textura"), sort_keys=True))
    if chave in _ACAB:
        return _ACAB[chave]
    m = bpy.data.materials.new(f"{a['cor_id']}-{a['hex']}" + ("-luz" if emissor_rgb else ""))
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = a["rgba"]
    bsdf.inputs["Metallic"].default_value = a["metal"]
    bsdf.inputs["Roughness"].default_value = a["rugosidade"]
    if a.get("alfa") is not None:
        bsdf.inputs["Alpha"].default_value = a["alfa"]
        for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
            if hasattr(m, attr):
                try:
                    setattr(m, attr, val)
                except TypeError:
                    pass
    aplicar_textura(m, bsdf, a)
    if emissor_rgb:
        bsdf.inputs["Emission Color"].default_value = (*emissor_rgb, 1)
        bsdf.inputs["Emission Strength"].default_value = 0.0  # ligado no período "noite"
    _ACAB[chave] = m
    return m


def colecao(nome):
    c = bpy.data.collections.get(nome) or bpy.data.collections.new(nome)
    if c.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(c)
    return c


def objeto(nome, malha, col, mat):
    ob = bpy.data.objects.new(nome, malha)
    col.objects.link(ob)
    ob.data.materials.append(mat)
    return ob


def prisma(nome, d, col, mat):
    """Extrusão de um polígono (triângulos + anéis) entre z0 e z1."""
    bm = bmesh.new()
    z0, z1 = d["z0"] * MM, d["z1"] * MM
    for t in d["tris"]:
        bm.faces.new([bm.verts.new((x * MM, y * MM, z1)) for x, y in t])
        bm.faces.new([bm.verts.new((x * MM, y * MM, z0)) for x, y in reversed(t)])
    for anel in d["aneis"]:
        n = len(anel)
        for i in range(n):
            (ax, ay), (bx, by) = anel[i], anel[(i + 1) % n]
            bm.faces.new([bm.verts.new(v) for v in (
                (ax * MM, ay * MM, z0), (bx * MM, by * MM, z0), (bx * MM, by * MM, z1), (ax * MM, ay * MM, z1))])
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0005)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(nome)
    bm.to_mesh(me)
    bm.free()
    return objeto(nome, me, col, mat)


def superficie(nome, d, col, mat):
    bm = bmesh.new()
    z = d["z"] * MM
    for t in d["tris"]:
        bm.faces.new([bm.verts.new((x * MM, y * MM, z)) for x, y in t])
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0005)
    me = bpy.data.meshes.new(nome)
    bm.to_mesh(me)
    bm.free()
    return objeto(nome, me, col, mat)


CHANFRO_PADRAO = 3  # mm: quina levemente quebrada em toda caixa (pega brilho; só aparência)


def folhas(nome, lista, col, mat):
    """Junta as folhas de um móvel numa malha só: lâmina pontuda (contorno de seno), curvada para
    baixo ao longo do comprimento, girada por rot (graus, X depois Z) e posta na base (mm)."""
    from mathutils import Euler
    bm = bmesh.new()
    N = 8
    for f in lista:
        w, comp = (t * MM for t in f["tam"])
        rot = Euler([math.radians(a) for a in f["rot"]], "XYZ").to_matrix()
        base = Vector(f["base"]) * MM
        curva, perfil = f.get("curva", 0.18), f.get("perfil", 0.75)

        def pt(x, y):
            t = y / comp
            return rot @ Vector((x, y, -curva * comp * t * t)) + base
        recortes = int(f.get("recortes", 0))
        n = N if not recortes else 6 * recortes + 6
        linhas = []  # por estação: esquerda, interna esq., meio, interna dir., direita
        for k in range(n + 1):
            t = k / n
            meia = 0.5 * w * math.sin(math.pi * t ** perfil) * (1 - 0.25 * t)
            xs = (-meia, -0.35 * meia, 0.0, 0.35 * meia, meia)
            linhas.append([bm.verts.new(pt(x, t * comp)) for x in xs])
        for k, (a, b) in enumerate(zip(linhas, linhas[1:])):
            # monstera: a cada 6 estações, uma fenda da borda até perto da nervura (faixa externa omitida)
            fenda = recortes and 3 <= k < n - 3 and k % 6 == 3
            for c in range(4):
                if fenda and c in (0, 3):
                    continue
                face = bm.faces.new([a[c], a[c + 1], b[c + 1], b[c]])
                face.smooth = True
    me = bpy.data.meshes.new(nome)
    bm.to_mesh(me)
    bm.free()
    ob = objeto(nome, me, col, mat)
    sol = ob.modifiers.new("espessura", "SOLIDIFY")
    sol.thickness = 0.0008
    return ob


def superficie_grade(nome, linhas, espessura, col, mat):
    """Superfície lisa pela grade de pontos (mm): faces entre linhas vizinhas, espessura e suavização."""
    bm = bmesh.new()
    vs = [[bm.verts.new(Vector(p) * MM) for p in linha] for linha in linhas]
    for a, b in zip(vs, vs[1:]):
        for k in range(len(a) - 1):
            f = bm.faces.new([a[k], a[k + 1], b[k + 1], b[k]])
            f.smooth = True
    me = bpy.data.meshes.new(nome)
    bm.to_mesh(me)
    bm.free()
    ob = objeto(nome, me, col, mat)
    sol = ob.modifiers.new("espessura", "SOLIDIFY")
    sol.thickness = espessura * MM
    sub = ob.modifiers.new("liso", "SUBSURF")
    sub.levels = sub.render_levels = 2
    return ob


def tubo(nome, pontos, raio, col, mat, fechado=False, lados=14):
    """Tubo de seção circular (raio mm) varrido pelos pontos (mm); quinas suavizadas pelo transporte
    paralelo do referencial. Pontas tampadas (ou fechado em anel)."""
    pts = [Vector(p) * MM for p in pontos]
    if fechado:
        pts = pts + [pts[0]]
    r = raio * MM
    bm = bmesh.new()
    tang = []
    for i in range(len(pts)):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, len(pts) - 1)]
        tang.append((b - a).normalized())
    ref = Vector((0, 0, 1)) if abs(tang[0].z) < 0.9 else Vector((1, 0, 0))
    n = tang[0].cross(ref).normalized()
    aneis = []
    for i, (p, t) in enumerate(zip(pts, tang)):
        if i:
            n = (n - t * n.dot(t)).normalized()  # transporte paralelo
        bn = t.cross(n).normalized()
        aneis.append([bm.verts.new(p + r * (math.cos(2 * math.pi * k / lados) * n + math.sin(2 * math.pi * k / lados) * bn))
                      for k in range(lados)])
    for a, b in zip(aneis, aneis[1:]):
        for k in range(lados):
            f = bm.faces.new([a[k], a[(k + 1) % lados], b[(k + 1) % lados], b[k]])
            f.smooth = True
    if not fechado:
        for anel, inv in ((aneis[0], True), (aneis[-1], False)):
            try:
                bm.faces.new(list(reversed(anel)) if inv else anel)
            except ValueError:
                pass
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(nome)
    bm.to_mesh(me)
    bm.free()
    return objeto(nome, me, col, mat)


def caixa(nome, bb, z0, z1, col, mat, forma="caixa", raio=None, eixo=None):
    """Caixa, cilindro vertical ou elipsoide inscritos na bbox (mm) entre z0 e z1.
    Caixa com `raio` (mm, vindo do archtools) sai arredondada (bevel); sem ele, chanfro mínimo."""
    x0, y0, x1, y1 = (v * MM for v in bb)
    bm = bmesh.new()
    if forma == "cilindro":
        try:
            bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=32, radius1=0.5, radius2=0.5, depth=1.0)
        except TypeError:
            bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=32, diameter1=0.5, diameter2=0.5,
                                  depth=1.0)
    elif forma == "rolo":  # cilindro deitado ao longo de `eixo`, seção elíptica inscrita na bbox
        try:
            bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=40, radius1=0.5, radius2=0.5, depth=1.0)
        except TypeError:
            bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=40, diameter1=0.5, diameter2=0.5,
                                  depth=1.0)
        for v in bm.verts:  # cilindro em z -> deita: z vira o eixo pedido
            x, y, z = v.co
            v.co = Vector((z, x, y)) if eixo == "x" else Vector((x, z, y))
        for f in bm.faces:
            f.smooth = True
    elif forma == "esfera":
        try:
            bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=16, radius=0.5)
        except TypeError:
            bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=16, diameter=0.5)
        for f in bm.faces:
            f.smooth = True
    else:
        bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector(((v.co.x + 0.5) * (x1 - x0) + x0, (v.co.y + 0.5) * (y1 - y0) + y0,
                       (v.co.z + 0.5) * (z1 - z0) * MM + z0 * MM))
    if forma in ("caixa", "almofada"):
        for f in bm.faces:
            f.smooth = True
    me = bpy.data.meshes.new(nome)
    bm.to_mesh(me)
    bm.free()
    ob = objeto(nome, me, col, mat)
    if forma in ("almofada", "rolo"):  # estofado macio: cantos bem arredondados + subdivisão
        if forma == "almofada":
            bv = ob.modifiers.new("arredondar", "BEVEL")
            bv.width = (raio or 0.12 * min(x1 - x0, y1 - y0, (z1 - z0) * MM) / MM) * MM
            bv.segments = 4
            bv.limit_method = "NONE"
            bv.use_clamp_overlap = True
        else:
            bv = ob.modifiers.new("arredondar", "BEVEL")  # pontas do rolo arredondadas
            bv.width = 0.18 * min(x1 - x0, y1 - y0, (z1 - z0) * MM)
            bv.segments = 6
            bv.limit_method = "ANGLE"
            bv.use_clamp_overlap = True
        sub = ob.modifiers.new("macio", "SUBSURF")
        sub.levels = sub.render_levels = 2
        return ob
    if forma == "caixa":
        r = raio if raio else min(CHANFRO_PADRAO, 0.25 * min(x1 - x0, y1 - y0, (z1 - z0) * MM) / MM)
        bv = ob.modifiers.new("arredondar", "BEVEL")
        bv.width = r * MM
        bv.segments = 8 if raio else 2
        bv.limit_method = "NONE"
        bv.use_clamp_overlap = True
        bv.harden_normals = True
    return ob


def camera(c, col):
    cam = bpy.data.cameras.new(c["id"])
    ob = bpy.data.objects.new(c["id"], cam)
    col.objects.link(ob)
    ob.location = Vector(c["pos"]) * MM
    direcao = Vector(c["alvo"]) * MM - ob.location
    ob.rotation_euler = direcao.to_track_quat("-Z", "Y").to_euler()
    if c["tipo"] == "ortografica":
        cam.type = "ORTHO"
        cam.ortho_scale = c["escala_orto"] * MM
    else:
        cam.lens = c["lente"]
    cam.clip_end = 100
    return ob


def motor(cena_bpy, nome, amostras):
    if nome == "cycles":
        cena_bpy.render.engine = "CYCLES"
        cena_bpy.cycles.device = "CPU"
        cena_bpy.cycles.samples = amostras
        cena_bpy.cycles.use_denoising = True
        return "CYCLES"
    for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            cena_bpy.render.engine = eng
            ev = cena_bpy.eevee
            if hasattr(ev, "taa_render_samples"):
                ev.taa_render_samples = amostras
            # luz rebatida e oclusão (sem isso a luz do céu ilumina o quarto por igual e tudo fica chapado)
            for prop, val in (("use_raytracing", True), ("ray_tracing_method", "SCREEN"), ("use_fast_gi", True),
                              ("fast_gi_method", "GLOBAL_ILLUMINATION"), ("fast_gi_distance", 1.5),
                              ("fast_gi_resolution", "2"), ("use_shadows", True), ("shadow_ray_count", 2),
                              ("shadow_step_count", 12)):
                if hasattr(ev, prop):
                    try:
                        setattr(ev, prop, val)
                    except (TypeError, ValueError) as erro:
                        print(f"aviso eevee {prop}: {erro}")
            return eng
        except TypeError:
            continue
    raise RuntimeError("Eevee indisponível")


def _hash(p):
    """Mesmo hash do archtools.manifesto (sha256, 16 hex; CRLF->LF em texto)."""
    dados = Path(p).read_bytes()
    if Path(p).suffix.lower() in {".yaml", ".yml", ".md", ".json", ".py", ".txt", ".svg", ".csv"}:
        dados = dados.replace(b"\r\n", b"\n")
    return hashlib.sha256(dados).hexdigest()[:16]


def manifesto(saida, gerados, cena, args_txt):
    """Atualiza saida/manifest.json (mesmo formato do archtools): cada arquivo gerado <- cena.json."""
    arq = saida / "manifest.json"
    man = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {"versao": 1, "saidas": {}}
    cena_rel = Path(os.path.relpath(Path(cena).resolve(), Path.cwd())).as_posix()
    agora = datetime.datetime.now().isoformat(timespec="seconds")
    for g in gerados:
        man["saidas"][Path(g).resolve().relative_to(saida).as_posix()] = {
            "entradas": {cena_rel: _hash(cena)}, "comando": f"blender/construir_cena.py -- {args_txt}",
            "gerado_em": agora, "archtools": "blender " + bpy.app.version_string}
    man["saidas"] = dict(sorted(man["saidas"].items()))
    arq.write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")


def cor_id(i):
    """Cor (bytes sRGB) que identifica o móvel de índice i na imagem de máscaras."""
    return ((i * 53) % 210 + 30, (i * 97) % 210 + 30, (i * 151) % 210 + 30)


def profundidade(sc, cams, saida, c_cam, mundo, perto=0.3, longe=5.0):
    """Mapa de profundidade exato da cena (perto = branco, longe = preto), uma imagem por câmera:
    material de emissão com a distância ao plano da câmera (View Z Depth) em todas as malhas."""
    m = bpy.data.materials.new("profundidade")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    cam = nt.nodes.new("ShaderNodeCameraData")
    faixa = nt.nodes.new("ShaderNodeMapRange")
    faixa.inputs["From Min"].default_value = perto
    faixa.inputs["From Max"].default_value = longe
    faixa.inputs["To Min"].default_value = 1.0
    faixa.inputs["To Max"].default_value = 0.0
    em = nt.nodes.new("ShaderNodeEmission")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(cam.outputs["View Z Depth"], faixa.inputs["Value"])
    nt.links.new(faixa.outputs["Result"], em.inputs["Strength"])
    em.inputs["Color"].default_value = (1, 1, 1, 1)
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    for ob in bpy.data.objects:
        if ob.type == "LIGHT":
            ob.hide_render = True
        elif ob.type == "MESH":
            ob.data.materials.clear()
            ob.data.materials.append(m)
    mundo.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.0
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 4
    sc.cycles.use_denoising = False
    sc.cycles.max_bounces = 0
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.view_settings.exposure = 0.0
    sc.render.image_settings.file_format = "PNG"
    for c in cams:
        sc.camera = bpy.data.objects.get(c["id"]) or camera(c, c_cam)
        sc.render.filepath = str(saida / f"{c['id']}-profundidade.png")
        bpy.ops.render.render(write_still=True)
        print(f"PROFUNDIDADE_OK {c['id']} -> {sc.render.filepath}")


def mascaras(sc, dados, cams, saida, c_cam, mundo):
    """Uma imagem por câmera em que cada móvel tem uma cor única e plana (emissão, sem luz, sem
    anti-aliasing) + mascaras.json {câmera: {móvel: [r, g, b]}}. Arquitetura sai preta."""
    def arquitetura(nome):
        """Região da arquitetura de um objeto sem móvel (paredes pintadas por índice, teto, piso,
        vidro da janela, espessura das paredes nos vãos; o resto, visto pelos vãos, é "fora")."""
        import re
        m = re.match(r"pintura-([\w-]+)-(\d+)$", nome)
        if m:
            return f"@{m.group(1)}:parede-{m.group(2)}"
        for pref, chave in (("teto-", "teto"), ("vidro-janela-", "janela")):
            if nome.startswith(pref):
                return f"@{nome[len(pref):]}:{chave}"
        m = re.match(r"piso-([\w-]+?)(-cor)?$", nome)
        if m:
            return f"@{m.group(1)}:piso"
        if nome.startswith("parede-"):
            return "@batente"
        return "@fora"

    ids = [m["id"] for m in dados["moveis"]]
    arqs = sorted({arquitetura(ob.name) for ob in bpy.data.objects if ob.type == "MESH" and ob.get("movel") is None})
    cores = {mid: cor_id(i + 1) for i, mid in enumerate(ids + arqs)}
    assert len(set(cores.values())) == len(cores), "cores de máscara repetidas"

    def emissao(nome, rgb_bytes):
        m = bpy.data.materials.new(nome)
        m.use_nodes = True
        nt = m.node_tree
        nt.nodes.clear()
        em = nt.nodes.new("ShaderNodeEmission")
        lin = [((v / 255 + 0.055) / 1.055) ** 2.4 if v / 255 > 0.04045 else v / 255 / 12.92 for v in rgb_bytes]
        em.inputs["Color"].default_value = (*lin, 1)
        em.inputs["Strength"].default_value = 1.0
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
        return m

    mats = {mid: emissao(f"id-{mid}", c) for mid, c in cores.items()}
    preto = emissao("id-fundo", (0, 0, 0))
    for ob in bpy.data.objects:
        if ob.type == "LIGHT":
            ob.hide_render = True
        elif ob.type == "MESH":
            mt = mats.get(ob.get("movel")) or mats.get(arquitetura(ob.name), preto)
            ob.data.materials.clear()
            ob.data.materials.append(mt)
    mundo.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.0
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 1
    sc.cycles.use_denoising = False
    sc.cycles.max_bounces = 0
    sc.cycles.filter_width = 0.01
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.view_settings.exposure = 0.0
    sc.view_settings.gamma = 1.0
    sc.render.image_settings.file_format = "PNG"
    mapa = {}
    for c in cams:
        sc.camera = bpy.data.objects.get(c["id"]) or camera(c, c_cam)
        sc.render.filepath = str(saida / f"{c['id']}-ids.png")
        bpy.ops.render.render(write_still=True)
        mapa[c["id"]] = {mid: list(cor) for mid, cor in cores.items()}
        print(f"MASCARA_OK {c['id']} -> {sc.render.filepath}")
    (saida / "mascaras.json").write_text(json.dumps(mapa, ensure_ascii=False), encoding="utf-8")


def main():
    a = args()
    dados = json.loads(Path(a.cena).read_text(encoding="utf-8"))
    saida = Path(a.saida).resolve()  # Blender interpreta caminhos relativos a partir do .blend
    saida.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene

    c_par, c_cor, c_pis, c_tet = colecao("paredes"), colecao("recortes"), colecao("pisos"), colecao("tetos")
    c_mov, c_cam, c_ext = colecao("moveis"), colecao("cameras"), colecao("externo")

    def mat(d, nome):
        return material_acabamento(acabamento(d, nome))

    paredes = [prisma(p["id"], p, c_par, mat(p, p["id"])) for p in dados["paredes"]]
    for rv in dados.get("revestimentos", []):
        ob = (prisma if "aneis" in rv else superficie)(rv["id"], rv, c_par, material_acabamento(rv))
        if rv.get("recortar"):
            paredes.append(ob)
    for r in dados["recortes"]:
        prisma(f"recorte-{r['id']}", r, c_cor, material_acabamento(MARCACAO))  # oculto: só subtrai
    for par in paredes:
        mod = par.modifiers.new("aberturas", "BOOLEAN")
        mod.operation = "DIFFERENCE"
        mod.operand_type = "COLLECTION"
        mod.collection = c_cor
        mod.solver = "EXACT"
        bpy.context.view_layer.objects.active = par
        bpy.ops.object.modifier_apply(modifier=mod.name)
    c_cor.hide_render = True
    c_cor.hide_viewport = True

    for v in dados["vidros"]:
        ob = prisma(v["id"], v, c_par, mat(v, v["id"]))
        if hasattr(ob, "visible_shadow"):
            ob.visible_shadow = False  # o vidro deixa passar o sol e o céu
    for p in dados["pisos"]:
        superficie(p["id"], p, c_pis, mat(p, p["id"]))
    for t in dados["tetos"]:
        (prisma if "aneis" in t else superficie)(t["id"], t, c_tet, mat(t, t["id"]))
    for c in dados["cercamentos"]:
        prisma(c["id"], c, c_ext, mat(c, c["id"]))
    luzes_dados = dados.get("luzes", [])
    emissores = {lz["movel"]: lz["rgb"] for lz in luzes_dados if lz.get("emissor")}
    com_luz = {lz["movel"] for lz in luzes_dados}
    for m in dados["moveis"]:
        partes = m.get("partes") or [m]
        tem_cupula = any(pt.get("material") == "cupula" for pt in partes)
        grupos_folha = {}
        for i, pt in enumerate(partes):
            if pt.get("forma") == "folha":  # juntadas numa malha por material (abaixo)
                grupos_folha.setdefault(json.dumps(pt.get("acabamento"), sort_keys=True), []).append((i, pt))
                continue
            brilha = not tem_cupula or pt.get("material") == "cupula"
            mt = material_acabamento(acabamento(pt, f"{m['id']}-{i}"), emissores.get(m["id"]) if brilha else None)
            if pt.get("forma") == "superficie":
                ob = superficie_grade(f"{m['id']}-{i}", pt["superficie"]["linhas"], pt["superficie"]["espessura"],
                                      c_mov, mt)
            elif pt.get("forma") == "tubo":
                ob = tubo(f"{m['id']}-{i}", pt["tubo"]["pontos"], pt["tubo"]["raio"], c_mov, mt,
                          pt["tubo"].get("fechado", False))
            else:
                ob = caixa(f"{m['id']}-{i}", pt["bbox"], pt["z0"], pt["z1"], c_mov, mt, pt.get("forma", "caixa"),
                           pt.get("raio"), pt.get("eixo"))
            ob["movel"] = m["id"]
            if m["id"] in com_luz and hasattr(ob, "visible_shadow"):
                ob.visible_shadow = False  # a cúpula não bloqueia a própria lâmpada
        for g, itens in grupos_folha.items():
            i0, pt0 = itens[0]
            mt = material_acabamento(acabamento(pt0, f"{m['id']}-{i0}"))
            folhas(f"{m['id']}-folhas-{i0}", [pt["folha"] for _, pt in itens], c_mov, mt)["movel"] = m["id"]

    luzes_obs = []
    for lz in luzes_dados:
        tipo = {"spot": "SPOT", "linha": "AREA"}.get(lz["tipo"], "POINT")
        ld = bpy.data.lights.new(lz["id"], tipo)
        ld.energy = lz["intensidade_w"]
        ld.color = lz["rgb"]
        if tipo == "AREA":  # fita de LED: retângulo estreito no comprimento dado pelo archtools
            ld.shape = "RECTANGLE"
            ld.size = lz["comprimento"] * MM
            ld.size_y = 0.012
        else:
            ld.shadow_soft_size = 0.04
        if tipo == "SPOT":
            ld.spot_size = math.radians(lz.get("abertura", 70))
            ld.spot_blend = 0.6
        ob = bpy.data.objects.new(lz["id"], ld)
        sc.collection.objects.link(ob)
        ob.location = Vector(lz["pos"]) * MM  # spot e área apontam para -z (para baixo) por padrão
        if tipo == "AREA" and lz.get("eixo") == "y":
            ob.rotation_euler = (0, 0, math.pi / 2)
        if tipo == "SPOT" and lz.get("alvo"):  # spot direcionado (ex.: trilho): aponta para o alvo
            ob.rotation_euler = (Vector(lz["alvo"]) * MM - ob.location).to_track_quat("-Z", "Y").to_euler()
        luzes_obs.append(ob)

    # luz: sol genérico (orientação real desconhecida) + céu
    sol = bpy.data.objects.new("sol", bpy.data.lights.new("sol", "SUN"))
    sc.collection.objects.link(sol)
    sol.data.energy = 4.0
    sol.data.angle = math.radians(5)
    sol.rotation_euler = (math.radians(50), 0, math.radians(180))  # vem de +y (lado das janelas do fundo)
    mundo = bpy.data.worlds.new("ceu")
    sc.world = mundo
    mundo.use_nodes = True
    mundo.node_tree.nodes["Background"].inputs["Color"].default_value = (0.75, 0.82, 0.95, 1)
    mundo.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.5
    luz = bpy.data.objects.new("luz-teto", bpy.data.lights.new("luz-teto", "AREA"))
    sc.collection.objects.link(luz)
    luz.data.energy = 40
    luz.data.size = 1.2

    eng = motor(sc, a.motor, a.amostras)
    w, h = (int(v) for v in a.res.lower().split("x"))
    sc.render.resolution_x, sc.render.resolution_y = w, h
    sc.render.image_settings.file_format = "PNG"
    for look in ("AgX - Medium High Contrast", "Medium High Contrast"):
        try:
            sc.view_settings.look = look
            break
        except TypeError:
            continue
    sc.view_settings.view_transform = "AgX" if "AgX" in [i.identifier for i in
                                                          sc.view_settings.bl_rna.properties["view_transform"].enum_items] else "Filmic"

    fundo = mundo.node_tree.nodes["Background"].inputs

    def periodo(nome):
        noite = nome == "noite"
        sol.hide_render = noite
        ceu = a.ceu if a.ceu is not None else CEU_DIA
        fundo["Strength"].default_value = 0.02 if noite else ceu
        sol.data.energy = SOL_DIA
        ev = EXPOSICAO["CYCLES" if eng == "CYCLES" else "EEVEE"][nome]
        sc.view_settings.exposure = a.exposicao if a.exposicao is not None else ev
        fundo["Color"].default_value = (0.05, 0.07, 0.12, 1) if noite else (0.75, 0.82, 0.95, 1)
        luz.hide_render = noite or bool(luzes_obs)  # luz de apoio genérica só sem proposta de luz
        for ob in luzes_obs:
            ob.hide_render = not noite
        for m in _ACAB.values():
            if m.name.endswith("-luz"):
                m.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 4.0 if noite else 0.0

    periodos = ["dia", "noite"] if a.periodo == "ambos" else [a.periodo]
    sufixo = bool(luzes_obs) or a.periodo != "dia"
    cams = [c for c in dados["cameras"] if a.cameras is None or c["id"] in a.cameras]
    if a.mascaras:
        mascaras(sc, dados, cams, saida, c_cam, mundo)
        return
    if a.profundidade:
        profundidade(sc, cams, saida, c_cam, mundo)
        return
    gerados = []
    for per in periodos:
        periodo(per)
        for c in cams:
            ob = bpy.data.objects.get(c["id"]) or camera(c, c_cam)
            sc.camera = ob
            alvo = Vector(c["alvo"]) * MM
            luz.location = (alvo.x, alvo.y, dados["pe_direito"] * MM - 0.05)
            c_tet.hide_render = bool(c.get("sem_teto"))
            for rv in dados.get("revestimentos", []):
                if rv["id"].startswith("teto-"):
                    bpy.data.objects[rv["id"]].hide_render = bool(c.get("sem_teto"))
            sc.render.filepath = str(saida / (f"{c['id']}-{per}.png" if sufixo else f"{c['id']}.png"))
            bpy.ops.render.render(write_still=True)
            gerados.append(Path(sc.render.filepath))
            print(f"RENDER_OK {c['id']} {per} -> {sc.render.filepath} ({eng})")
    c_tet.hide_render = False
    bpy.ops.wm.save_as_mainfile(filepath=str(saida / "modelo.blend"))
    print(f"BLEND_OK {saida / 'modelo.blend'}")
    gerados.append(saida / "modelo.blend")
    relatorio = {"cena": str(a.cena), "motor": eng, "suposicoes": dados.get("suposicoes", []),
                 "sem_acabamento_no_json": SEM_ACABAMENTO,
                 "neutros": sorted({m["id"] for m in dados["moveis"]
                                    for pt in (m.get("partes") or [m])
                                    if (pt.get("acabamento") or MARCACAO).get("origem") == "neutro"})}
    (saida / "relatorio.json").write_text(json.dumps(relatorio, ensure_ascii=False, indent=1), encoding="utf-8")
    gerados.append(saida / "relatorio.json")
    manifesto(saida, gerados, Path(a.cena), " ".join(sys.argv[sys.argv.index("--") + 1:]) if "--" in sys.argv else "")
    if SEM_ACABAMENTO:
        print(f"AVISO: {len(SEM_ACABAMENTO)} elemento(s) sem acabamento no cena.json (cinza de marcação)")


main()
