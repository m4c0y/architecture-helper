"""Modelos 3D paramétricos de produtos específicos (só aparência; não afetam validações).

Cada modelo devolve peças no referencial do PRODUTO, olhando-o de frente:
  u: 0 (esquerda de quem olha) .. largura
  v: 0 (frente) .. profundidade
  z: 0 (piso) .. altura
Proporções internas (pés, gaveta, prateleiras) foram estimadas nas fotos de referência
enviadas pelo usuário em 2026-11-17 — são aproximações visuais.
"""

from __future__ import annotations


def _p(u0, u1, v0, v1, z0, z1, mat, forma="caixa", raio=None):
    """Peça: caixa, cilindro (vertical, elíptico na bbox) ou esfera (elipsoide na bbox).
    `raio` (mm, opcional): cantos arredondados da caixa no Blender (só aparência)."""
    p = {"u": [u0, u1], "v": [v0, v1], "z": [z0, z1], "material": mat, "forma": forma}
    if raio:
        p["raio"] = raio
    return p


def _tubo(pontos, raio, mat, fechado=False):
    """Tubo de seção circular varrido pelos pontos (u, v, z) do produto (forma "tubo"): pés, armações,
    ganchos, hastes e ramos curvos. A bbox cobre os pontos ± raio."""
    us, vs, zs = zip(*pontos)
    return {"u": [min(us) - raio, max(us) + raio], "v": [min(vs) - raio, max(vs) + raio],
            "z": [min(zs) - raio, max(zs) + raio], "material": mat, "forma": "tubo",
            "tubo": {"pontos": [list(p) for p in pontos], "raio": raio, "fechado": fechado}}


def _superficie(linhas, espessura, mat):
    """Superfície lisa (forma "superficie") pela grade de pontos (u, v, z): linhas × colunas; o Blender
    liga a grade, dá espessura e suaviza. Para peças curvas e inclinadas (encosto de tela)."""
    pts = [p for linha in linhas for p in linha]
    us, vs, zs = zip(*pts)
    return {"u": [min(us), max(us)], "v": [min(vs), max(vs)], "z": [min(zs), max(zs)], "material": mat,
            "forma": "superficie", "superficie": {"linhas": [[list(p) for p in linha] for linha in linhas],
                                                  "espessura": espessura}}


def _cil(cu, cv, diam, z0, z1, mat):
    return _p(cu - diam / 2, cu + diam / 2, cv - diam / 2, cv + diam / 2, z0, z1, mat, "cilindro")


ESTANTE_NIVEIS = (0.128, 0.317, 0.507, 0.696, 0.886)  # fração da altura (medido na foto)
ESTANTE_PRATELEIRA = 20  # mm


def estante_industrial(w, d, h):
    """Quadro de tubo metálico preto (laterais em quadro) + 5 prateleiras de madeira clara.
    Prateleiras a ~13%, 32%, 51%, 70% e 89% da altura (medido na foto)."""
    t, e = 25, ESTANTE_PRATELEIRA  # tubo e espessura da prateleira
    pecas = []
    for u0 in (0, w - t):  # quadros laterais
        for v0 in (0, d - t):
            pecas.append(_p(u0, u0 + t, v0, v0 + t, 0, h, "metal_preto"))
        for z0 in (0, h - t):
            pecas.append(_p(u0, u0 + t, 0, d, z0, z0 + t, "metal_preto"))
    for frac in ESTANTE_NIVEIS:
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


ARMARIO_PORTA_ALVO = 450  # mm: largura de folha buscada ao dividir a frente (desenho, não medida)
ARMARIO_CAVA = 30         # mm: altura do puxador cava sob as portas


def armario_aereo(w, d, h):
    """Armário suspenso (a comprar; desenho de projeto): caixa de 18 mm, portas de abrir com frisos
    de 3 mm (folhas de ~450 mm) e puxador cava contínuo sob as portas (perfil escuro recuado)."""
    c, f, cava = 18, 3, ARMARIO_CAVA
    n = max(1, round(w / ARMARIO_PORTA_ALVO))
    pecas = [
        _p(0, w, c, d, h - c, h, "caixa"),                      # tampo
        _p(0, w, c + 25, d, 0, c, "caixa"),                     # base recuada (abre a cava)
        _p(0, c, c, d, 0, h - c, "caixa"), _p(w - c, w, c, d, 0, h - c, "caixa"),  # laterais
        _p(c, w - c, d - 6, d, c, h - c, "caixa"),              # fundo
        _p(c, w - c, c + 20, c + 25, 0, cava, "puxador"),       # perfil da cava (fundo escuro)
    ]
    folha = (w - f * (n - 1)) / n
    for k in range(n):
        u0 = k * (folha + f)
        pecas.append(_p(u0, u0 + folha, 0, c, cava, h, "porta"))
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


