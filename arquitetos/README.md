# Arquitetos (personas de estilo)

Cada pasta é um arquiteto **fictício** com um estilo próprio, reutilizável em qualquer projeto.
Um estilo é **dado**, não uma skill: a skill `arquiteto` carrega a pasta certa sob demanda.
Adicionar um estilo = criar uma pasta.

| Arquivo | Conteúdo | Quem lê |
|---|---|---|
| `arquiteto.yaml` | o que uma ferramenta verifica: paleta (hex, papel, tags), materiais, iluminação (K), luminárias, regras e `evitar_tags` | `archtools` |
| `persona.md` | como o estilo pensa: filosofia, móveis, proporções, decoração, elementos arquitetônicos, combinações, erros comuns, referências que faltam, perguntas ao usuário | o agente |
| `referencias/` | biblioteca de imagens do estilo + um `<imagem>.yaml` por imagem (skill `referencia`) | agente, crítico, `archtools` |
| `tags.yaml` (nesta pasta) | vocabulário de tags comum a personas e referências | `archtools` |

Regra prática: **se uma ferramenta precisa checar, vai no YAML; se é para entender, vai no Markdown.**

## Estilos disponíveis

| id | Persona | Estilo |
|---|---|---|
| `brasileiro_contemporaneo` | Estúdio Terra | Brasileiro contemporâneo |
| `industrial` | Estúdio Oficina | Industrial |
| `japandi` | Estúdio Ma | Minimalista japandí |
| `mid_century` | Estúdio Atômico | Mid-century moderno |
| `minimalista` | Ateliê Linha | Minimalista |
| `rustico_moderno` | Casa Tramela | Rústico moderno |

Todas em `estado: rascunho` até serem calibradas com referências e revisadas pelo usuário.

## Seleção no projeto

`projetos/<p>/estilo.yaml` (aprovado, via decisão) ou `projetos/<p>/propostas/<x>/estilo.yaml`:

```yaml
padrao:                      # casa toda (opcional)
  principal: brasileiro_contemporaneo
ambientes:                   # sobrepõe o padrão (opcional)
  escritorio: {principal: industrial, acentos: [mid_century]}
```

- **principal**: define base da paleta, materiais, temperatura de cor e regras.
- **acentos**: contribuem só com cores de destaque, materiais e luminárias.
- Item de acento com tag listada em `evitar_tags` do principal é excluído e relatado como conflito.
- **Comparar arquitetos**: uma proposta por combinação; a aprovada vira `estilo.yaml` + decisão.

```bash
uv run --project tools archtools estilo projetos/<p>                                  # lista + seleção aprovada
uv run --project tools archtools estilo projetos/<p> --estilo projetos/<p>/propostas/x/estilo.yaml --ambiente <id>
uv run --project tools archtools referencias arquitetos                               # valida as bibliotecas
uv run --project tools archtools paleta arquitetos/<id>/referencias/<img>.jpg --arquiteto <id> [--gravar]
```

## Tags

O vocabulário está em [`tags.yaml`](tags.yaml); o `archtools` recusa tag fora dele (em personas
e em referências). Tag nova → acrescentar lá e revisar os `evitar_tags` de cada persona.

## Imagens e licenças

As imagens das bibliotecas são versionadas neste repositório **público**. Só entram imagens
próprias ou com licença que permita redistribuição; o YAML de cada imagem registra `origem`,
`licenca` e `atribuicao` (obrigatória quando a licença exige).
