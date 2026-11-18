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
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

MM = 0.001

CORES = {  # cores neutras (acabamentos reais desconhecidos)
    "parede": (0.92, 0.91, 0.89, 1), "teto": (0.95, 0.95, 0.95, 1),
    "piso_interno": (0.62, 0.50, 0.38, 1), "piso_varanda": (0.70, 0.70, 0.68, 1),
    "piso_externo": (0.35, 0.55, 0.30, 1), "piso_tecnico": (0.6, 0.6, 0.6, 1),
    "cercamento": (0.20, 0.40, 0.22, 1), "vidro": (0.8, 0.9, 1.0, 1),
    "sofa": (0.18, 0.27, 0.50, 1), "mesa": (0.55, 0.40, 0.26, 1), "estante": (0.15, 0.15, 0.15, 1),
    "aparador": (0.45, 0.30, 0.18, 1), "prateleira": (0.35, 0.35, 0.35, 1),
    "equipamento": (0.08, 0.08, 0.08, 1), "outro": (0.7, 0.7, 0.7, 1),
    # materiais dos modelos de produto (archtools.modelos)
    "metal_preto": (0.02, 0.02, 0.02, 1), "madeira_clara": (0.72, 0.56, 0.40, 1),
    "preto_brilho": (0.01, 0.01, 0.01, 1), "cromado": (0.85, 0.85, 0.87, 1),
    "nogueira": (0.30, 0.18, 0.11, 1), "madeira_pes": (0.76, 0.58, 0.40, 1), "discos": (0.55, 0.47, 0.36, 1),
    "vaso": (0.55, 0.53, 0.50, 1), "caule": (0.30, 0.22, 0.12, 1), "folhagem": (0.13, 0.35, 0.12, 1),
    "tela": (0.03, 0.04, 0.06, 1), "tecido_preto": (0.04, 0.04, 0.045, 1),
}
ACABAMENTO = {  # (metálico, rugosidade)
    "metal_preto": (0.8, 0.45), "cromado": (1.0, 0.12), "preto_brilho": (0.0, 0.15),
    "nogueira": (0.0, 0.5), "madeira_clara": (0.0, 0.55), "madeira_pes": (0.0, 0.5),
    "tela": (0.0, 0.08), "tecido_preto": (0.0, 0.85), "folhagem": (0.0, 0.7),
}


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
    p.add_argument("--exposicao", type=float, default=0.0)
    return p.parse_args(argv)


def material(nome, cor, vidro=False):
    m = bpy.data.materials.get(nome) or bpy.data.materials.new(nome)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = cor
    metal, rug = ACABAMENTO.get(nome, (0.0, 0.05 if vidro else 0.6))
    bsdf.inputs["Roughness"].default_value = rug
    bsdf.inputs["Metallic"].default_value = metal
    if vidro:
        bsdf.inputs["Alpha"].default_value = 0.15
        for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
            if hasattr(m, attr):
                try:
                    setattr(m, attr, val)
                except TypeError:
                    pass
    return m


_ACAB = {}


def material_acabamento(a, emissor_rgb=None):
    """Material a partir de um `acabamento` do cena.json (cor linear + metálico + rugosidade)."""
    chave = (a["hex"], a["metal"], a["rugosidade"], tuple(emissor_rgb or ()))
    if chave in _ACAB:
        return _ACAB[chave]
    m = bpy.data.materials.new(f"{a['cor_id']}-{a['hex']}" + ("-luz" if emissor_rgb else ""))
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = a["rgba"]
    bsdf.inputs["Metallic"].default_value = a["metal"]
    bsdf.inputs["Roughness"].default_value = a["rugosidade"]
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


def caixa(nome, bb, z0, z1, col, mat, forma="caixa"):
    """Caixa, cilindro vertical ou elipsoide inscritos na bbox (mm) entre z0 e z1."""
    x0, y0, x1, y1 = (v * MM for v in bb)
    bm = bmesh.new()
    if forma == "cilindro":
        try:
            bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=32, radius1=0.5, radius2=0.5, depth=1.0)
        except TypeError:
            bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=32, diameter1=0.5, diameter2=0.5,
                                  depth=1.0)
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
    me = bpy.data.meshes.new(nome)
    bm.to_mesh(me)
    bm.free()
    return objeto(nome, me, col, mat)


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
            if hasattr(cena_bpy.eevee, "taa_render_samples"):
                cena_bpy.eevee.taa_render_samples = amostras
            return eng
        except TypeError:
            continue
    raise RuntimeError("Eevee indisponível")