def luminaria_coluna_mesa(w, d, h):
    """Luminária de piso com mesa lateral: base redonda, haste fina, tampo redondo a ~41% da altura
    (70 de 170 cm no anúncio) e cúpula cilíndrica no topo (20 de 170 cm)."""
    zc, zm = h * (150 / 170), h * (69 / 170)
    return [_cil(w / 2, d / 2, 0.74 * w, 0, 20, "estrutura"),
            _cil(w / 2, d / 2, 20, 20, zc, "estrutura"),
            _cil(w / 2, d / 2, 0.77 * w, zm, zm + 10, "mesa"),
            _cil(w / 2, d / 2, w, zc, h, "cupula")]


# ------------------------------------------------------------------ decoração (categoria `decor`)
# Itens a comprar/escolher: formas ilustrativas dentro da bbox; cores vêm do conceito.

def tapete(w, d, h):
    return [_p(0, w, 0, d, 0, h, "tapete")]


def quadro(w, d, h):
    """Moldura (caixa) com a arte rente à frente, margem de 40 mm (passe-partout incluso na arte)."""
    m = min(40, w / 6, h / 6)
    return [_p(0, w, 0, d, 0, h, "moldura"), _p(m, w - m, -2, 0, m, h - m, "arte")]


def livros(w, d, h):
    """Fileira de livros em pé: larguras e alturas variadas (padrão fixo), três grupos de cor."""
    larg = (28, 35, 22, 40, 30, 25, 33, 38, 24)
    alt = (1.0, 0.86, 0.93, 0.8, 0.97, 0.9, 0.84, 0.95, 0.88)
    pecas, u, i = [], 0.0, 0
    while u + larg[i % len(larg)] <= w:
        lw = larg[i % len(larg)]
        pecas.append(_p(u, u + lw - 2, 0.05 * d, d, 0, alt[i % len(alt)] * h, ("livro_a", "livro_b", "livro_c")[i % 3]))
        u += lw
        i += 1
    return pecas


def almofada(w, d, h):
    return [_p(0, w, 0, d, 0, h, "almofada", "esfera")]


def cortina(w, d, h):
    """Trilho no topo + pregas (cilindros de 120 mm sobrepostos, alternando a profundidade)."""
    pecas = [_p(0, w, d / 2 - 10, d / 2 + 10, h - 20, h, "estrutura")]
    n = max(2, round(w / 90))
    passo = (w - 120) / (n - 1)
    for k in range(n):
        u = k * passo
        v = 0 if k % 2 == 0 else d - 0.6 * d
        pecas.append(_p(u, u + 120, v, v + 0.6 * d, 0, h - 25, "cortina", "cilindro"))
    return pecas


def toca_discos(w, d, h):
    """Toca-discos: base (plinto), prato de ~66% da largura à esquerda e braço à direita.
    Proporções genéricas (refs do usuário, 2026-11-19), não de um produto."""
    hb = 0.65 * h
    dp = min(0.66 * w, 0.9 * d)
    return [_p(0, w, 0, d, 0, hb, "base"),
            _cil(0.06 * w + dp / 2, d / 2, dp, hb, h, "prato"),
            _cil(0.85 * w, 0.25 * d, 40, hb, h, "braco"),
            _p(0.82 * w, 0.88 * w, 0.25 * d, 0.8 * d, h - 12, h, "braco")]


def caixa_som(w, d, h):
    """Caixa de som de estante: gabinete + frente (tela) com woofer e tweeter indicados por discos."""
    return [_p(0, w, 0, d, 0, h, "gabinete"),
            _p(6, w - 6, -3, 0, 6, h - 6, "tela"),
            _p(0.15 * w, 0.85 * w, -6, -3, 0.12 * h, 0.12 * h + 0.7 * w, "cone", "esfera"),
            _p(0.35 * w, 0.65 * w, -6, -3, 0.72 * h, 0.72 * h + 0.3 * w, "cone", "esfera")]


