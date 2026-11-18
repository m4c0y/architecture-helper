---
name: referencia
description: Guarda e analisa imagens de referência (ambientes, móveis, luminárias, materiais, paletas, produtos) — da biblioteca de um estilo (arquitetos/<id>/referencias/) ou de um projeto (projetos/<p>/referencias/) — gerando um YAML por imagem com o que foi observado, a paleta extraída por script e as preferências confirmadas pelo usuário. Use quando o usuário enviar ou colocar imagens de referência, pedir para analisar referências, ou quando for calibrar uma persona de estilo.
---

# Referência visual

Cada imagem tem um YAML irmão com o mesmo nome (`sala-01.jpg` → `sala-01.yaml`). Esquema e
exemplo: docstring de `tools/src/archtools/referencias.py`. Três níveis, nunca misturados:

| Nível | Bloco | Quem preenche |
|---|---|---|
| observado | `analise` | o agente (visão) e scripts (`archtools paleta`) |
| preferência | `usuario` | só com confirmação explícita do usuário |
| aprovado | — | um conceito aprovado cita a referência; nunca neste arquivo |

## 1. Onde fica a imagem
- **Biblioteca de estilo** (reutilizável, vai para o repositório público):
  `arquitetos/<id>/referencias/`. Exige imagem própria ou com licença que permita redistribuir.
- **Projeto** (pessoal): `projetos/<p>/referencias/`.
- Imagens enviadas no chat não viram arquivo sozinhas: peça ao usuário para salvá-las na pasta
  certa (com um nome curto, `kebab-case`) e avise quando terminar.
- Foto de produto usada para obter medidas não é referência de estilo: registre como `tipo:
  produto` no projeto e trate as medidas pelo fluxo do layout (`estimado` com fonte).

## 2. Criar o YAML (um por imagem)
Campos obrigatórios: `id` (= nome do arquivo sem extensão), `arquivo`, `origem` (site/página e
data), `licenca`, `tipo`. Pergunte ao usuário a origem e a licença se não souber — **não
invente**. Se a licença exigir crédito, preencha `atribuicao` com o texto pedido pelo site.
`ilustra`: o que a imagem demonstra para a biblioteca (ex.: "parede de tijolo", "trilho com spots").

## 3. Paleta: sempre por script
```bash
uv run --project tools archtools paleta <pasta>/<img> --arquiteto <id> --gravar
```
Grava `analise.paleta`. `--arquiteto` mostra a cor mais próxima da persona e o ΔE (CIE76):
~2 quase igual, <10 parecida, >10 claramente diferente. Nunca escreva hex "a olho".

## 4. Análise visual (o agente)
Preencha em `analise`:
- `por`: "agente (visão), AAAA-MM-DD";
- `influencias`: **várias**, com peso (alto/medio/baixo) — não force um estilo único; use ids de
  `arquitetos/` quando existirem, nome livre quando não (vira aviso: estilo sem persona);
- `elementos`: tipo + descrição + tags **do vocabulário** `arquitetos/tags.yaml`
  (tag que falta → propor ao usuário acrescentar, não inventar);
- `luz` e `composicao`: uma frase cada.
Proporções e medidas vistas na imagem não viram números aqui — referência nunca é fonte de
geometria. Com muitas imagens, analise em lote num subagente e revise o resultado.

## 5. Confirmar preferências
Mostre ao usuário o que foi observado e pergunte do que gosta e do que não gosta. Só então
preencha `usuario: {gosto, nao_gosto, confirmado_em}`. Em biblioteca de estilo isso é opcional
(a imagem ilustra o estilo, não necessariamente o gosto do usuário).

## 6. Validar
```bash
uv run --project tools archtools referencias arquitetos            # todas as bibliotecas
uv run --project tools archtools referencias projetos/<p>/referencias
```
Mostra contagem por tipo (o que ainda falta pedir), imagens sem YAML, tags fora do vocabulário
e análises pendentes. Erro = corrigir antes de usar a referência.

## 7. Usar as referências
- **Calibrar uma persona**: compare as paletas extraídas com a da persona (ΔE) e os elementos
  observados com `persona.md`/`arquiteto.yaml`. Proponha ajustes ao usuário; mudanças em
  `arquiteto.yaml` só com aprovação (skill `arquiteto`, seção 7).
- **Referência nova num ambiente já aprovado**: produza uma nota de impacto (o que conflita com a
  paleta/materiais aprovados, por tags) e, se o usuário quiser, uma **proposta** nova. O que está
  aprovado nunca muda automaticamente.
