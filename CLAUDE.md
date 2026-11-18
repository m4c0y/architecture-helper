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
projetos/<nome>/
  geometria.yaml            envelope: ambientes, aberturas, pé-direito, pontos fixos (FONTE DA VERDADE)
  layout.yaml               móveis aprovados (FONTE DA VERDADE do mobiliário; coords locais do ambiente)
  criterios.yaml            folgas de circulação (decisão 0008)
  estilo.yaml               arquitetos escolhidos (padrao / por ambiente; principal + acentos)
  estudos/                  buscas exaustivas de layout (scripts reproduzíveis)
  requisitos.md             o que o usuário quer/precisa
  pendencias.md             GERADO por `archtools pendencias` — não editar à mão
  decisoes/NNNN-titulo.md   registro de decisões
  fontes/                   material bruto do usuário (plantas, fotos, croquis) — somente leitura
  medicoes/                 scripts que medem as imagens de fontes/ (valores PX/PV) — reproduzíveis
  referencias/              imagens de inspiração + index.yaml
  propostas/                variações ainda não aprovadas (promovidas ficam com LEIA-ME "arquivada")
  saidas/                   GERADO: planta.png/svg, planta-layout.*, cena.json, 3d/ (renders + modelo.blend)
blender/construir_cena.py   lê cena.json e monta/renderiza no Blender (não calcula geometria)
.claude/skills/             procedimentos: ingerir-planta, validar-projeto, registrar-decisao, arquiteto
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
    projetos/apartamento/saidas/cena.json projetos/apartamento/saidas/3d [--cameras dorm2-se] [--res 1280x720] [--motor eevee|cycles] [--periodo dia|noite|ambos]
uv run --project tools pytest tools/tests -q
```

Layouts novos: proposta em `propostas/<nome>/layout.yaml` → `archtools layout` (0 erros) → aprovação do
usuário → copiar para `layout.yaml` + decisão. Móveis são caixas simples (mesa = tampo + pernas).

Estilo: skill `arquiteto`. Cada ambiente (ou a casa toda) tem um arquiteto principal + acentos;
cores/materiais/luz vêm de `archtools estilo` (nunca de cabeça). Comparar = uma proposta por combinação.
Imagens com estilo: `acabamentos.yaml` na proposta (cor por parede/teto/móvel + luzes das luminárias)
→ `archtools cena --layout <proposta>/layout.yaml` valida contra o estilo resolvido e exporta cores/luzes
→ Blender `--periodo ambos` (dia: sol; noite: só as luminárias). Não recolorir produtos de cor conhecida.

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
  Consequência: Blender ok (Eevee; Cycles na CPU); IA de imagem local inviável → usar serviço na nuvem (fase 3).
- Preferir ferramentas gratuitas ou de baixo custo.
- **Blender 5.3** (winget, 2026-11-17), fora do PATH:
  `& "C:\Program Files\Blender Foundation\Blender 5.3\blender.exe" --background --python <script> -- <args>`
  Python embutido 3.13 (sem shapely) → toda geometria é calculada no `archtools`; o Blender só monta a cena.

## Fases

1. Esquema + validação + planta 2D + histórico. (concluída)
2. **(atual)** Layout de móveis, regras de circulação, modelo 3D no Blender (headless, gerado do YAML).
   Feito: escritório (dorm2) aprovado e renderizado. Falta: demais ambientes.
3. Imagens realistas (render do Blender como base + serviço de IA na nuvem).
4. Auditoria de consistência entre saídas e fonte da verdade.