def cacto(w, d, h):
    """Cacto colunar com dois braços em vaso cilíndrico (~30% da altura)."""
    hv = 0.3 * h
    dt = 0.32 * min(w, d)
    return [_cil(w / 2, d / 2, 0.8 * min(w, d), 0, hv, "vaso"),
            _cil(w / 2, d / 2, dt, hv, h, "folhagem"),
            _cil(0.16 * w, d / 2, 0.7 * dt, 0.55 * h, 0.82 * h, "folhagem"),
            _p(0.16 * w, w / 2, d / 2 - 0.3 * dt, d / 2 + 0.3 * dt, 0.52 * h, 0.58 * h, "folhagem"),
            _cil(0.84 * w, d / 2, 0.7 * dt, 0.62 * h, 0.9 * h, "folhagem"),
            _p(w / 2, 0.84 * w, d / 2 - 0.3 * dt, d / 2 + 0.3 * dt, 0.6 * h, 0.66 * h, "folhagem")]


PENDENTE_QUEDA = 1.4  # ramos descem 1,4 × a altura do vaso+copa abaixo da base (à frente do apoio)


def _folha(u, v, z, largura, comprimento, rx, rz, mat="folhagem", perfil=0.75, curva=0.18, recortes=0):
    """Folha (forma "folha"): base no ponto (u, v, z) do produto; no Blender é uma lâmina pontuda,
    levemente curvada, de `largura` × `comprimento` (mm), deitada no plano XY apontando para +Y e
    girada por rx (em torno de X) e depois rz (em torno de Z), em graus. A bbox é só o ponto da base."""
    return {"u": [u - 2, u + 2], "v": [v - 2, v + 2], "z": [z - 2, z + 2], "material": mat, "forma": "folha",
            "folha": {"base": [u, v, z], "tam": [largura, comprimento], "rot": [rx, 0.0, rz],
                      "perfil": perfil, "curva": curva, "recortes": recortes}}


def persiana_romana(w, d, h):
    """Persiana romana: trilho no topo, painel liso atrás e dobras horizontais (rolos achatados ao
    longo da largura) empilhadas de baixo para cima, a cada ~70 mm."""
    pecas = [_p(0, w, d / 2 - 10, d / 2 + 10, h - 20, h, "estrutura"),
             _p(10, w - 10, d - 12, d - 4, 0, h - 20, "cortina")]
    n = max(1, round((h - 20) / 70))
    passo = (h - 20) / n
    for k in range(n):
        z0 = k * passo
        pecas.append(_p(5, w - 5, 0, d - 8, z0, min(z0 + passo + 6, h - 20), "cortina", "esfera"))
    return pecas


VINIL = 315  # mm: capa de LP (aparência)


def tv_parede(w, d, h):
    """TV fina: painel com moldura estreita (preto) + tela, e suporte de parede atrás."""
    return [_p(0, w, 0.25 * d, 0.6 * d, 0, h, "moldura_tv", raio=4),
            _p(8, w - 8, 0.25 * d - 2, 0.25 * d, 8, h - 8, "tela"),
            _p(w / 2 - 150, w / 2 + 150, 0.6 * d, d, 0.3 * h, 0.7 * h, "estrutura")]


def porta_celeiro(w, d, h):
    """Folha de porta de correr estilo celeiro: tábuas verticais (~140 mm, frisos de 4 mm), travessas
    no alto e embaixo na face visível, puxador vertical e duas alças das roldanas no topo.
    Materiais: "madeira" (folha, cor do conceito), "ferragem" (alças e puxador)."""
    alca = 90  # alças das roldanas acima da folha
    hf = h - alca
    pecas = []
    n = max(3, round(w / 140))
    t = w / n
    for k in range(n):
        pecas.append(_p(k * t + 2, (k + 1) * t - 2, 8, d, 0, hf, "madeira"))
    for z0 in (60, hf - 200):
        pecas.append(_p(0, w, 0, 10, z0, z0 + 140, "madeira"))
    for u in (0.15 * w, 0.85 * w - 40):
        pecas.append(_p(u, u + 40, 6, 14, hf - 120, h, "ferragem"))
    pecas.append(_p(0.1 * w, 0.1 * w + 22, -40, 0, 0.42 * hf, 0.62 * hf, "ferragem", "cilindro"))
    return pecas


# ------------------------------------------------------------------ modelos detalhados (P4/P5, 2026-11-23)
# Mais fiéis às fotos dos produtos (proporções estimadas nas fotos; só aparência, dentro da caixa do item).

