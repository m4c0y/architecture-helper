# Assistente de Arquitetura e Interiores

Ambiente de trabalho para projetos pessoais de arquitetura e design de interiores.
O agente atua como assistente de projeto: interpreta plantas, organiza requisitos,
planeja ambientes e mantém o histórico. **Cálculos e validações são sempre feitos
pelas ferramentas determinísticas em `tools/` (pacote `archtools`), nunca "de cabeça".**

## Princípios (inegociáveis)

1. **A geometria documentada é a fonte da verdade.** Arquivos em `projetos/<nome>/*.yaml`.
   Modelos 3D, imagens e plantas desenhadas são *saídas* — podem ser apagadas e regeradas.
2. **Nunca invente medidas.** Se um valor não foi informado ou medido, ele é
   `status: desconhecido` com `valor: null`. Não preencha "valores típicos" — exceto quando o
   usuário pedir explicitamente; aí o valor é `estimado`, a fonte cita a decisão que autorizou
   (ex.: decisão 0006, esquadrias) e ele continua listado em `pendencias.md`.
3. **Nunca altere `geometria.yaml` sem autorização explícita do usuário** para aquela
   alteração específica. Propostas vão para `propostas/` ou são apresentadas no chat.
4. **Diferencie sempre o status de cada informação:**
   - `confirmado` — medido ou cotado em documento oficial; exige `fonte`.
   - `estimado` — inferido (leitura de imagem, proporção, suposição informada); exige `fonte`
     explicando a origem da estimativa.
   - `desconhecido` — sem valor.
   Valores derivados herdam o status mais fraco das entradas (o `archtools` faz isso).
   Ao falar de números com o usuário, deixe o status explícito.
5. **Toda afirmação numérica passa pelo `archtools`** (áreas, folgas, se algo cabe, etc.).
   Se a ferramenta não cobre o cálculo, diga isso e proponha estendê-la — não estime.
6. **Simplicidade.** Nada de dependências, serviços ou abstrações sem necessidade concreta.

## Estrutura

```
tools/                      pacote Python archtools (determinístico, com testes)
arquitetos/<id>/            personas de estilo FICTÍCIAS (persona.md + arquiteto.yaml + referencias/)
arquitetos/tags.yaml        vocabulário de tags (personas e referências)
catalogo/produtos/          itens genéricos reutilizáveis (medidas com status)
catalogo/texturas/          texturas CC0 (texturas.yaml; imagens fora do git: `baixar.py` baixa de novo)
projetos/<nome>/
  geometria.yaml            envelope: ambientes, aberturas, pé-direito, pontos fixos (FONTE DA VERDADE)
  ambientes/<id>/           um ambiente (a pasta é a aprovação; decisões 2026-11-18):
    briefing.md             entrevista: uso, itens existentes, gostos, restrições (skill `briefing`)
    conceito.yaml           APROVADO: como fica (estilo, referências, cores por superfície/item, luzes)
    layout.yaml             APROVADO: o que vai onde (coords locais; itens `produto:` herdam do catálogo)
    cameras.yaml            câmeras fixas do ambiente (coords locais) para comparar propostas (sem aprovação)
    detalhamento.yaml       P4: troca só o `modelo` 3D de itens aprovados (mesma caixa; sem decisão nova)
    render_final.yaml       P5: câmeras, períodos, qualidade e bloco `ia:` (mestra, sementes, cores fixas,
                            o que cada objeto é) — saida: saidas/final, sempre com duas pastas: blender/ (renders,
                            mascaras/, profundidade/, modelo.blend) e ia/ (imagens de IA escolhidas)
  catalogo/produtos/        produtos escolhidos pelo usuário: medidas (status+fonte), modelo 3D, cor_real
                            (hex ou {material da peça: hex}), textura
  layout.yaml               (antigo) layout único do projeto — vale até cada ambiente ter o seu
  criterios.yaml            folgas de circulação (decisão 0008)
  estilo.yaml               só `padrao` da casa (o estilo de cada ambiente fica no conceito.yaml)
  estudos/                  buscas exaustivas de layout (scripts reproduzíveis)
  requisitos.md             o que o usuário quer/precisa
  pendencias.md             GERADO por `archtools pendencias` — não editar à mão
  decisoes/NNNN-titulo.md   registro de decisões
  fontes/                   material bruto do usuário (plantas, fotos, croquis) — somente leitura
  medicoes/                 scripts que medem as imagens de fontes/ (valores PX/PV) — reproduzíveis
  referencias/              imagens de inspiração + index.yaml
  propostas/                variações ainda não aprovadas (promovidas ficam com LEIA-ME "arquivada")
                            (mudança de infraestrutura: `geometria.yaml` PRÓPRIO na pasta da proposta;
                            `layout`/`cena` usam essa geometria; a do projeto só muda na aprovação)
  saidas/                   GERADO: planta.png/svg, planta-layout.*, cena.json, 3d/ (renders + modelo.blend);
                            cada pasta tem manifest.json (de quais entradas veio) — `archtools status` confere
blender/construir_cena.py   lê cena.json e monta/renderiza no Blender (não calcula geometria)
.claude/skills/             procedimentos: ingerir-planta, validar-projeto, registrar-decisao, briefing, arquiteto, referencia,
                            render-final
```

