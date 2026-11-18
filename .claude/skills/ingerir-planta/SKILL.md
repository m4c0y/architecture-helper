---
name: ingerir-planta
description: Transforma uma planta baixa, croqui, foto ou lista de medidas do usuário em entradas para geometria.yaml, marcando cada valor como confirmado, estimado ou desconhecido. Use quando o usuário enviar uma planta, cotas, medições de trena ou pedir para "cadastrar" ambientes.
---

# Ingerir planta

Objetivo: levar informação bruta para `projetos/<projeto>/geometria.yaml` **sem inventar nada**.

## Passos

1. **Guardar a fonte.** Peça ao usuário para colocar o arquivo em
   `projetos/<projeto>/fontes/` (ou confirme onde está). A fonte nunca é editada.

2. **Ler e transcrever, não interpretar além do visível.** Monte uma tabela no chat:

   | Elemento | Valor lido | Como foi obtido | Status proposto |
   |---|---|---|---|

   - Cota escrita legível na planta → `confirmado`, fonte: "cota na planta <arquivo>".
   - Medida de trena informada pelo usuário → `confirmado`, fonte: "trena, <data>, <quem>".
   - Valor deduzido (soma/diferença de cotas, proporção, escala gráfica, desenho sem cota)
     → `estimado`, fonte explicando a dedução.
   - Ilegível, ausente ou ambíguo → `desconhecido`, valor null. **Não use valores típicos**,
     a menos que o usuário peça explicitamente: aí o valor é `estimado`, a fonte cita a decisão
     que autorizou (ex.: "mercado (decisão 0006)") e o item continua em `pendencias.md`.
   - Leitura visual da imagem é sempre **no máximo `estimado`**.
   - Material da construtora: se traz informação técnica (cotas, pé-direito, pontos), vai para
     `fontes/`; se é só ilustrativo (planta decorada), vai para `referencias/` e não gera geometria.

   **Medir em imagem = script versionado.** Toda medição por pixels (fonte "PX"/"PV") é feita
   por um script em `projetos/<projeto>/medicoes/` (calibração da escala por cotas, varreduras,
   conversão para mm), nunca por comandos soltos. Valores lidos visualmente (centros de símbolos,
   raios de arcos) ficam como constantes no script. Atualize `medicoes/README.md`.

3. **Definir a origem e a orientação** com o usuário (um canto físico identificável),
   antes de calcular coordenadas.

4. **Converter em vértices** (face interna, em ordem, mm). Mostre como cada coordenada
   foi obtida a partir das cotas. Coordenada que depende de valor estimado é estimada.
   Quando as dimensões internas são cotadas mas o encaixe na planta não (ex.: espessura de
   parede desconhecida), use `posicao` estimada + vértices relativos confirmados (decisão 0003).

5. **Pedir autorização.** Mudanças grandes (ambientes novos, rodada de ingestão) vão primeiro
   para `propostas/<nome>/geometria.yaml`; rode validar + planta nela e mostre ao usuário.
   Só depois de um "sim" explícito copie para `geometria.yaml` (o sistema também pedirá
   confirmação da edição) e registre a promoção em `decisoes/`. Acréscimos pontuais pedidos
   pelo usuário podem ir direto, mostrando o trecho.

6. **Verificar com as ferramentas:**
   ```bash
   uv run --project tools archtools validar projetos/<projeto>
   uv run --project tools archtools planta projetos/<projeto>
   uv run --project tools archtools pendencias projetos/<projeto>
   ```
   Abra `saidas/planta.png` e compare visualmente com a fonte. Relate divergências ao
   usuário — não "corrija" a geometria por conta própria.

7. **Registrar** com a skill `registrar-decisao` qualquer escolha feita (ex.: origem,
   como tratar uma cota conflitante).

## Conflitos

Se duas fontes discordam (ex.: soma das cotas parciais ≠ cota total), **não escolha**:
apresente as duas, a diferença em mm (calculada) e pergunte ao usuário. Até a resposta,
o valor fica `estimado` com a fonte mencionando o conflito.