def cadeira_escritorio(w, d, h):
    """Cadeira ergonômica (foto da Elements Rasala): base estrela de 5 patas com rodízios, pistão,
    mecanismo, assento estofado, encosto de tela reclinado (mais estreito na lombar) com apoio lombar,
    apoio de cabeça em haste, braços em L com apoio, e alavanca. v = 0 é para onde a pessoa olha.
    Materiais: "estofado" e "estrutura" (cor real do produto), "malha" (tela do encosto), "metal_preto"."""
    import math
    cu, cv = w / 2, 0.48 * d
    za = 0.37 * h                      # altura do assento
    pecas = [_cil(cu, cv, 80, 55, 105, "estrutura")]
    rp = 0.46 * min(w, d)              # raio da estrela até o rodízio
    for k in range(5):
        a = math.radians(90 + 72 * k)
        tu, tv = cu + rp * math.cos(a), cv + rp * math.sin(a)
        pecas.append(_tubo([(cu, cv, 85), (cu + 0.5 * rp * math.cos(a), cv + 0.5 * rp * math.sin(a), 80), (tu, tv, 66)],
                           17, "estrutura"))
        pecas.append(_p(tu - 9, tu + 9, tv - 9, tv + 9, 45, 70, "estrutura"))            # garfo
        pecas.append(_p(tu - 26, tu + 26, tv - 13, tv + 13, 0, 52, "estrutura", "esfera"))  # roda dupla
    pecas += [_cil(cu, cv, 46, 105, 250, "cromado"), _cil(cu, cv, 56, 250, za - 70, "metal_preto"),
              _p(cu - 95, cu + 95, cv - 90, cv + 110, za - 75, za - 40, "metal_preto", raio=10),
              _tubo([(cu + 60, cv - 40, za - 60), (cu + 210, cv - 140, za - 75), (cu + 250, cv - 150, za - 70)], 6,
                    "metal_preto")]
    # assento: concha + almofada
    s0, s1 = 0.12 * w, 0.88 * w
    pecas.append(_p(s0 + 10, s1 - 10, 0.08 * d, 0.84 * d, za - 45, za - 25, "estrutura", raio=15))
    almof = _p(s0, s1, 0.06 * d, 0.86 * d, za - 30, za + 35, "estofado", raio=30)
    almof["forma"] = "almofada"
    pecas.append(almof)
    # encosto de tela: fatias horizontais reclinando para trás, mais estreitas na lombar
    zb0, zb1 = za + 70, 0.85 * h
    vb0, vb1 = 0.80 * d, 0.92 * d
    n = 18
    linhas = []  # tela do encosto: superfície lisa, reclinada e curva (laterais avançam para a frente)
    for i in range(n + 1):
        t = i / n
        larg = (0.50 + 0.14 * math.sin(math.pi * min(1.0, 0.35 + 0.8 * t))) * w
        v0, z = vb0 + t * (vb1 - vb0) + 7, zb0 + t * (zb1 - zb0)
        linhas.append([(cu + f * larg / 2, v0 - 28 * f * f, z) for f in (-1, -0.66, -0.33, 0, 0.33, 0.66, 1)])
    pecas.append(_superficie(linhas, 6, "malha"))
    # moldura do encosto (tubo em volta)
    borda = []
    for i in range(n + 1):
        t = i / n
        larg = (0.50 + 0.14 * math.sin(math.pi * min(1.0, 0.35 + 0.8 * t))) * w
        borda.append((cu - larg / 2, vb0 + t * (vb1 - vb0) + 7 - 28, zb0 + t * (zb1 - zb0)))
    pecas.append(_tubo(borda + [(u2 + 2 * (cu - u2), v2, z2) for u2, v2, z2 in reversed(borda)], 11, "malha",
                       fechado=True))
    # apoio lombar
    lz = zb0 + 0.22 * (zb1 - zb0)
    lomb = _p(cu - 0.2 * w, cu + 0.2 * w, vb0 - 30, vb0 + 2, lz, lz + 0.1 * h, "malha", raio=18)
    lomb["forma"] = "almofada"
    pecas.append(lomb)
    # espinha que liga o mecanismo ao encosto
    pecas.append(_tubo([(cu, cv + 90, za - 55), (cu, vb0 + 40, za - 20), (cu, vb0 + 25, zb0 + 40)], 22, "estrutura"))
    # apoio de cabeça
    hz0, hz1 = 0.89 * h, h
    pecas.append(_tubo([(cu, vb1 + 10, zb1 - 40), (cu, vb1 + 18, hz0 + 30)], 13, "metal_preto"))
    cab = _p(cu - 0.21 * w, cu + 0.21 * w, vb1 - 10, vb1 + 12, hz0, hz1, "malha", raio=30)
    cab["forma"] = "almofada"
    pecas.append(cab)
    # braços em L (sob o assento -> sobe) + apoio
    for lado in (-1, 1):
        ub = cu + lado * 0.44 * w
        pecas.append(_tubo([(cu + lado * 0.2 * w, cv + 20, za - 50), (ub, cv + 20, za - 50), (ub, cv + 20, za + 175)],
                           16, "estrutura"))
        apoio = _p(ub - 38, ub + 38, cv - 110, cv + 120, za + 175, za + 205, "estrutura", raio=12)
        apoio["forma"] = "almofada"
        pecas.append(apoio)
    return pecas