## Comandos (rodar a partir da raiz do repositório)

```bash
uv run --project tools archtools validar projetos/apartamento
uv run --project tools archtools areas projetos/apartamento
uv run --project tools archtools planta projetos/apartamento      # gera saidas/planta.png e .svg
uv run --project tools archtools pendencias projetos/apartamento  # regenera pendencias.md
uv run --project tools archtools layout projetos/apartamento --layout projetos/apartamento/layout.yaml --recorte dorm2
uv run --project tools archtools cena projetos/apartamento --cameras dorm2   # saidas/cena.json (+ câmeras do ambiente)
uv run --project tools archtools estilo projetos/apartamento [--estilo <proposta>/estilo.yaml] [--ambiente dorm2]
& "C:\Program Files\Blender Foundation\Blender 5.3\blender.exe" --background --python blender/construir_cena.py -- `
    projetos/apartamento/saidas/cena.json projetos/apartamento/saidas/3d [--cameras dorm2-se] [--res 1280x720] [--motor eevee|cycles] [--periodo dia|noite|ambos] [--mascaras] [--profundidade]
uv run --project tools archtools render-final projetos/apartamento-reforma --ambiente dorm2  # chamadas do Blender (saída em final/blender)
uv run --project tools archtools ia projetos/apartamento-reforma --ambiente dorm2 [--vistas dorm2-mesa-noite]  # FLUX.2 (PAGO)
uv run --project tools archtools ia-selecionar projetos/apartamento-reforma --ambiente dorm2 [--escolha vista=arquivo] [--limpar]
uv run --project tools archtools referencias arquitetos                       # valida bibliotecas de referência
uv run --project tools archtools paleta <imagem> [--arquiteto <id>] [--gravar]  # paleta por script (median cut)
uv run --project tools archtools status projetos/apartamento       # fases, aprovações, saídas desatualizadas
uv run --project tools archtools aprovacao projetos/apartamento --arquivos layout.yaml   # cabeçalho de decisão com hash
uv run --project tools python -I catalogo/texturas/baixar.py      # texturas CC0 (só com permissão do usuário)
uv run --project tools pytest tools/tests -q
```

Fluxo de um ambiente: `briefing` → propostas em `propostas/<ambiente>-<nome>/` (`layout.yaml` com
`ambiente: <id>` + `conceito.yaml` + `LEIA-ME.md`) → `archtools layout` (0 erros) e `archtools cena`
→ aprovação do usuário → copiar para `ambientes/<id>/` + decisão com `archtools aprovacao`.
Spot com `alvo: [x, y, z]` (local) e `abertura` (graus) no conceito aponta para o alvo (ex.: trilho).
Móveis são caixas simples (mesa = tampo + pernas) ou modelos paramétricos (`modelo`, ex.: `armario_aereo`).
Estofado com forma (`altura_assento`, `blocos_assento`, braços, `prof_encosto`, `almofadas_encosto`) sai em
peças com `raio` de arredondamento (bevel no Blender). Luminária `fita_led` vira luz `linha`: fita de
ponta a ponta sob o móvel (`intensidade_w` por metro).
Decoração (P3): itens `categoria: decor` no layout (tapete, quadro, livros, cortina, almofada, plantas);
`sobre: <id>` (+ `nivel:` da prateleira) apoia o item em outro e o `archtools` CALCULA a elevação;
tapete (decor no piso, até 30 mm) não colide nem bloqueia a passagem. Texturas procedurais
(madeira, réguas, tecido, couro, metal, pintura) vêm do `archtools` (`materiais.TEXTURAS`, tags da cor,
`piso_textura` no conceito); o Blender só monta os nós.

P4 (detalhamento): texturas de imagem CC0 entram por tipo/material (`materiais.aplicar_imagens`); a cor
continua a do archtools (a imagem só dá variação de tom, rugosidade e relevo). Sem as imagens, fica o
procedural. Materiais `PROPRIOS` (capas de LP, tela, cromado) não recebem a `cor` geral do item.
Na P4, **todo item com `produto:` visível nas câmeras precisa de `modelo` 3D detalhado** (o mais fiel
possível ao produto: forma, encosto, pés, almofadas): é ele que passa a forma do móvel para a IA da P5
(`archtools ia` recusa produto que seja só caixa). Fotos de produto NÃO vão para a IA.

P5 (acabamento com IA, skill `render-final`): **FLUX.2 [max] edit** na fal (`fal-ai/flux-2-max/edit`).
Cada vista leva render Cycles + mapa de profundidade exato do Blender + texto das máscaras (onde fica
cada parede e objeto) + cores fixas (`ia.fixas`). VISTA MESTRA (`ia.mestra`, ex. porta-dia) sai primeiro;
as outras de dia recebem a mestra como referência de aparência; as de noite recebem a de DIA da mesma
câmera (só a luz muda). Sementes `[21, 7]` (a 2ª só com aderência < 0,85). A aderência mede contornos e
não pega objeto inventado: a escolha final é visual, com o usuário (`archtools ia-selecionar`). Custo
(2026-11-23): ≈ US$ 0,16 a mestra e 0,22 por vista/semente — estimar e combinar teto ANTES de rodar.
Testados e descartados: Gemini (deforma o espaço), FLUX.1 depth (inventa objetos e cores), inpainting
por região, planta baixa e closes como referência, fotos de produto.

Estilo: skill `arquiteto`. Cada ambiente (ou a casa toda) tem um arquiteto principal + acentos;
cores/materiais/luz vêm de `archtools estilo` (nunca de cabeça). Comparar = uma proposta por combinação.
Imagens com estilo: `conceito.yaml` (cor por parede/teto/item + luzes das luminárias)
→ `archtools cena` valida contra o estilo resolvido e exporta cores/luzes; o Blender não escolhe cor
nenhuma (o que não tiver aparência definida sai em cinza de marcação e vai para o relatório)
→ Blender `--periodo ambos` (dia: sol; noite: só as luminárias). Luz fiel = `--motor cycles`
(~40 s por quadro 1280×720 na CPU): só entra luz pela janela e pela porta. O Eevee é rascunho rápido:
a luz do céu vaza pelas paredes e o interior sai claro e chapado. Não recolorir produtos com `cor_real`.

## Convenções da geometria

- Unidade: **milímetros**, inteiros. Coordenadas cartesianas; x para a direita, y para cima.
- Origem: definida em `geometria.yaml` (`origem`), um ponto físico identificável.
- Ambiente = polígono da **face interna** das paredes (o que se mede com trena), vértices em ordem.
- Parede `i` de um ambiente = segmento do vértice `i` ao vértice `i+1` (o último fecha no primeiro).
- Abertura = parede + distância a partir do vértice inicial dessa parede + largura (+ altura, peitoril).
- `posicao` (opcional) no ambiente: vértices e pontos fixos passam a ser relativos a ela (decisão 0003).
- `tipo` do ambiente: `interno` | `varanda` | `externo` (descoberto, sem pé-direito) | `tecnico`.
  O quadro de áreas soma por tipo.
- `cercamentos`: limites lineares (tela, muro), em coordenadas globais, com altura.

## Ambiente do usuário

- Windows 11, 32 GB RAM, GPU integrada Intel Iris Xe (sem CUDA, sem VRAM dedicada).
  Consequência: Blender ok (Eevee; Cycles na CPU); IA de imagem local inviável → serviço na nuvem (fal, FLUX.2; chave em ~/.archtools/fal.key).
- Preferir ferramentas gratuitas ou de baixo custo.
- **Blender 5.3** (winget, 2026-11-17), fora do PATH:
  `& "C:\Program Files\Blender Foundation\Blender 5.3\blender.exe" --background --python <script> -- <args>`
  Python embutido 3.13 (sem shapely) → toda geometria é calculada no `archtools`; o Blender só monta a cena.

## Fases (por ambiente; decididas em 2026-11-18)

- **P1 Levantamento** — geometria do apartamento (concluída; reabre quando chega medição nova).
- **P2 Projeto do ambiente** — 2a briefing · 2b conceito · 2c layout (+ blockout no Blender).
- **P3 Preview e refinamento** — design completo renderizado; volta a P2 a cada mudança.
- **P4 Detalhamento** — mais fidelidade de modelos e materiais, sem mudar decisões.
- **P5 Render final** — câmeras definitivas, Cycles; acabamento FLUX.2 com vista mestra, rotulado
  "ILUSTRATIVA (IA)" (o render do Blender continua sendo a referência).
- **P6 Entrega** — lista de compras, quantidades, pontos elétricos, marcenaria.

A fase de cada ambiente é **calculada** (`archtools status`), não escrita à mão. A auditoria de
consistência é contínua: `status` aponta saídas desatualizadas e arquivos aprovados alterados sem
decisão. Roteiro de implementação: `docs/proposta-arquitetura-v2.md` (§7, §8).
