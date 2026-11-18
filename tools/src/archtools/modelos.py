"""Modelos 3D paramétricos de produtos específicos (só aparência; não afetam validações).

Cada modelo devolve peças no referencial do PRODUTO, olhando-o de frente:
  u: 0 (esquerda de quem olha) .. largura
  v: 0 (frente) .. profundidade
  z: 0 (piso) .. altura
Proporções internas (pés, gaveta, prateleiras) foram estimadas nas fotos de referência
enviadas pelo usuário em 2026-11-17 — são aproximações visuais.
"""

from __future__ import annotations


def _p(u0, u1, v0, v1, z0, z1, mat, forma="caixa"):
    """Peça: caixa, cilindro (vertical, elíptico na bbox) ou esfera (elipsoide na bbox)."""
    return {"u": [u0, u1], "v": [v0, v1], "z": [z0, z1], "material": mat, "forma": forma}


def _cil(cu, cv, diam, z0, z1, mat):
    return _p(cu - diam / 2, cu + diam / 2, cv - diam / 2, cv + diam / 2, z0, z1, mat, "cilindro")


def estante_industrial(w, d, h):
    """Quadro de tubo metálico preto (laterais em quadro) + 5 prateleiras de madeira clara.
    Prateleiras a ~13%, 32%, 51%, 70% e 89% da altura (medido na foto)."""
    t, e = 25, 20  # tubo e espessura da prateleira
    pecas = []
    for u0 in (0, w - t):  # quadros laterais
        for v0 in (0, d - t):
            pecas.append(_p(u0, u0 + t, v0, v0 + t, 0, h, "metal_preto"))
        for z0 in (0, h - t):
            pecas.append(_p(u0, u0 + t, 0, d, z0, z0 + t, "metal_preto"))
    for frac in (0.128, 0.317, 0.507, 0.696, 0.886):
        z = round(frac * h)
        pecas.append(_p(0, w, 0, d, z, z + e, "madeira_clara"))
        for u0 in (0, w - t):
            pecas.append(_p(u0, u0 + t, 0, d, z - t, z, "metal_preto"))  # travessa sob a prateleira
    return pecas


def frigobar_retro(w, d, h):
    """Corpo preto brilhante sobre 4 pés cromados (~21% da altura) e puxador vertical cromado
    à esquerda da porta (dobradiça à direita), como na foto."""
    pe = round(0.21 * h)
    corpo = h - pe
    pecas = [_p(0, w, 0, d, pe, h, "preto_brilho")]
    pecas.append(_p(0.28 * w, 0.28 * w + 18, -22, 0, h - 0.48 * corpo, h - 0.15 * corpo, "cromado"))
    for u0 in (35, w - 65):
        for v0 in (35, d - 65):
            pecas.append(_p(u0, u0 + 30, v0, v0 + 30, 0, pe, "cromado"))
    return pecas


def rack_vinil_norvege(w, d, h):
    """Rack em nogueira: metade esquerda = gaveta + 4 nichos de LPs; metade direita = nicho aberto
    + 2 portas. 6 pés cônicos de madeira clara (~23% da altura). Proporções da foto."""
    pe, c = round(0.23 * h), 18  # pés e espessura das chapas
    z0, z1 = pe, h
    meio = w / 2
    zg = z1 - c - round(0.36 * (z1 - z0))  # base da gaveta / prateleira do nicho
    pecas = [
        _p(0, w, 0, d, z0, z0 + c, "nogueira"), _p(0, w, 0, d, z1 - c, z1, "nogueira"),       # base, tampo
        _p(0, c, 0, d, z0, z1, "nogueira"), _p(w - c, w, 0, d, z0, z1, "nogueira"),           # laterais
        _p(0, w, d - 6, d, z0, z1, "nogueira"),                                                # fundo
        _p(meio - c / 2, meio + c / 2, 0, d, z0, z1, "nogueira"),                              # divisória central
        _p(c, meio - c / 2, 0, d, zg - c, zg, "nogueira"),                                     # piso da gaveta
        _p(meio + c / 2, w - c, 0, d, zg - c, zg, "nogueira"),                                 # prateleira do nicho
        _p(c, meio - c / 2, -c, 0, zg, z1 - c, "nogueira"),                                    # frente da gaveta
        _p((c + meio) / 2 - 60, (c + meio) / 2 + 60, -c - 15, -c, z1 - c - 60, z1 - c - 40, "cromado"),
    ]
    vao = (meio - c / 2 - c) / 4  # 4 nichos de LP
    for k in range(1, 4):
        u = c + k * vao
        pecas.append(_p(u - c / 2, u + c / 2, 0, d - 6, z0 + c, zg - c, "nogueira"))
    for k in range(4):  # discos nos nichos
        u = c + k * vao
        pecas.append(_p(u + c / 2 + 15, u + vao - c / 2 - 15, 30, d - 30, z0 + c, min(zg - c - 20, z0 + c + 315),
                        "discos"))
    folha = (w - c - (meio + c / 2)) / 2
    for k in range(2):  # portas
        u0 = meio + c / 2 + k * folha
        pecas.append(_p(u0 + 1.5, u0 + folha - 1.5, -c, 0, z0 + c, zg - c, "nogueira"))
        ux = u0 + folha - 40 if k == 0 else u0 + 22
        pecas.append(_p(ux, ux + 18, -c - 15, -c, (z0 + zg) / 2 - 60, (z0 + zg) / 2 + 60, "cromado"))
    for u in (60, meio, w - 60):
        for v in (40, d - 40):
            pecas.append(_p(u - 18, u + 18, v - 18, v + 18, 0, pe, "madeira_pes"))
    return pecas


