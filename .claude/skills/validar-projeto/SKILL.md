---
name: validar-projeto
description: Roda as validações determinísticas do archtools sobre um projeto e explica os resultados ao usuário, separando erros, avisos e itens não verificáveis. Use após qualquer alteração em geometria.yaml, quando o usuário pedir para validar/conferir o projeto, ou antes de gerar plantas, modelos ou imagens.
---

# Validar projeto

1. Rodar, a partir da raiz do repositório:
   ```bash
   uv run --project tools archtools validar projetos/<projeto>
   uv run --project tools archtools areas projetos/<projeto>
   uv run --project tools archtools pendencias projetos/<projeto>
   ```
   Se houver erro de esquema (exit 2), mostre a mensagem e pare: o YAML precisa ser
   corrigido antes de qualquer outra análise.

2. Apresentar ao usuário, nesta ordem:
   - **Erros** — inconsistências. Para cada um, diga que dado o causa e se está
     baseado em dados estimados. Proponha como investigar (ex.: remedir a parede X),
     **não** proponha mudar números para o erro sumir.
   - **Avisos** — o que falta para as próximas fases.
   - **Não verificáveis** — regras que não puderam rodar por falta de dados; aponte
     para `pendencias.md`.
   - **Quadro de áreas** — copie a saída do comando; não recalcule nada à mão.

3. Se um erro só existe por causa de um valor estimado, sugira confirmar esse valor
   com trena como próximo passo.

4. Nunca declare o projeto "validado" se houver erros. Se houver itens não verificáveis,
   diga "validado parcialmente" e cite quantos.