def rack_vinis(w, d, h):
    """Rack baixo mid-century de nogueira com pés hairpin pretos e 3 nichos abertos de LPs em pé.
    Materiais: "caixa" (cor do conceito), "hairpin" (metal preto) e capas "disco_a/b/c" (genéricas)."""
    pe, c = 0.25 * h, 18
    pecas = []
    for u in (60, w - 60):
        for v in (55, d - 55):
            pecas.append(_tubo([(u - 18, v, pe), (u, v, 5), (u + 18, v, pe)], 5, "hairpin"))
            pecas.append(_tubo([(u, v - 18, pe), (u, v, 5), (u, v + 18, pe)], 5, "hairpin"))
    pecas += [_p(0, w, 0, d, h - c, h, "caixa", raio=4), _p(0, w, 0, d, pe, pe + c, "caixa", raio=3),
              _p(0, c, 0, d, pe, h, "caixa", raio=3), _p(w - c, w, 0, d, pe, h, "caixa", raio=3),
              _p(c, w - c, d - 8, d, pe, h, "caixa")]
    n = 3
    vao = (w - 2 * c - (n - 1) * c) / n
    alt = min(VINIL, h - c - (pe + c) - 10)
    for i in range(n):
        u0 = c + i * (vao + c)
        if i:
            pecas.append(_p(u0 - c, u0, 0, d - 8, pe + c, h - c, "caixa", raio=2))
        u, k = u0 + 6, 0
        fim = u0 + vao - 6 - (60 if i == 1 else 0)
        while u + 4 <= fim:
            inc = 0.0 if i != 1 else 0  # em pé
            pecas.append(_p(u, u + 4, 20, min(d - 12, 20 + VINIL), pe + c,
                            pe + c + alt * (0.97 + 0.03 * (k % 2)) + inc, ("disco_a", "disco_b", "disco_c")[(k * 7 + i) % 3]))
            u += 5.5
            k += 1
    return pecas