def vaso_planta(w, d, h):
    """Vaso cilíndrico (~76% da largura, 35% da altura) com folhagem em volume elipsoidal."""
    dv = 0.76 * min(w, d)
    hv = 0.35 * h
    return [_cil(w / 2, d / 2, dv, 0, hv, "vaso"),
            _cil(w / 2, d / 2, 30, hv, 0.55 * h, "caule"),
            _p(0, w, 0, d, 0.42 * h, h, "folhagem", "esfera")]


def monitor_ultrawide(w, d, h):
    """Monitor 21:9 sobre pedestal. w = largura do painel; d = profundidade da base;
    h = altura total sobre o tampo. Painel começa a 120 mm do tampo (pedestal)."""
    base_z, painel_z0, esp = 18, 120, 50
    vp = 0.55 * d  # painel atrás do centro da base (a tela olha para v = 0)
    return [_p(w / 2 - 130, w / 2 + 130, 0.1 * d, 0.9 * d, 0, base_z, "metal_preto"),
            _p(w / 2 - 30, w / 2 + 30, vp + esp, vp + esp + 40, base_z, painel_z0 + 150, "metal_preto"),
            _p(0, w, vp, vp + esp, painel_z0, h, "preto_brilho"),
            _p(8, w - 8, vp - 2, vp, painel_z0 + 8, h - 8, "tela")]


def cadeira_escritorio(w, d, h):
    """Cadeira giratória: base estrela (aprox. disco), coluna, assento, encosto alto, apoio de
    cabeça e braços. A frente (v = 0) é para onde a pessoa sentada olha."""
    za = 0.37 * h  # altura do assento ~ 46 cm para h = 1250
    return [_cil(w / 2, d / 2, min(w, d) - 40, 30, 60, "metal_preto"),
            _cil(w / 2, d / 2, 60, 60, za - 60, "metal_preto"),
            _p(90, w - 90, 60, d - 70, za - 60, za, "tecido_preto"),
            _p(110, w - 110, d - 120, d - 40, za + 40, h - 160, "tecido_preto"),
            _p(w / 2 - 130, w / 2 + 130, d - 110, d - 40, h - 150, h, "tecido_preto"),
            _p(40, 90, 140, d - 180, za + 160, za + 200, "metal_preto"),
            _p(w - 90, w - 40, 140, d - 180, za + 160, za + 200, "metal_preto"),
            _p(55, 75, d / 2 - 20, d / 2 + 20, za, za + 160, "metal_preto"),
            _p(w - 75, w - 55, d / 2 - 20, d / 2 + 20, za, za + 160, "metal_preto")]


# ------------------------------------------------------------------ luminárias
# Materiais: "estrutura" (haste/base) e "cupula" (difusor). A luz do render fica no centro da
# primeira peça "cupula" (spot: na base dela). Formas/braços são ilustrativos (produto a escolher).

