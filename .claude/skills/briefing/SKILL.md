---
name: briefing
description: Conduz a entrevista de briefing de um ambiente (uso, rotina, quem usa, itens existentes e obrigatórios, gostos, restrições, orçamento, prioridades) e grava projetos/<p>/ambientes/<id>/briefing.md. Use quando o usuário quiser começar ou recomeçar um ambiente, mudar o uso de um cômodo, ou antes de propor conceito e layout de um ambiente sem briefing.
---

# Briefing de um ambiente (fase P2a)

O briefing é a entrada das fases seguintes (conceito e layout). Ele registra **o que o usuário
disse**, não o que o agente acha: nada de inventar rotina, gosto ou medida.

## 1. Preparar
- Confirmar o ambiente (`id` da `geometria.yaml`) e rodar
  `uv run --project tools archtools status projetos/<p>` para ver a fase atual e o que já existe.
- Ler o que já está registrado e **não perguntar de novo**: `requisitos.md` (linhas do ambiente),
  decisões em `decisoes/`, layout/conceito aprovados, propostas em aberto e o catálogo
  (`projetos/<p>/catalogo/produtos/`).
- Se o ambiente já tem layout ou conceito aprovado e o usuário quer recomeçar, deixar claro que o
  aprovado continua valendo até uma decisão nova substituí-lo.

## 2. Entrevistar (poucas perguntas por vez, com opções quando fizer sentido)
1. **Uso:** para que serve o ambiente; atividades principais e secundárias; horários.
2. **Quem usa:** quantas pessoas, visitas, pets; necessidades específicas (ergonomia, acessibilidade).
3. **Itens existentes/obrigatórios:** o que já existe ou já foi comprado e precisa ficar
   (produto, medidas e fonte das medidas → catálogo); o que pode sair.
4. **Armazenamento e equipamentos:** o que precisa ser guardado; o que fica à vista.
5. **Gostos e rejeições:** estilos, cores, materiais; referências (skill `referencia`).
6. **Restrições:** obra permitida (paredes estruturais, pontos elétricos/hidráulicos, forro),
   locação/condomínio, prazo.
7. **Orçamento e prioridades:** o que é essencial × desejável × talvez.
8. **Luz e conforto:** luz natural, uso noturno, ar-condicionado, ruído.

## 3. Gravar `projetos/<p>/ambientes/<id>/briefing.md`

```markdown
# Briefing — <ambiente> (<id>)

- **Data:** AAAA-MM-DD · **Fonte:** entrevista com o usuário (resumo das respostas)

## Uso e rotina
## Quem usa
## Itens existentes e obrigatórios
| Item | Situação (existe / comprado / obrigatório / pode sair) | Produto no catálogo |
## Armazenamento e equipamentos
## Gostos e rejeições
## Restrições
## Prioridades (essencial / desejável / talvez)
## Perguntas em aberto
```

- Cada item com medida conhecida vira uma entrada em `projetos/<p>/catalogo/produtos/<id>.yaml`
  (medidas com status e fonte — **nunca** inventar).
- Requisitos novos ou alterados: acrescentar linhas em `requisitos.md` (com ID, prioridade,
  ambiente e origem). O briefing explica; o `requisitos.md` lista.
- Mostrar o briefing ao usuário e pedir confirmação antes de seguir.

## 4. Depois
Briefing confirmado → `archtools status` mostra o ambiente em "P2b/P2c conceito e layout
(briefing feito)". Próximos passos: conceito (skill `arquiteto`) e layout (propostas em
`propostas/<ambiente>-<nome>/`, validadas com `archtools layout`).
