---
name: render-final
description: Conduz o detalhamento (P4) e o render final (P5) de um ambiente aprovado — modelos 3D fiéis dos produtos no Blender, render Cycles, mapas de profundidade e máscaras, e o acabamento fotográfico com FLUX.2 usando vista mestra, com estimativa de custo antes e escolha visual das imagens depois. Use quando o usuário pedir imagens finais, render de alta fidelidade, "imagem real com IA" ou para avançar um ambiente para P4/P5.
---

# Render final de um ambiente (P4 → P5)

Pré-requisito: `conceito.yaml` e `layout.yaml` aprovados em `ambientes/<id>/` (`archtools status`
mostra P4 ou P5). Nada aqui muda decisões de projeto; mudou algo de projeto → volta para P2/P3.

## 1. P4 — modelos dos produtos no Blender (antes de qualquer IA)
A IA só vê os móveis pelo Blender: **cada item com `produto:` visível nas câmeras precisa de um
`modelo` 3D detalhado** (`modelos.py`, ou `partes` no caso de estofados), o mais fiel possível ao
produto: silhueta, encosto, braços, pés, almofadas, cores por peça. Caixa simples = a IA inventa.
- Troca de modelo: `ambientes/<id>/detalhamento.yaml` (mesma caixa do catálogo, sem decisão nova).
- Conferir com Eevee/Cycles e comparar com as fotos do produto (catálogo `fotos`) — as fotos servem
  para MODELAR, não vão para a IA.
- `archtools cena` → render. `ia_flux2.sem_modelo` / `archtools ia` acusam o que faltar.

## 2. P5 — render e insumos da IA
Em `ambientes/<id>/render_final.yaml`: câmeras, períodos, motor cycles, resolução, amostras, `saida`,
e o bloco `ia:` (`mestra`, `sementes`, `limite`, `comodo`, `superficies`, `fixas` com as cores de
paredes/sofá/cadeira e "nada pendurado além de…", `objetos` com o que cada item realmente é, em inglês,
e `paredes`). Depois, Blender (em segundo plano, ~1 h para 8 quadros Cycles 1080p). **Tudo o que o
Blender gera vai para `<saida>/blender/`** (renders, `mascaras/`, `profundidade/`, `modelo.blend`); a IA
fica em `<saida>/ia/` — assim se sabe de onde veio cada imagem. As três chamadas, já com as pastas
certas: `uv run --project tools archtools render-final projetos/<p> --ambiente <id>`. São elas:
```
blender --background --python blender/construir_cena.py -- <cena.json> <saida>/blender --cameras ... --res 1920x1080 --motor cycles --amostras 192 --periodo ambos
blender ... -- <cena.json> <saida>/blender/profundidade --cameras ... --res 1536x864 --profundidade
blender ... -- <cena.json> <saida>/blender/mascaras --cameras ... --res 1536x864 --mascaras
```

## 3. Custo — sempre antes de gerar (memória `custo-apis-imagem`)
FLUX.2 [max] edit cobra as imagens ENVIADAS também: ≈ US$ 0,16 a mestra (render + profundidade),
≈ 0,22 cada outra vista por semente (+ referência). 8 vistas ≈ US$ 1,70 com uma semente, até ≈ 3,40
com duas. Diga a estimativa e combine o teto com o usuário antes de rodar; nunca rode "mais uma".

## 4. Gerar (vista mestra)
```
uv run --project tools archtools ia projetos/<p> --ambiente <id>            # todas as vistas
uv run --project tools archtools ia projetos/<p> --ambiente <id> --vistas <id>-mesa-noite   # refazer uma
```
Ordem: mestra → outras de dia (referência = mestra) → noites (referência = dia da MESMA câmera).
Candidatas em `<saida>/ia-candidatas/` (+ `.prompt.txt` e `relatorio.json` com notas e custo).

## 5. Escolher com o usuário
A aderência só mede contornos; ela NÃO percebe móvel inventado ou mudado de lugar (ex.: cadeira
virada). Monte uma folha render × candidatas, olhe cada vista contra o render (posição e forma
de cada móvel, janela reta, porta certa, cores fixas) e mostre ao usuário com as notas e o custo.
Vista errada → refazer só ela (`--vistas`), com o teto combinado.
```
uv run --project tools archtools ia-selecionar projetos/<p> --ambiente <id> --escolha <vista>=<arquivo> ... --limpar
```
Grava `<saida>/ia/<vista>.png` + `selecao.json` (origem, semente, aderência, referência, quem escolheu)
e apaga as candidatas. As imagens são ILUSTRATIVAS (selo); o render do Blender é a referência.
A P5 termina com a decisão do usuário aprovando as imagens (skill `registrar-decisao`).
