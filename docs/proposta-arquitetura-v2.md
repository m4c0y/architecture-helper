# Architecture proposal v2 — AI-assisted interior design assistant

> **Status:** open questions settled (§8, 2026-11-18); implementation in progress (§8, progress table).
> Written in English because the request was; file and field names stay in Portuguese to match
> the repository (`conceito.yaml`, not `approved-concept.yaml` — see §6.1).

---

## 0. Summary (the short version)

1. **The current project is a solid base, not a prototype to replace.** Its core idea — YAML as
   source of truth, every number with a status, deterministic `archtools`, Blender as a dumb
   renderer, proposals → user approval → decision record — is exactly the architecture you are
   describing. Most of this proposal *extends* it.
2. **One coordinating agent + knowledge as data/skills; subagents only where independence
   matters** (parallel style proposals, design critique, batch image analysis). No agent per
   style or per discipline.
3. **Two approved design artifacts per room, as you suggested, plus a product catalog** to avoid
   duplicating dimensions: `layout.yaml` (what + where), `conceito.yaml` (how it looks). The
   concept references layout item ids; the layout references catalog products.
4. **Merge your phases 3 and 4** (Preview and Refinement are one loop), **make "detailed
   modeling" an on-demand asset upgrade**, and **add a hand-off phase** (shopping list,
   quantities, electrical points, carpentry) — that is where the project pays off in real life.
5. **Room state is computed, not stored**: approvals live in decision front matter (with a
   content hash), outputs carry a manifest of their inputs, and `archtools status` derives
   phase, pending items and stale outputs.
6. **First thing to do: commit the repository.** It has no commits. "Preserve previous
   versions" has no foundation until git holds the history.

---

## 1. Current implementation assessment

### 1.1 What exists

| Area | What is there | Evidence |
|---|---|---|
| Geometry | `geometria.yaml`: 11 rooms, openings, fixed points, enclosures, `posicao` per room; every value is a `Medida` with `confirmado/estimado/desconhecido` + `fonte` | `projetos/apartamento/geometria.yaml`, `schema.py` |
| Validation | Schema + geometric consistency, area table by room type, generated `pendencias.md` | `validacao.py`, `relatorios.py` |
| 2D plans | `planta.png/svg`, `planta-layout.*` with furniture, clearances and zoom per room | `planta2d.py` |
| Measuring images | Reproducible pixel-measurement scripts with calibration | `medicoes/` |
| Layout | Furniture schema (centre, `frente`, dims as `Medida`, elevation, upholstery shape, `produto`, `modelo`, `associado`); checks: inside room, collisions, clearances from `criterios.yaml`, door swing, reachability from the door, fixed points, window coverage | `layout.py`, decision 0008 |
| Layout studies | Scripted exhaustive layout searches | `estudos/busca_escritorio*.py` |
| Style | 4 fictitious personas (`persona.md` + `arquiteto.yaml` + empty `referencias/`); deterministic combination principal + accents with `evitar_tags` conflicts | `arquitetos/`, `estilo.py` |
| Finishes | `acabamentos.yaml`: colour per wall/ceiling/furniture/piece + lights per fixture, validated against the *resolved* style; K comes from the style | `acabamentos.py` |
| 3D export | `cena.json`: walls with openings cut, glass, floors, ceilings, furniture boxes or parametric models, cameras, explicit `suposicoes` | `cena.py`, `modelos.py` (11 parametric product models) |
| Blender | Headless build + render, Eevee/Cycles, day/night, per-camera PNG + `modelo.blend` | `blender/construir_cena.py` |
| Process | Skills: `ingerir-planta`, `validar-projeto`, `registrar-decisao`, `arquiteto`; 10 decisions; proposals folder with LEIA-ME | `.claude/skills/`, `decisoes/`, `propostas/` |
| Tests | 66 passing (`pytest tools/tests -q`, run today) | `tools/tests/` |

Room progress: **dorm2 (office)** has an approved layout (decision 0010), a blockout render,
and two *unapproved* style proposals (`dorm2-japandi`, `dorm2-mid_century-industrial`) with
finishes and day/night renders. No other room has a layout.

### 1.2 What works well (preserve)

- **Truth hierarchy and status propagation.** This is the project's spine; everything new
  should follow it (I reuse the same idea for references and preferences in §4).
- **Proposal → approval → decision → promotion** flow. It already gives iteration without
  restarting.
- **Blender does not compute geometry.** `cena.json` is a clean contract.
- **Style resolution is deterministic** (`archtools estilo`), and finishes are validated against
  it. This is the right way to keep "AI taste" honest.
- **Reproducible scripts** for measurements and layout searches.