def main():
    a = args()
    dados = json.loads(Path(a.cena).read_text(encoding="utf-8"))
    saida = Path(a.saida).resolve()  # Blender interpreta caminhos relativos a partir do .blend
    saida.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene

    mats = {k: material(k, v, vidro=(k == "vidro")) for k, v in CORES.items()}
    c_par, c_cor, c_pis, c_tet = colecao("paredes"), colecao("recortes"), colecao("pisos"), colecao("tetos")
    c_mov, c_cam, c_ext = colecao("moveis"), colecao("cameras"), colecao("externo")

    paredes = [prisma(p["id"], p, c_par, mats["parede"]) for p in dados["paredes"]]
    for rv in dados.get("revestimentos", []):
        ob = (prisma if "aneis" in rv else superficie)(rv["id"], rv, c_par, material_acabamento(rv))
        if rv.get("recortar"):
            paredes.append(ob)
    for r in dados["recortes"]:
        prisma(f"recorte-{r['id']}", r, c_cor, mats["outro"])
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
        prisma(v["id"], v, c_par, mats["vidro"])
    for p in dados["pisos"]:
        superficie(p["id"], p, c_pis, mats.get(f"piso_{p['tipo']}", mats["outro"]))
    for t in dados["tetos"]:
        (prisma if "aneis" in t else superficie)(t["id"], t, c_tet, mats["teto"])
    for c in dados["cercamentos"]:
        prisma(c["id"], c, c_ext, mats["cercamento"])
    luzes_dados = dados.get("luzes", [])
    emissores = {lz["movel"]: lz["rgb"] for lz in luzes_dados if lz.get("emissor")}
    com_luz = {lz["movel"] for lz in luzes_dados}
    for m in dados["moveis"]:
        partes = m.get("partes") or [m]
        tem_cupula = any(pt.get("material") == "cupula" for pt in partes)
        for i, pt in enumerate(partes):
            if "acabamento" in pt:
                brilha = not tem_cupula or pt.get("material") == "cupula"
                mat = material_acabamento(pt["acabamento"], emissores.get(m["id"]) if brilha else None)
            else:
                mat = mats.get(pt.get("material") or m["categoria"], mats["outro"])
            ob = caixa(f"{m['id']}-{i}", pt["bbox"], pt["z0"], pt["z1"], c_mov, mat, pt.get("forma", "caixa"))
            if m["id"] in com_luz and hasattr(ob, "visible_shadow"):
                ob.visible_shadow = False  # a cúpula não bloqueia a própria lâmpada

    luzes_obs = []
    for lz in luzes_dados:
        tipo = "SPOT" if lz["tipo"] == "spot" else "POINT"
        ld = bpy.data.lights.new(lz["id"], tipo)
        ld.energy = lz["intensidade_w"]
        ld.color = lz["rgb"]
        ld.shadow_soft_size = 0.04
        if tipo == "SPOT":
            ld.spot_size = math.radians(70)
            ld.spot_blend = 0.6
        ob = bpy.data.objects.new(lz["id"], ld)
        sc.collection.objects.link(ob)
        ob.location = Vector(lz["pos"]) * MM  # spot aponta para -z (para baixo) por padrão
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

    sc.view_settings.exposure = a.exposicao
    fundo = mundo.node_tree.nodes["Background"].inputs

    def periodo(nome):
        noite = nome == "noite"
        sol.hide_render = noite
        fundo["Strength"].default_value = 0.02 if noite else 0.5
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
            print(f"RENDER_OK {c['id']} {per} -> {sc.render.filepath} ({eng})")
    c_tet.hide_render = False
    bpy.ops.wm.save_as_mainfile(filepath=str(saida / "modelo.blend"))
    print(f"BLEND_OK {saida / 'modelo.blend'}")


main()
