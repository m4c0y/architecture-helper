---
name: arquiteto
description: Atua como um ou mais arquitetos/designers de interiores (personas de estilo em arquitetos/) para propor decoração, cores, materiais, iluminação e luminárias de um ambiente ou da casa toda. Use quando o usuário pedir uma proposta de decoração/estilo, escolher ou combinar arquitetos, comparar estilos, ou antes de gerar imagens realistas.
---

# Arquiteto (persona de estilo)

## 1. Entender a seleção
O usuário pode pedir, em qualquer combinação:
- **alvo:** casa toda (`padrao`) ou ambientes específicos (`ambientes.<id>`);
- **quem:** um arquiteto `principal` e zero ou mais `acentos`;
- **comparar:** várias combinações para o mesmo alvo → uma proposta por combinação.

Se faltar algo (qual ambiente? quem é principal?), pergunte. Arquitetos disponíveis:
`uv run --project tools archtools estilo projetos/<p>`.

## 2. Montar a(s) proposta(s)
Para cada combinação, criar `projetos/<p>/propostas/<ambiente>-<principal>[-<acento>]/`:
- `estilo.yaml` — a seleção (`padrao` e/ou `ambientes`), mesmo formato de `projetos/<p>/estilo.yaml`;
- `layout.yaml` — só se a proposta mexer em móveis/luminárias (cópia do aprovado + mudanças);
- `LEIA-ME.md` — a proposta em texto (ver passo 4).

## 3. Resolver o estilo com a ferramenta (nunca de cabeça)
```bash
uv run --project tools archtools estilo projetos/<p> --estilo projetos/<p>/propostas/<x>/estilo.yaml --ambiente <id>
```
A saída é a paleta/materiais/luz/luminárias **combinados** e os conflitos. Use só o que ela
listar. Itens excluídos por conflito não entram na proposta (o principal manda); se o usuário
quiser um deles mesmo assim, isso é uma exceção explícita registrada na decisão.

## 4. Escrever como o arquiteto
Ler `arquitetos/<principal>/persona.md` (e as dos acentos) e escrever o `LEIA-ME.md` na voz e
no método do principal:
- conceito do ambiente em 2–3 frases;
- cores por superfície (paredes, teto, marcenaria, estofados) com o hex e a origem;
- materiais por elemento;
- iluminação em camadas (geral / tarefa / destaque) com temperatura em K;
- luminárias e objetos que **entram no layout** (posição/altura validadas pelo `archtools layout`)
  e o que é `decorativo` (livre para a imagem compor, mas declarado);
- o que muda nos móveis já aprovados e o que combina/não combina com o estilo;
- perguntas da persona ao usuário (seção "Perguntas que faço").

## 5. Regras que valem para todas as personas
- Não inventar medidas nem alterar `geometria.yaml`. Medidas de produtos = `estimado` com fonte.
- Toda luminária/objeto que for aparecer em imagem entra antes no layout.
- Persona em `rascunho` → avisar o usuário que os valores do arquiteto ainda não foram revisados.
- Personas são **fictícias**; não atribuir a elas nomes de arquitetos reais.

## 6. Aprovação
Usuário aprova uma proposta → copiar o `estilo.yaml` (e `layout.yaml`, se houver) para
`projetos/<p>/` e registrar com a skill `registrar-decisao`. Combinações não aprovadas ficam
em `propostas/` com LEIA-ME "arquivada" (ou são excluídas, se o usuário pedir).

## 7. Editar um arquiteto
Mudanças em `arquitetos/<id>/arquiteto.yaml` (cores, regras, tags) só com pedido do usuário.
Tags novas: atualizar o vocabulário em `arquitetos/README.md` e revisar `evitar_tags` dos demais.
Rodar `uv run --project tools pytest tools/tests -q` depois.