### 1.3 Gaps and problems found

| # | Gap | Why it matters |
|---|---|---|
| G1 | **No git history** (no commits; everything untracked) | Versioning, "revert a decision", diffs between proposals all depend on it |
| G2 | **Stale outputs are invisible.** `saidas/3d/` still has `dorm2-close-frigobar.png`, but decision 0010 removed the fridge | The "what must be regenerated?" question has no answer today |
| G3 | **Blender invents design.** `construir_cena.py` has a `CORES` dict with category defaults (e.g. sofa = blue). The approved-layout render shows a blue sofa nobody chose | Violates your principle "Blender must not invent design decisions" |
| G4 | **The concept is scattered**: `estilo.yaml` (who), `acabamentos.yaml` (colours), `LEIA-ME.md` (materials, decor, rationale). Materials are only colour + metal/roughness inferred from tags | No single "approved concept"; materials like brick/wood panel cannot be represented |
| G5 | **Decor is prose only** ("decorativo" section of LEIA-ME). Rugs, art, cushions, curtains, books are not in the model | Preview cannot show the complete design |
| G6 | **Product data is duplicated and unstructured.** Sofa dims are in `layout.yaml` *and* in `referencias/index.yaml` free text; product models live as Python functions without metadata | Changing a product means editing several places |
| G7 | **No room-level briefing.** `requisitos.md` is project-wide; "Moradores e uso" is empty | Phase 2 has no explicit input |
| G8 | **References are thin**: `gosto/nao_gosto` empty, persona libraries empty, no analysis metadata, no distinction AI-observed vs user-confirmed | Style personas remain `rascunho` with nothing to calibrate them |
| G9 | **Phase/state lives in prose** (`CLAUDE.md` "Fases") | Can't answer "which phase is each room in" mechanically |
| G10 | **Constraint inputs missing for planning**: outlets/switches, floor finish, real wall thickness, ceiling (forro) | Lighting and layout decisions get blocked (e.g. the Japandi proposal couldn't place recessed lights) |
| G11 | One `layout.yaml` for the whole apartment | Approvals and staleness can't be per room |

---

## 2. Proposed workflow

### 2.1 Evaluation of your phases

| Your phase | Verdict | Reason |
|---|---|---|
| 1 Apartment setup | Keep; done | But it never fully closes: outlets, floor, wall thickness, forro arrive later. Treat as a **survey that can reopen**, feeding `pendencias.md` |
| 2 Room design & spatial planning | Keep, **split into three steps with a loop** (2a briefing, 2b concept, 2c layout & selection) | Concept and layout are iterative, not sequential: a mandatory sofa constrains the style; a style suggests furniture types that change the layout |
| 3 Design preview | **Merge with 4** | The preview *is* the refinement tool. A change in refinement is just a change to concept/layout followed by regeneration. Two phases create a fake gate |
| 4 Design refinement | ↑ merged | Exit criterion of the merged phase: "visual specification approved" |
| 5 Detailed 3D modeling | Keep, but **re-scope as asset-fidelity upgrade on demand** | Detail is per item (hero pieces), not per room. Most value sits in 5–10 objects. It's mostly asset-library work reusable across rooms |
| 6 Final rendering | Keep | Plus optional AI enhancement of renders for presentation (§5.6) |
| — | **Add: 7 Hand-off / execution** | Shopping list with links, paint m² per colour, rug sizes, electrical points to install, carpentry sketches. This turns the design into something you can buy and build |
| — | **Add: house-level concept (light)** | Rooms designed one by one can clash. A `padrao` style already exists in `estilo.yaml`; give it a short house brief (shared floor, transitions, palette continuity) |
| — | **Consistency audit: continuous, not a phase** | Original phase 4 of `CLAUDE.md`. Becomes `archtools status` (§6.4), runnable any time |

### 2.2 Phases (proposed)

```
 P1 Survey (apartment)          continuous; reopens when new measurements arrive
   │
 P2 Room design  ┌─ 2a Briefing ─┐
                 │               ▼
                 │   2b Concept ◄──► 2c Layout & selection  (+ blockout renders)
                 │       │                  │
                 └── approve conceito.yaml  approve layout.yaml
   │
 P3 Preview & refinement        full-design renders; loop back to 2b/2c on any change
   │  approve "visual spec" (= approved conceito + layout + chosen cameras, at a git commit)
 P4 Detailing (on demand)       upgrade hero assets/materials; no design changes allowed
   │
 P5 Final rendering             Cycles, final cameras, optional AI polish (labelled)
   │
 P6 Hand-off                    shopping list, quantities, electrical/carpentry notes
```

| Phase | Purpose | Inputs | Outputs | Done when |
|---|---|---|---|---|
| P1 Survey | Physical truth | sources, measurements | `geometria.yaml`, `pendencias.md` | validate = 0 errors; unknowns listed (never "complete" forever) |
| 2a Briefing | Understand the room | user interview, `requisitos.md` | `ambientes/<id>/briefing.md`; requirement lines in `requisitos.md` | user confirms the briefing |
| 2b Concept | Visual direction | briefing, references, style personas | proposals → approved `conceito.yaml` + `conceito.md` | user approves; `archtools conceito` 0 errors |
| 2c Layout & selection | What goes where | briefing, geometry, catalog, concept (furniture typology) | proposals → approved `layout.yaml`; blockout renders | `archtools layout` 0 errors; warnings accepted in decision |
| P3 Preview & refine | See the whole design | approved concept + layout, assets, materials | renders (day/night, named cameras), critique notes | user approves visual spec |
| P4 Detailing | Fidelity, not decisions | approved spec | upgraded assets/material textures | renders differ only in fidelity (critic checks) |
| P5 Final render | Presentation | detailed scene | final images, optional AI-polished versions | user approves images |
| P6 Hand-off | Make it real | approved spec + catalog | `entrega.md` (list, links, quantities, electrical points) | user has what they need to buy/hire |

### 2.3 Dependencies and revisiting

- Every artifact has explicit inputs; changing an input marks dependents **stale**, never
  rewrites them. Example: new reference → may produce a concept *proposal*; approved
  `conceito.yaml` stays as is until you approve the change.
- **Going back is just editing upstream through a proposal.** Phase is *derived* from which
  artifacts are approved and fresh (§6.4), so "revisiting phase 2" needs no ceremony: the room
  simply shows as P2 again until the new concept is approved.
- Approval of a downstream artifact records the hashes of what it was approved against, so
  "layout approved on concept v1, concept is now v2" is detectable.

---

## 3. Agent and skill architecture

### 3.1 The core trade-off

| Option | Gains | Costs |
|---|---|---|
| Many specialised agents (designer, planner, lighting, furniture, materials, critic, per-style) | Role clarity on paper | Each agent starts cold and re-reads the room; hand-off contracts between them; coordination logic; contradictory outputs to reconcile; much higher token cost. Disciplines in a single room are **tightly coupled** (a lamp is lighting, furniture *and* layout) |
| One agent + skills + data | One shared context; disciplines combine naturally; cheap | Risk of "one voice" — styles bleed into each other, self-critique is weak |

**Recommendation: one coordinating agent (the main session = Interior Designer), knowledge in
skills and data files, and subagents only where *independence* is the point:**

| Subagent (`.claude/agents/`) | Why a separate context is worth it |
|---|---|
| `proponente-estilo` (style proposer) | Comparing or combining styles: each persona drafts a proposal **without seeing the others**, so you get genuinely different options instead of three variations of one idea. Run in parallel; the coordinator synthesises |
| `critico` (design critic) | Fresh, adversarial review of a proposal or render against the brief, concept and style rules. Self-review by the author is weak; independence is the value |
| `analista-referencias` (reference analyst) | Batch vision analysis of many images without flooding the main context; returns structured YAML |

Space planning, lighting, furniture and materials are **skills** (procedures + checklists +
domain knowledge), not agents: their value is knowledge, and they must operate on the same
shared context.

### 3.2 Skills

Existing (keep): `ingerir-planta`, `validar-projeto`, `registrar-decisao`, `arquiteto`.

| Skill | Responsibility | Tools it calls |
|---|---|---|
| `briefing` (new) | Interview script per room type (purpose, users, routines, mandatory/existing items, likes/dislikes, budget, priorities); writes `briefing.md` + requirement lines | — |
| `arquiteto` → `conceito` (evolve) | Build concept proposals from personas; scenarios 1–5 below; writes `conceito.yaml` + `conceito.md` | `archtools estilo`, `archtools conceito` |
| `planejar-layout` (new) | Space-planning knowledge (zones, ergonomics, sight lines, door/window/outlet rules, search scripts) | `archtools layout`, `estudos/` |
| `iluminacao` (new) | Layers, K per activity, fixture choice, what needs forro/electrical points; flags what the tools can't compute (lux) | `archtools estilo`, layout |
| `produto` (new) | Register a real product in the catalog from a listing/photo: dims with status, source, link, asset mapping | catalog schema validation |
| `referencia` (new) | Ingest + analyse images (delegates batch to `analista-referencias`), confirm preferences with the user | palette script |
| `preview` (new) | `cena` + Blender pipeline, camera choice, render report, staleness check | `archtools cena`, Blender |

Seven to eight skills total. Each one is loaded only when its description matches, so the
cost of having them is small.

### 3.3 Style knowledge: data, not one skill per style

Styles should **not** be individual Claude Code skills. A style is *data* consumed by one
procedure (the concept skill). Eight style skills would mean eight always-visible descriptions
and eight copies of the same procedure. The existing `arquitetos/<id>/` layout is already the
right shape; extend it:

| File | Holds | Read by |
|---|---|---|
| `arquiteto.yaml` | Only what tools check: palette (hex, role, tags), materials (+ material catalog ids), lighting K, fixture types, `evitar_tags`, **new:** furniture typology tags, compatible accents | `archtools` |
| `persona.md` | How the style thinks: principles, proportions/composition, furniture character, decor, architectural features, **common mistakes**, questions to ask | the agent (LLM) |
| `referencias/` | Curated images + sidecar analysis (§4) | agent, critic |

Rule of thumb: **if a tool needs to check it, YAML; if a mind needs to understand it,
Markdown.** "Common mistakes" are mostly Markdown, but the mechanisable ones become tags
(`evitar_tags`) so the critic can be backed by a deterministic check.

Adding a style (Scandinavian, Minimalist, Modern rustic, Eclectic, Contemporary…) = adding a
folder. Personas stay `rascunho` until you calibrate them with references.

### 3.4 Collaboration patterns for your five scenarios

| Scenario | Flow |
|---|---|
| 1. No style yet | Coordinator reads briefing + liked/disliked references → `archtools` ranks personas by tag overlap with confirmed preferences (deterministic shortlist) → 2–3 `proponente-estilo` in parallel → comparison table + renders on the *same* approved layout → user picks |
| 2. Preferred style | Coordinator alone with the `conceito` skill + that persona |
| 3. Combination | Option A (cheap): principal + accents via `archtools estilo` (exists). Option B (richer): each style drafts independently, coordinator synthesises, **critic checks coherence**; conflicts reported by tags, user resolves |
| 4. Mandatory items | Items flagged `existente/obrigatorio` in layout; their known colours/materials are *inputs* to the concept (never recoloured — rule already exists); persona compatibility checked by tags (e.g. walnut rack → `nogueira` tag vs persona `evitar_tags`) |
| 5. Compare proposals | One proposal folder per option, same cameras, same layout unless the layout is the variable; `critico` writes a comparison; renders side by side |

---

## 4. Reference management

### 4.1 Three epistemic levels (mirrors geometry status)

| Level | Meaning | Who sets it | Where |
|---|---|---|---|
| `observado` | Characteristic identified by AI or script | analyst agent / script | `analise:` block of the sidecar |
| `preferencia` | User confirmed they like/dislike it | user | `usuario:` block of the sidecar, or briefing |
| `aprovado` | Adopted for a room | user, through a decision | `conceito.yaml` → `referencias:` |

An AI observation never becomes a preference without your confirmation; a preference never
becomes a design decision without an approved concept. Same discipline as `estimado` vs
`confirmado`.

### 4.2 Directory structure

```
catalogo/                            reusable across projects (repo root)
  produtos/<id>.yaml (+ fotos/)       real products: dims with status, link, asset id (§5.5)
  materiais/<id>.yaml (+ texturas/)   material catalog: PBR params, procedural preset or texture
ativos/<id>/ativo.yaml (+ modelo)     3D representations (§5.5)
arquitetos/<id>/referencias/          style libraries: <img> + <img>.yaml sidecars
projetos/<p>/referencias/             user-provided images: <img> + <img>.yaml sidecars
  geradas/                            AI-generated moodboards, clearly separated (§5.6)
projetos/<p>/ambientes/<id>/conceito.yaml   approved references = ids listed here (no copies)
```

- **One sidecar YAML per image** instead of one growing `index.yaml`: the analysis can be long,
  and per-file sidecars make "analyse new images" a simple glob. The current `index.yaml`
  migrates into sidecars.
- **Approved-for-room is a reference, not a copy.** Avoids duplicate images and drift.
- A product photo used to define dims belongs to `catalogo/produtos/`, not to `referencias/`
  (today `sofa-chaise-194.webp` plays both roles).

### 4.3 Sidecar metadata (example)

```yaml
# projetos/apartamento/referencias/sala-tijolo-01.jpg.yaml
id: sala-tijolo-01
origem: "Pinterest, enviada pelo usuário em 2026-11-20"
tipo: ambiente            # ambiente | movel | luminaria | objeto | paleta | revestimento | piso | material | produto
ambientes: [dorm2]        # onde o usuário pensa em usar (opcional)

analise:                  # nível: observado
  por: "analista-referencias, 2026-11-20"
  paleta:                 # extraída por SCRIPT (k-means), não a olho
    script: "tools: archtools paleta"
    cores: [{hex: "#9C4F36", fracao: 0.22}, {hex: "#2B2B2B", fracao: 0.15}]
  influencias: [{estilo: industrial, peso: alto}, {estilo: mid_century, peso: medio}]  # várias, sem forçar uma
  elementos:
    - {tipo: revestimento, descricao: "parede de tijolinho aparente", tags: [tijolo]}
    - {tipo: luminaria, descricao: "pendente domo preto sobre a mesa", tags: [metal_preto]}
    - {tipo: movel, descricao: "poltrona de couro conhaque, pés palito", tags: [couro, madeira_media]}
  luz: "quente, pontual, rasante na parede de textura"
  composicao: "uma parede de destaque; demais neutras; contraste alto"

usuario:                  # nível: preferencia (só com confirmação explícita)
  gosto: ["parede de tijolo", "pendente domo"]
  nao_gosto: ["poltrona de couro"]
  confirmado_em: 2026-11-20
```

Tags reuse the existing vocabulary in `arquitetos/README.md` — that is what lets `archtools`
compare references, personas and concepts deterministically (shortlist styles, flag that a new
reference conflicts with the approved palette, etc.). Proportions and dimensions read from a
reference are at most `estimado` and never feed geometry (decision 0004 already says so).

### 4.4 Analysis workflow

1. You drop images (any time) into `projetos/<p>/referencias/`.
2. `referencia` skill: deterministic part first (palette script), then vision analysis (batch →
   `analista-referencias`), writing `analise:`.
3. The agent shows the observations and **asks** what you like/dislike → `usuario:`.
4. If a room already has an approved concept, the agent produces an **impact note** (tag
   conflicts with the approved palette/materials, what it would change) and, only if you want,
   a new concept *proposal*. The approved concept is never touched automatically.
5. Promoting a project reference into a style library (`arquitetos/<id>/referencias/`) is an
   explicit action — that's how personas get calibrated out of `rascunho`.

---

## 5. Blender integration

### 5.1 Division of responsibilities (your list, validated with two amendments)

| Layer | Decides | Never does |
|---|---|---|
| AI agent | Interprets, proposes concept/selection/positions, analyses references, critiques | Computes dimensions, clearances, areas, quantities; edits approved files without approval |
| `archtools` (Python, tested) | Validates and **computes**: positions in global coordinates, collisions, clearances, style resolution, finish validation, **asset scaling to catalog dims**, quantities (paint m², etc.), staleness | Aesthetic choices |
| Blender | Turns `cena.json` into objects, materials, lights; renders | **Any default that looks like a decision** |

Amendment 1: **the AI also proposes positions** (layout is a design act), but positions only
become valid after `archtools layout`. Amendment 2: **Blender gets zero design defaults.**
Anything not specified renders as an explicit *neutral placeholder* (uniform grey, labelled
in the render report), so an unspecified sofa looks unspecified rather than blue (fixes G3).

### 5.2 Blockout (inside 2c)

Already exists: `archtools layout` → `archtools cena` (no finishes) → Blender Eevee, low res.
Proposal: make it part of the layout loop — every layout proposal gets a plan + 2–4 blockout
views automatically, so spatial validation is visual *before* approval. Your expectation is
right: blockout belongs to spatial planning, not to the preview phase.

### 5.3 Design preview (P3)

`cena.json` must carry **everything** visible, all derived from approved files:

| Need | Today | Proposed |
|---|---|---|
| Wall/ceiling/floor finishes | colour only | `material` id from material catalog (paint, brick, wood panel, wallpaper, microcement) with PBR params; procedural Blender node presets for brick/wood/fabric first (no downloads) |
| Furniture | boxes + 11 parametric models | assets via catalog (§5.5), finishes per material slot |
| Decor (rugs, art, curtains, cushions, books, plants, objects) | prose only | **items in `layout.yaml`** with `categoria: decor`. Rugs/art/curtains have real positions and sizes; small objects use `sobre: <item>` (host item + slot), and `archtools` computes their placement. Collision rules relaxed for decor (rug under chair is fine) |
| Lighting | point/spot from fixtures, K from style | keep; add sun direction per window orientation (needs north — `desconhecido` today) |
| Cameras | auto per room | auto for blockout; named cameras saved per room for P3/P5 so comparisons use identical views |

### 5.4 Detailing (P4) and final rendering (P5)

- **Asset fidelity levels (LOD)** in the asset metadata: `0` box, `1` parametric recognisable
  (today's `modelos.py`), `2` detailed mesh (`.blend`/`.glb`, modelled or a CC0 download with
  your permission), `3` hero (textured, bevelled, cushions). Detailing = raising the LOD of
  chosen items; the bounding box is always the catalog dims, so **the layout stays valid by
  construction** (Blender scales/fits the mesh into the bbox `archtools` gives it).
- Textures: CC0 PBR sets (ambientCG/Poly Haven class) referenced from the material catalog.
- Final render: Cycles on CPU (Iris Xe → expect minutes per 1080p frame with denoising; few
  views), named cameras, day/night, render report listing placeholders and suppositions.

### 5.5 Reusable asset library

Separate **product** (a real thing you could buy) from **asset** (a 3D representation):

```yaml
# catalogo/produtos/sofa-chaise-194.yaml
id: sofa-chaise-194
nome: "Sofá com chaise 194"
categoria: sofa
link: "<url do anúncio>"
dimensoes:
  largura:      {valor: 1940, status: estimado, fonte: "anúncio"}
  profundidade: {valor: 1640, status: estimado, fonte: "anúncio (com chaise)"}
  altura:       {valor: 900,  status: estimado, fonte: "anúncio"}
cor_real: null            # null = a definir (pode ser escolhida no conceito); hex = não recolorir
ativo: sofa_chaise         # representação 3D
parametros: {altura_assento: 460, prof_encosto: 200, braco_largura: 150, braco_altura: 650}
tags: [linho]
```

```yaml
# ativos/sofa_chaise/ativo.yaml
id: sofa_chaise
categoria: sofa
lod: 1
gerador: "archtools.modelos.sofa_chaise"   # LOD 1: parametric python; LOD 2+: arquivo: modelo.glb
slots: [estrutura, assento, almofadas, pes]  # material slots filled by conceito.yaml
variacoes: [braco_esquerdo, braco_direito, sem_bracos]
estilos: [contemporaneo, japandi, mid_century]   # indicative only
```

- Many products can share one parametric asset; generic items (a "rug 2×3") need no product.
- Layout items reference `produto:` (or `ativo:` + dims for generic items); **dims come from
  the catalog** — removes the duplication in G6. A layout may override dims only with a status
  and source (e.g. custom carpentry).
- Grow incrementally: catalog entries for the dorm2 items first; LOD 2 only for items you care
  about. No bulk asset hunting.

### 5.6 Generative images: where they fit

| Use | Value | Rule |
|---|---|---|
| Moodboards in 2b (before any geometry) | High: fast direction-finding | Stored in `referencias/geradas/` with prompt + service; treated like any reference (level `observado`) |
| Material/texture exploration | Medium | Can inspire a material catalog entry; the entry itself is defined by you/products |
| Alternative concepts "what if" | Medium | Never compared against renders as if equivalent |
| Presentation polish of a Blender render (img2img guided by depth/edges) | High in P5 | Output labelled "ilustrativa"; the render is the authoritative image |
| Dimensions, layout, fit, product proportions, quantities | **None** | Never input to geometry, layout or catalog |
| Approval artefact | **None** | Approvals are of `conceito.yaml` + `layout.yaml` + renders |

Cloud service needed (no local GPU); postpone until P5 or until moodboards are clearly useful.

**P5 polish as implemented (2026-11-23):** FLUX.2 [max] edit (fal) with the Cycles render, the exact
Blender depth map and a mask-derived region list; one master view first, other day views reference
it, night views reference the day image of the same camera. Products reach the AI only through their
detailed 3D models (P4), never product photos. Seeds 21/7, final pick is visual. See `ia_flux2.py`
and the `render-final` skill.

### 5.7 End-to-end flow

```
briefing.md ─┐
references ──┼─► AI proposes ─► propostas/<x>/{conceito,layout}.yaml
personas ────┘                         │
                          archtools layout / conceito (validate, compute)
                                       │ 0 errors
                         archtools cena ─► cena.json (+ manifest of inputs)
                                       │
                         Blender (no decisions) ─► renders + .blend (+ manifest)
                                       │
                         critico ─► notes ─► user approves ─► decision (+ hashes) ─► promote
```

---

## 6. Data contracts and artifacts

### 6.1 Concept vs layout: separate, one-directional reference

**Yes, separate.** They change at different rates, are validated by different tools, and are
compared differently (you compare styles on the same layout, and layouts in neutral blockout).

| File | Contains | References | Does not contain |
|---|---|---|---|
| `layout.yaml` | Items (id, category, `produto`/`ativo`, existing/mandatory flag), positions, orientation, elevation, decor placement | catalog, geometry (room ids) | colours, materials, style |
| `conceito.yaml` | Style selection, palette roles, surface finishes, item finishes by layout id/slot, lighting strategy and lights by fixture id, approved references | style personas, material catalog, **layout item ids** | positions, dimensions |
| `conceito.md` | Rationale in the persona's voice, decor intent, open questions (today's LEIA-ME) | — | numbers not coming from tools |