def pegboard(w, d, h):
    """Pegboard de parede (painel perfurado no fundo, v = d) com o que fica pendurado: teclado em dois
    ganchos, headphone (arco + conchas) num gancho e três controles embaixo; ganchos em L de arame."""
    import math
    e = 15
    pecas = [_p(0, w, d - e, d, 0, h, "painel", raio=3)]
    passo = 38
    nu, nz = int((w - 20) // passo), int((h - 20) // passo)
    u0, z0 = (w - (nu - 1) * passo) / 2, (h - (nz - 1) * passo) / 2
    for i in range(nu):
        for j in range(nz):
            u, z = u0 + i * passo, z0 + j * passo
            pecas.append(_p(u - 4, u + 4, d - e - 1.5, d - e, z - 4, z + 4, "furo", "cilindro"))
    fr = d - e

    def gancho(u, z, compr=50):
        pecas.append(_tubo([(u, fr, z), (u, fr - compr, z), (u, fr - compr, z + 16)], 2.5, "gancho"))

    tk0, tk1, tz = 0.06 * w, 0.68 * w, 0.62 * h
    for u in (tk0 + 40, tk1 - 40):
        gancho(u, tz - 6)
    tec = _p(tk0, tk1, fr - 44, fr - 20, tz, tz + 0.2 * h, "teclado", raio=6)
    pecas.append(tec)
    for fila in range(4):
        zz = tz + 16 + fila * 0.042 * h
        u = tk0 + 14
        while u + 16 <= tk1 - 12:
            pecas.append(_p(u, u + 15, fr - 50, fr - 44, zz, zz + 0.032 * h, "tecla", raio=2))
            u += 19
    hu, hz = 0.84 * w, 0.6 * h
    gancho(hu, hz + 0.3 * h, 60)
    arco = [(hu + 70 * math.cos(math.radians(a)), fr - 45, hz + 0.12 * h + 85 * math.sin(math.radians(a)))
            for a in range(0, 181, 12)]
    pecas.append(_tubo(arco, 9, "fone"))
    for lado in (-1, 1):
        pecas.append(_p(hu + lado * 72 - 24, hu + lado * 72 + 24, fr - 62, fr - 22, hz, hz + 0.16 * h, "fone", "esfera"))
    for k, u in enumerate((0.2 * w, 0.5 * w, 0.8 * w)):
        gancho(u, 0.35 * h, 55)
        ctl = _p(u - 72, u + 72, fr - 60, fr - 18, 0.1 * h, 0.1 * h + 95, "controle_b" if k == 1 else "controle", raio=24)
        ctl["forma"] = "almofada"
        pecas.append(ctl)
    return pecas


def planta_pendente(w, d, h):
    """Jiboia pendente: vaso com terra, coroa de folhas em coração arqueando para fora e ramos curvos
    (tubos finos) que passam pela borda da frente do apoio e descem balançando, com folhas alternadas
    que diminuem até a ponta. Semente fixa pelas dimensões (aparência)."""
    import math
    import random
    rnd = random.Random(int(w * 7 + d * 3 + h))
    hv = 0.45 * h
    dv = 0.6 * min(w, d)
    cu, cv = w / 2, 0.6 * d
    q = PENDENTE_QUEDA * h
    pecas = [_cil(cu, cv, dv, 0, hv, "vaso")]
    for k in range(34):
        ang = 2 * math.pi * k / 34 + rnd.uniform(-0.2, 0.2)
        r = rnd.uniform(0.2, 0.55) * dv
        comp = rnd.uniform(70, 115)
        pecas.append(_folha(cu + r * math.cos(ang), cv + r * math.sin(ang), hv + rnd.uniform(-10, 25),
                            0.7 * comp, comp, rnd.uniform(-30, 35), math.degrees(ang) - 90 + rnd.uniform(-30, 30),
                            perfil=0.55, curva=0.2))
    for i in range(6):
        u = cu + (i - 2.5) * dv / 6 + rnd.uniform(-10, 10)
        queda = q * rnd.uniform(0.45, 1.0)
        fase = rnd.uniform(0, 6.3)
        pts = [(u, cv - dv / 2 + 10, hv - 5), (u, cv - dv / 2 - 25, hv), (u, -20, hv * 0.5), (u, -40, 0.0)]
        z = 0.0
        while z > -queda:
            z = max(z - 45, -queda)
            pts.append((u + 30 * math.sin(fase + z / 120), -45 + 15 * math.sin(fase + z / 160), z))
        pecas.append(_tubo(pts, 2.5, "caule"))
        tot = len(pts)
        for k, (pu, pv, pz) in enumerate(pts[2:], start=2):
            comp = 100 - 45 * k / tot + rnd.uniform(-10, 10)
            lado = 1 if k % 2 else -1
            pecas.append(_folha(pu, pv, pz, 0.72 * comp, comp, rnd.uniform(-160, -95),
                                180 + lado * rnd.uniform(25, 75), perfil=0.55, curva=0.15))
    return pecas


def monstera(w, d, h):
    """Monstera deliciosa: hastes longas e curvas (tubos) saindo do vaso e folhas grandes em coração
    com recortes (fendas da borda até perto da nervura); folhas novas menores e inteiras."""
    import math
    import random
    rnd = random.Random(int(w * 5 + d * 11 + h))
    hv = 0.3 * h
    cu, cv = w / 2, d / 2
    pecas = [_cil(cu, cv, 0.55 * min(w, d), 0, hv, "vaso")]
    n = 9
    for k in range(n):
        ang = 2 * math.pi * k / n + rnd.uniform(-0.25, 0.25)
        alto = rnd.uniform(0.5, 0.88) * h
        alcance = rnd.uniform(0.18, 0.34) * min(w, d)
        pts = []
        for t in range(9):
            f = t / 8
            pts.append((cu + alcance * f ** 1.5 * math.cos(ang), cv + alcance * f ** 1.5 * math.sin(ang),
                        hv - 20 + (alto - hv + 20) * math.sin(f * math.pi / 2)))
        pecas.append(_tubo(pts, 6, "caule"))
        grande = k % 3 != 2
        comp = (rnd.uniform(0.55, 0.7) if grande else rnd.uniform(0.32, 0.42)) * min(w, d)
        u, v, z = pts[-1]
        pecas.append(_folha(u, v, z, 0.95 * comp, comp, rnd.uniform(20, 50), math.degrees(ang) - 90,
                            perfil=0.5, curva=0.16, recortes=3 if grande else 0))  # folha voltada para cima/fora
    return pecas


MODELOS = {
    "tapete": tapete,
    "quadro": quadro,
    "livros": livros,
    "almofada": almofada,
    "cortina": cortina,
    "luminaria_coluna_mesa": luminaria_coluna_mesa,
    "pendente_esfera": pendente_esfera,
    "luminaria_arco": luminaria_arco,
    "luminaria_articulada": luminaria_articulada,
    "abajur_cogumelo": abajur_cogumelo,
    "luminaria_piso_cupula": luminaria_piso_cupula,
    "estante_industrial": estante_industrial,
    "armario_aereo": armario_aereo,
    "frigobar_retro": frigobar_retro,
    "rack_vinil_norvege": rack_vinil_norvege,
    "vaso_planta": vaso_planta,
    "monitor_ultrawide": monitor_ultrawide,
    "cadeira_escritorio": cadeira_escritorio,
    "toca_discos": toca_discos,
    "caixa_som": caixa_som,
    "cacto": cacto,
    "planta_pendente": planta_pendente,
    "persiana_romana": persiana_romana,
    "rack_vinis": rack_vinis,
    "tv_parede": tv_parede,
    "monstera": monstera,
    "porta_celeiro": porta_celeiro,
}


def superficies_apoio(modelo: str | None, w, d, h) -> list[float]:
    """Alturas (mm, a partir da base do móvel) das superfícies onde se apoiam objetos (`sobre` + `nivel`).
    Sem modelo (ou modelo sem prateleiras): só o topo."""
    if modelo == "estante_industrial":
        return [round(f * h) + ESTANTE_PRATELEIRA for f in ESTANTE_NIVEIS]
    if modelo == "luminaria_coluna_mesa":
        return [h * (69 / 170) + 10]
    return [h]


MODELOS["pegboard"] = pegboard

GIRO_FRENTE = {"-y": 0.0, "+y": 180.0, "+x": 90.0, "-x": -90.0}  # graus: eixos (u, v) do produto -> (x, y)


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
    g = {"bbox": [min(xs), min(ys), max(xs), max(ys)],
         "z0": z_base + peca["z"][0], "z1": z_base + peca["z"][1], "material": peca["material"],
         "forma": peca.get("forma", "caixa"), **({"raio": peca["raio"]} if peca.get("raio") else {})}
    if "superficie" in peca:  # cada ponto da grade para o global
        linhas = []
        for linha in peca["superficie"]["linhas"]:
            nova = []
            for pu, pv, pz in linha:
                q = para_global({"u": [pu, pu], "v": [pv, pv], "z": [pz, pz], "material": ""}, frente, bbox, z_base)
                nova.append([q["bbox"][0], q["bbox"][1], q["z0"]])
            linhas.append(nova)
        g["superficie"] = {**peca["superficie"], "linhas": linhas}
    if "tubo" in peca:  # cada ponto do tubo para o global
        pts = []
        for pu, pv, pz in peca["tubo"]["pontos"]:
            q = para_global({"u": [pu, pu], "v": [pv, pv], "z": [pz, pz], "material": ""}, frente, bbox, z_base)
            pts.append([q["bbox"][0], q["bbox"][1], q["z0"]])
        g["tubo"] = {**peca["tubo"], "pontos": pts}
    if "folha" in peca:  # base da folha no global + giro do produto somado ao rz
        fu, fv, fz = peca["folha"]["base"]
        p = para_global({"u": [fu, fu], "v": [fv, fv], "z": [fz, fz], "material": ""}, frente, bbox, z_base)
        rx, ry, rz = peca["folha"]["rot"]
        g["folha"] = {**peca["folha"], "base": [p["bbox"][0], p["bbox"][1], p["z0"]],
                      "rot": [rx, ry, rz + GIRO_FRENTE[frente]]}
    return g