def pendente_esfera(w, d, h):
    """Pendente globo/papel: esfera inscrita na bbox (o fio até a laje é acrescentado pela cena)."""
    return [_p(0, w, 0, d, 0, h, "cupula", "esfera")]


def luminaria_arco(w, d, h):
    """Base circular + haste vertical; braço sobe até o topo e avança (750 mm para a esquerda de
    quem olha a frente, 350 mm para a frente) até a cúpula pendurada. Braço não validado (visual)."""
    cu, cv, ua, va = w / 2, d / 2, w / 2 - 750, -350
    return [_cil(cu, cv, w, 0, 30, "estrutura"),
            _cil(cu, cv, 25, 30, h, "estrutura"),
            _p(ua - 10, cu, cv - 10, cv + 10, h - 20, h, "estrutura"),
            _p(ua - 10, ua + 10, va - 10, cv + 10, h - 20, h, "estrutura"),
            _cil(ua, va, 10, h - 200, h - 20, "estrutura"),
            _p(ua - 170, ua + 170, va - 170, va + 170, h - 380, h - 180, "cupula", "esfera")]


def luminaria_articulada(w, d, h):
    """Luminária de mesa: base, haste, braço para a esquerda de quem olha e cúpula voltada para baixo."""
    cu, cv, ua = w / 2, d / 2, w / 2 - 220
    return [_cil(cu, cv, w, 0, 20, "estrutura"),
            _cil(cu, cv, 18, 20, h, "estrutura"),
            _p(ua, cu, cv - 8, cv + 8, h - 16, h, "estrutura"),
            _cil(ua, cv, 130, h - 150, h - 16, "cupula")]


def abajur_cogumelo(w, d, h):
    """Abajur cogumelo: pé cilíndrico + chapéu em domo (peça única de cor)."""
    return [_cil(w / 2, d / 2, 0.35 * w, 0, 0.6 * h, "estrutura"),
            _p(0, w, 0, d, 0.35 * h, h, "cupula", "esfera")]


def luminaria_piso_cupula(w, d, h):
    """Luminária de piso: base, haste curta e cúpula cilíndrica alta (papel/tecido)."""
    return [_cil(w / 2, d / 2, 0.7 * w, 0, 20, "estrutura"),
            _cil(w / 2, d / 2, 20, 20, 0.25 * h, "estrutura"),
            _cil(w / 2, d / 2, w, 0.25 * h, h, "cupula")]


MODELOS = {
    "pendente_esfera": pendente_esfera,
    "luminaria_arco": luminaria_arco,
    "luminaria_articulada": luminaria_articulada,
    "abajur_cogumelo": abajur_cogumelo,
    "luminaria_piso_cupula": luminaria_piso_cupula,
    "estante_industrial": estante_industrial,
    "frigobar_retro": frigobar_retro,
    "rack_vinil_norvege": rack_vinil_norvege,
    "vaso_planta": vaso_planta,
    "monitor_ultrawide": monitor_ultrawide,
    "cadeira_escritorio": cadeira_escritorio,
}


def para_global(peca: dict, frente: str, bbox, z_base: float) -> dict:
    """Converte (u, v, z) do produto para bbox global, conforme a frente do móvel.

    Quem olha o móvel de frente olha na direção oposta à `frente`; u cresce para a direita
    dessa pessoa e v cresce da frente para o fundo.
    """
    x0, y0, x1, y1 = bbox
    (u0, u1), (v0, v1) = peca["u"], peca["v"]
    if frente == "-y":   # frente em y0; observador olha +y; direita = +x
        xs, ys = (x0 + u0, x0 + u1), (y0 + v0, y0 + v1)
    elif frente == "+y":  # frente em y1; olha -y; direita = -x
        xs, ys = (x1 - u1, x1 - u0), (y1 - v1, y1 - v0)
    elif frente == "+x":  # frente em x1; olha -x; direita = +y
        xs, ys = (x1 - v1, x1 - v0), (y0 + u0, y0 + u1)
    else:                 # "-x": frente em x0; olha +x; direita = -y
        xs, ys = (x0 + v0, x0 + v1), (y1 - u1, y1 - u0)
    return {"bbox": [min(xs), min(ys), max(xs), max(ys)],
            "z0": z_base + peca["z"][0], "z1": z_base + peca["z"][1], "material": peca["material"],
            "forma": peca.get("forma", "caixa")}