Direction: `conceito → layout → catalog → geometry`. Validation of dangling ids already exists
for finishes. Swapping a sofa (layout change) flags the concept as stale only if the item id
or its slots changed.

Naming: I suggest `conceito.yaml` and `layout.yaml` (Portuguese, like the rest). "Approved" is
not part of the filename: **location** says it — `ambientes/<id>/` is approved,
`propostas/<x>/` is not. That is the existing convention.

Concept example (merges today's `estilo.yaml` entry + `acabamentos.yaml`):

```yaml
# projetos/apartamento/ambientes/dorm2/conceito.yaml
ambiente: dorm2
estilo: {principal: japandi, acentos: []}
referencias:
  - {id: sala-madeira-clara-03, papel: ancora}
  - {id: sala-tijolo-01, papel: evitar}
superficies:
  paredes: {padrao: {material: pintura_fosca, cor: branco_arroz}, "1": {material: pintura_fosca, cor: verde_garrafa}}
  teto: {material: pintura_fosca, cor: branco_arroz}
  piso: null                       # existente, desconhecido
itens:                             # ids do layout.yaml
  sofa: {slots: {estrutura: {material: linho, cor: pedra}}}
  tapete-1: {material: la, cor: pedra}
luz:
  camadas: {geral: 2700, tarefa: 3000}   # validated against the style
  luzes:
    lum-papel: {luminaria: pendente_papel, camada: geral, intensidade_w: 50}
```

### 6.2 Room folder

```
projetos/<p>/
  geometria.yaml  criterios.yaml  requisitos.md  pendencias.md   (as today)
  estilo.yaml                     house default only (padrao)
  ambientes/<id>/
    briefing.md
    conceito.yaml  conceito.md    APPROVED
    layout.yaml                   APPROVED (this room's items)
    cameras.yaml                  named views (P3+)
    saidas/                       GENERATED (+ manifest.json)
  propostas/<id>-<nome>/          same file names; LEIA-ME with status
  decisoes/NNNN-*.md              + YAML front matter (§6.3)
  referencias/                    user images + sidecars
  entrega/                        P6 outputs
```

`archtools` merges per-room layouts for whole-apartment plans and scenes. Migration is small:
only dorm2 has approved content.

### 6.3 Approvals and versions

- **Git is the version store.** Each approval = decision file + commit. Previous versions are
  recovered from git, not kept as copies (no `v1/`, `v2/` folders). Rejected proposals stay
  in `propostas/` marked `arquivada`, or are deleted at your request — git still has them.
- **Decision front matter** makes approvals machine-readable without a new state file:

```yaml
---
numero: "0011"
estado: aceita            # aceita | substituida_por: "0014" | revogada
aprova:
  - {arquivo: ambientes/dorm2/conceito.yaml, sha256: "3fa1…"}
base:                      # what it was approved against
  - {arquivo: ambientes/dorm2/layout.yaml, sha256: "9c0d…"}
---
# 0011 — Conceito do escritório: japandi
…(body as today)…
```

- **Output manifests**: every generated folder gets `manifest.json` listing input files + hashes
  + tool version + command. Cheap, and it is what makes staleness computable.

### 6.4 State is computed: `archtools status`

```
$ archtools status projetos/apartamento
dorm2     P3 preview      conceito ✔ 0011   layout ✔ 0010
          stale: saidas/3d/* (layout.yaml changed after render)
          drift: none     pending: 3 (forro, tomadas, cor real do sofá)
sala      P2a briefing    —
...
```

- Phase = derived from which artifacts exist, are approved, and are fresh.
- **Drift** = an approved file whose hash differs from its approving decision (edited without a
  decision) — this *is* the consistency audit.
- Pending = `pendencias.md` + open questions in proposals.
- No `estado.yaml`, no database: nothing to keep in sync by hand.

### 6.5 Format rules

| Format | Use |
|---|---|
| YAML | Anything a tool reads or validates (geometry, layout, concept, catalog, assets, sidecars, criteria) |
| Markdown | Reasoning for humans and the agent (briefing, persona, concept rationale, decisions, requirements) — with small YAML front matter only where a tool needs a field |
| JSON | Machine-generated intermediates only (`cena.json`, manifests) |

No JSON Schema files; pydantic models in `archtools` are the schema (as today).

---

## 7. Implementation roadmap

Each step ends with something usable on dorm2, which is the acceptance test throughout.

| Step | Content | Reuses | Size |
|---|---|---|---|
| **0. Foundation** | First commit; delete stale renders; `.gitignore` for `.blend1`, caches | — | tiny |
| **1. State & honesty** | Output manifests; decision front matter; `archtools status`; remove Blender design defaults → neutral placeholder + report | `cena.py`, CLI | small |
| **2. Room structure** | `ambientes/<id>/`; migrate dorm2 (split layout, merge `estilo`+`acabamentos` → `conceito.yaml`); product catalog for the ~12 dorm2 items (dims out of `layout.yaml`); `briefing` skill and dorm2 briefing retro-filled | `layout.py`, `acabamentos.py`, `estilo.py` | medium |
| **3. Complete preview** | Material catalog + procedural Blender presets (paint, brick, wood, fabric, metal, glass); decor items (rug, art, curtain, cushions, books) as parametric assets with `sobre:` placement; named cameras. **Goal: render one dorm2 proposal as a complete design** | `modelos.py`, Blender script | medium |
| **4. References** | Sidecar schema; palette script (Pillow, deterministic); `referencia` skill + `analista-referencias` agent; migrate `index.yaml`; calibrate one persona out of `rascunho` with your images | tag vocabulary | medium |
| **5. Collaboration** | `proponente-estilo` + `critico` agents; style shortlist by tag overlap; new personas (Scandinavian, Minimalist, Modern rustic…) | `arquiteto` skill | small–medium |
| **6. Next rooms** | Sala, dorm1… through the same flow (this is where the design proves itself) | everything | ongoing |
| Later | LOD 2 assets for hero items; CC0 textures; final-render cameras & Cycles settings; AI polish of renders via cloud; hand-off generator (shopping list, paint m², electrical points) | | |

**Deliberately postponed / avoided**

- Databases, MCP servers, orchestration frameworks, web UI — files + git + CLI cover all needs.
- One agent per style or discipline.
- Generative 3D models and bulk asset downloading.
- Lighting simulation in lux (say "not computed" until a real need appears).
- Automatic promotion of anything — approvals remain human.
- A generic schema system / plugin architecture for styles: a folder per style is enough.

---

## 8. Decisions (settled with the user, 2026-11-18)

1. **Phases:** Preview and Refinement are merged into one phase (P3), and the **Hand-off**
   phase (P6) is added. Final list: P1 Survey · P2 Room design (2a briefing, 2b concept,
   2c layout) · P3 Preview & refinement · P4 Detailing · P5 Final rendering · P6 Hand-off.
2. **One folder per room:** `projetos/<p>/ambientes/<id>/`, each with its own `layout.yaml`.
   The apartment-wide `layout.yaml` is migrated and removed.
3. **Two approved files per room:** `conceito.yaml` (how it looks) + `layout.yaml` (what
   goes where), as in §6.1. Item finishes live in `conceito.yaml`, not in the layout.
   Product dimensions come from the catalog (`catalogo/produtos/`), referenced by the layout.
4. **Git is the version store.** Done: public repo m4c0y/architecture-helper; personal
   project data (`projetos/apartamento/`) stays out of git.
5. **Portuguese names** for artifacts and fields (`conceito.yaml`, `ambientes/`, `catalogo/`).
6. **Styles are data, not one skill per style.** Added `minimalista` and `rustico_moderno`.
   Reference images come from **Unsplash** (connector; license allows redistribution);
   Magnific was tested and dropped (free plan blocks downloads).

### Progress against the roadmap (§7)

| Step | Status |
|---|---|
| 0. Foundation | done (commit c8feffb) |
| 4. References | partly done (commit fd2a92c): sidecar format, `referencias`/`paleta`, skill, 19 photos. Missing: furniture/lighting/material types, batch analysis agent |
| 5. Collaboration | partly done: 2 new personas. Missing: style-proposer and critic agents |
| 1. State & honesty | done (commit 31e6394) |
| 2. Room structure | done (commit 31e6394) |
| 3. Complete preview | done for dorm2 (2026-11-19): procedural texture presets (paint, wood, floor planks, fabric, leather, metal, paper, foliage) chosen by `archtools`; per-piece real colours; decor items (`categoria: decor`, `sobre:` + `nivel:` with computed elevation; rugs don't collide/block); named cameras (`ambientes/<id>/cameras.yaml`). Not done: a separate material catalogue file (presets live in `materiais.TEXTURAS`), brick/microcement presets, cushions on sofas without seat geometry |
