---
name: registrar-decisao
description: Registra uma decisão de projeto (layout, material, medida adotada, resolução de conflito) em projetos/<projeto>/decisoes/ e atualiza requisitos.md quando aplicável. Use quando o usuário decidir algo, aprovar uma proposta, escolher entre opções ou autorizar uma mudança de geometria.
---

# Registrar decisão

1. Descobrir o próximo número: maior `NNNN` em `projetos/<projeto>/decisoes/` + 1
   (começa em `0001`).

2. Criar `decisoes/NNNN-titulo-curto-com-hifens.md`:

   ```markdown
   # NNNN — Título

   - **Data:** AAAA-MM-DD
   - **Estado:** aceita | substituída por NNNN | revogada
   - **Decidido por:** usuário (citar a mensagem/resumo da autorização)
   - **Requisitos relacionados:** R00X, ...

   ## Contexto
   O problema, com números vindos do archtools (indicar status: confirmado/estimado).

   ## Opções consideradas
   - A — ... (prós/contras)
   - B — ...

   ## Decisão
   O que foi escolhido e por quê.

   ## Consequências
   O que muda nos arquivos (ex.: "geometria.yaml: parede 2 da sala passa de estimado
   para confirmado, 3420 mm") e o que fica pendente.
   ```

3. Só registre como decidido o que o **usuário** decidiu. Sugestões do agente que
   não foram aprovadas não viram decisão.

4. Decisões não são editadas depois de aceitas: se mudar, crie uma nova e marque a
   antiga como "substituída por NNNN".

5. Se a decisão afeta um requisito, atualize a linha correspondente em `requisitos.md`.
