# Arquitetos (personas de estilo)

Cada pasta é um arquiteto **fictício** com um estilo próprio, reutilizável em qualquer projeto:

| Arquivo | Conteúdo |
|---|---|
| `persona.md` | como o arquiteto pensa, prioriza e o que pergunta (texto para o agente) |
| `arquiteto.yaml` | dados: paleta (hex), materiais, iluminação (K), luminárias, regras e `evitar_tags` |
| `referencias/` | imagens de inspiração do estilo + `index.yaml` |

## Seleção no projeto

`projetos/<p>/estilo.yaml` (aprovado, via decisão) ou `projetos/<p>/propostas/<x>/estilo.yaml`:

```yaml
padrao:                      # casa toda (opcional)
  principal: brasileiro_contemporaneo
ambientes:                   # sobrepõe o padrão (opcional)
  dorm2: {principal: industrial, acentos: [mid_century]}
```

- **principal**: define base da paleta, materiais, temperatura de cor e regras.
- **acentos**: contribuem só com cores de destaque, materiais e luminárias.
- Item de acento com tag listada em `evitar_tags` do principal é excluído e relatado como conflito.
- **Comparar arquitetos**: uma proposta por combinação (`propostas/escritorio-industrial/`,
  `propostas/escritorio-japandi/`...); a aprovada vira `estilo.yaml` + decisão.

```bash
uv run --project tools archtools estilo projetos/apartamento                       # lista + seleção aprovada
uv run --project tools archtools estilo projetos/apartamento --estilo projetos/apartamento/propostas/x/estilo.yaml --ambiente dorm2
```

## Vocabulário de tags (para `evitar_tags` funcionar entre arquitetos)
metal_preto, cromado, latao, madeira_clara, madeira_media, madeira_escura, madeira_brasileira,
nogueira, concreto, tijolo, terracota, palha, linho, couro, filamento, cor_saturada, pastel,
estampa, ornamento, laca_brilho, plastico_brilhante, cinza_frio, rustico.
Tag nova → acrescentar aqui e revisar os `evitar_tags` dos outros arquitetos.
