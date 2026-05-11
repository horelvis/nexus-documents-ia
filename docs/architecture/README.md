# Architecture — NouxCubeIA

This folder is the source of truth for how NouxCubeIA is built. It centres
on the **Knowledge Graph (KG)** because the KG is the layer that turns raw
documents into structured, verifiable knowledge — and it is what
distinguishes NouxCube from a generic vector-RAG product.

The reading order below is opinionated. Newcomers should start with this
file, then drill into the reference docs as they need detail.

---

## 1. Document map

| Doc | What it covers | When you read it |
|-----|----------------|------------------|
| `README.md` (this file) | Conceptual primer for the KG and how it plugs into RAG | First. Always. |
| [`MODULAR_ARCHITECTURE.md`](MODULAR_ARCHITECTURE.md) | Service topology, ports, inter-service contracts, persistence stores | When you need to know which microservice owns what |
| [`TRUSTGRAPH.md`](TRUSTGRAPH.md) | KG schema, FalkorDB indexes, the 4 extractors, ontology, reindex script | When you implement against the KG or change extraction |
| [`RAG_PIPELINE.md`](RAG_PIPELINE.md) | Indexing pipeline (Weaviate side), 8-stage `graph_rag`, `smart_search`, re-ranking, caching | When you debug retrieval or tune relevance |
| [`EMMA_AI.md`](EMMA_AI.md) | LangGraph agent topology, ReAct loop, swarm, sub-graphs | When you change the agent or add a tool |
| [`EMMA_REACTIVE.md`](EMMA_REACTIVE.md) | Event bus, triggers, channels, heartbeat | When you need proactive/event-driven behaviour |
| [`USER_MEMORY.md`](USER_MEMORY.md) | Cross-thread persistent user facts (LangGraph Store) | When you touch personalisation or GDPR delete |
| [`PROMPT_MANAGEMENT.md`](PROMPT_MANAGEMENT.md) | Langfuse-as-source-of-truth for prompts, rules, guardrails | When you add or modify any prompt |
| [`AGENTS.md`](AGENTS.md) | Admin-curated specialist agents (`@slug` mention flow) | When you add a vertical agent or change scope filters |
| [`ACL_SYSTEM.md`](ACL_SYSTEM.md) | Authorisation model — single-tenant, `is_superuser` only | When you touch auth or admin gating |

The docs are reference style (dense, exhaustive). This README is the only
explanation-style doc — its job is to make the rest readable.

---

## 2. Why a Knowledge Graph at all?

Vector RAG retrieves **passages**. A KG retrieves **facts**. The two are
complementary, not competing — but vector RAG alone has known failure
modes that the KG is built to address.

### The three failures of pure vector RAG

1. **Multi-hop reasoning collapses.** "Which companies in the same group
   as ACME signed a contract with us last quarter?" requires three joins:
   ACME → group → siblings → contracts. Vector search retrieves the
   chunks that *mention* each piece, but the agent has to reconstruct the
   join from text. Recall and precision both degrade fast.

2. **No structural aggregation.** "Average gross salary across our
   employees in TechCorp." There is no chunk that contains the answer;
   the answer is a `SUM/COUNT` over a property of a set of entities.
   Vector RAG can only return the raw payslips.

3. **Citations are paraphrased, not verifiable.** When the LLM
   synthesises "Juan García is employed by TechCorp", a vector-only
   pipeline can show *which chunks were retrieved*, but the *fact itself*
   is just LLM output. The user has to re-read the chunk to verify. A KG
   stores the fact as a triple with a chunk URI attached — verification
   becomes a graph lookup, not a re-read.

### What the KG adds

The KG turns each document into a set of **triples** (subject → predicate
→ object) with provenance, confidence, and cross-source consensus. That
unlocks:

- **Joins** become graph traversals, not LLM context-stuffing.
- **Aggregations** become Cypher `count` / `sum` queries.
- **Citations** are first-class: every triple has a `chunk_uri`.
- **Contradictions** are detected automatically and surfaced as their
  own queryable nodes.
- **Trust** is composable: per-fact `confidence`, per-source `authority`,
  per-claim `consensus` (how many independent sources said the same
  thing).

The cost is non-zero: you pay for 4 LLM extractors per chunk, plus
storage in FalkorDB, plus an entity-resolution pass per document. We
believe the cost is justified for a document-management product where
**verifiability** and **multi-hop questions** are first-class
requirements. If you build a generic Q&A bot over wiki pages, vector RAG
alone would probably be enough.

---

## 3. How NouxCube's KG works (in 3 minutes)

NouxCube uses the **TrustGraph** model — an RDF-style triple store
implemented on top of FalkorDB. The model has only three labels and one
edge type, but it carries rich metadata.

### 3.1. The triple model

```
(:Node)─[:Rel {uri: predicate}]─→(:Node)     ← entity-to-entity
(:Node)─[:Rel {uri: predicate}]─→(:Literal)  ← entity-to-value
```

| Label | What it represents | Example |
|-------|-------------------|---------|
| `:Node` | Anything addressable: people, companies, documents, folders, chunks, contradictions, extractions | `nouxcube://entity/default/juan-garcia` |
| `:Literal` | Scalar values: names, dates, amounts, descriptions | `:Literal {value: "30000 EUR"}` |
| `:Rel` | A typed edge whose **type** is encoded as a `uri` property | `[:Rel {uri: "nouxcube://predicate/legal/empleado-de"}]` |

This uniformity is intentional. Every relationship in the graph — "Juan
is employed by TechCorp", "this triple was extracted from chunk X",
"this fact contradicts that fact" — has the same shape. There are no
special-cased edge types in Cypher, only different `uri` values. That
makes provenance, contradictions, and trust scoring easy to bolt on
without changing the schema.

### 3.2. The mini-ontology

The `uri` on each `:Rel` comes from a curated ontology of **72
predicates** in 6 namespaces:

| Namespace | Count | Examples |
|-----------|-------|----------|
| `core/` | 15 | `label`, `type`, `definition`, `has-topic`, `mentioned-in` |
| `legal/` | 25 | `empleado-de`, `firmante-de`, `vigente-desde`, `salario-bruto` |
| `medical/` | 12 | `diagnosticado-con`, `prescrito-por`, `alergia-a` |
| `documental/` | 10 | `autor-de`, `revisado-por`, `version-de` |
| `prov/` | 6 | `derived-from`, `model`, `timestamp`, `chunk-text` |
| `trust/` | 4 | `authority-weight`, `consensus-score` |

Predicates are seeded into FalkorDB and embedded into a Weaviate
collection (`OntologyTerms`) so the relationships extractor can do
**semantic predicate resolution** — when the LLM emits `works_at`, the
ontology returns the canonical `legal/empleado-de` predicate that is
already in use elsewhere in the graph.

This is what keeps the ontology from drifting. Without it, every doc
would invent its own variant of the same predicate and the graph would
become unqueryable.

### 3.3. The 4-extractor pipeline

Each chunk is processed by **4 LLM extractors in parallel** via
`asyncio.gather` in `ExtractionCoordinator`:

| Extractor | What it asks the LLM | Output triples |
|-----------|----------------------|----------------|
| `definitions` | "What entities are mentioned and how would you describe them?" | `(entity, core/label, name)`, `(entity, core/definition, text)` |
| `relationships` | "What facts are stated about these entities?" | `(subject, predicate_uri, object)` — semantically resolved |
| `objects` | "Named-entity recognition with type" | `(entity, core/label, name)`, `(entity, core/type, type)` |
| `topics` | "What is this chunk about thematically?" | `(document, core/has-topic, topic_entity)` |

Why four instead of one mega-prompt? Three reasons:

1. **Specialisation reduces hallucination.** A prompt scoped to one
   task is easier for a 9B model to satisfy. Putting "give me NER + SPO
   + topic + definitions in one JSON" is fragile.
2. **Independent failures are recoverable.** If the relationships
   extractor returns malformed JSON, definitions and topics still land.
3. **Consensus signal.** When two extractors independently emit the
   same triple (e.g. `objects` says `(juan, core/label, "Juan García")`
   and `definitions` says the same), the `consensus-score` on the edge
   ticks up. Cross-extractor agreement is one of the five trust signals
   used at retrieval time.

After parallel extraction, the coordinator:

- Deduplicates triples by `(normalized_subject, predicate, normalized_object)`.
- Filters subjects/objects against an entity blacklist
  (`config/entity_blacklist.yaml`) so generic concepts like "empresa" or
  "documento" don't pollute the graph.
- Upgrades `:Literal` objects to `:Node` when they match a known
  entity (so `(contrato_X, mentions, "TechCorp")` becomes a real edge
  from the contract to the TechCorp node).
- Materialises a `:Chunk` node per chunk and links every produced edge
  to it via `core/of-document` and a `source_chunk` property — this is
  the provenance backbone.
- Writes everything to FalkorDB in 1-2 batched Cypher calls.
- Records PROV-O provenance (model, timestamp, chunk text).
- Runs **contradiction detection** (same subject + same predicate, two
  different literal values from independent sources → emit a
  `:Node {uri: contradiction/...}`).
- Runs **consensus scoring** (how many independent sources back this
  predicate?) and writes the count back onto the edge.
- Runs **entity resolution** (heuristic Levenshtein + LLM clustering) to
  merge `Juan García` and `J. García` into one node. Scope is
  per-document but operates on the whole collection, so cross-document
  duplicates collapse as soon as a clearer label variant arrives.

The full pipeline takes ~300 ms per chunk on a 9B model with 4 GPU
extractors running in parallel. A 10-chunk document lands in ~3 seconds.

### 3.4. Provenance is non-negotiable

Every triple in the graph can answer the question **"how do you know
this?"**. The answer is a chain of edges:

```
(triple) ─source_chunk→ (:Chunk) ─core/of-document→ (:Document) ─prov/derived-from→ (:Extraction)
                                                                                       │
                                                                       prov/model──────┤
                                                                       prov/timestamp──┤
                                                                       prov/chunk-text─┘
```

This is what lets the agent cite a specific chunk in a specific document
when synthesising an answer, and what lets a user open the source PDF at
the right page.

---

## 4. KG vs a "normal" property graph

Most teams that consider a KG default to a property-graph schema in
Neo4j (or FalkorDB) with native types like `(:Person)-[:WORKS_AT]->(:Company)`.
That works for hand-curated domains but breaks down quickly on
LLM-extracted knowledge from heterogeneous documents.

NouxCube took a different design path. Here is the comparison:

| Aspect | "Normal" property graph | NouxCube TrustGraph |
|--------|-------------------------|---------------------|
| **Schema** | Schema-on-write, fixed labels (`:Person`, `:Company`, `:Contract`) | Schema-light triples; type is an edge `(entity)-[core/type]->("person")` |
| **Adding a new entity type** | Migration: new label, new indexes, possibly downtime | Just emit a new `core/type` value; no schema change |
| **Predicate vocabulary** | Hardcoded relationship types per integration | Curated ontology resolved semantically at extraction time |
| **Provenance** | Convention: a `source` property on edges, manually maintained | Mandatory: every edge has a `source_chunk` and the chunk is a `:Node`; PROV-O sub-graph per extraction |
| **Confidence per fact** | Optional, app-level concern | First-class `confidence` property; combined with authority + consensus + recency at query time |
| **Contradictions** | Bugs to deduplicate | Detected automatically and stored as queryable `:Node`s with edges to both conflicting values |
| **Multi-source consensus** | Not modelled | `consensus_count` property on each edge, computed across extractors and documents |
| **Source authority** | Not modelled | `authority-weight` triples per document type (legislation > internal memo) |
| **Query language affordance** | Cypher with typed traversals (`-[:WORKS_AT]->`) | Cypher with predicate-URI filters (`-[r:Rel {uri: "..."}]->`) — uniform shape, easier to compose generically |
| **Entity resolution** | Manual scripts or none | Built-in: Levenshtein + LLM clustering per document, scoped to type (person/org/place) |
| **Ingest source** | Usually one curated pipeline | 4 LLM extractors in parallel + cross-source merging |
| **Failure mode** | Wrong fact lands silently | Wrong fact gets a contradiction node and a low confidence; surfaces in retrieval |
| **Best fit** | Curated, stable domains (CRM, supply chain) | Document-derived knowledge that grows from heterogeneous, noisy sources |

### Why not just use a property graph?

We tried. Two failure modes pushed us to the triple model:

1. **The schema couldn't keep up with the documents.** Every new file
   type wanted a new label. A medical PDF wanted `(:Diagnosis)`, a
   contract wanted `(:Clause)`, a payslip wanted `(:Concepto)`.
   Migrations piled up. With triples + an ontology, "Diagnosis" is just
   another `core/type` value — no schema change, no migration.

2. **Provenance was always second-class.** With a property graph, the
   convention is to put `source_doc_id` as an edge property. That works
   until you want to ask "which extractions produced edges that
   contradict each other across documents?" — then you need provenance
   to be queryable, not opaque metadata. In TrustGraph, provenance is
   itself a sub-graph; the question becomes a Cypher pattern.

A normal graph is excellent when the domain is stable and curated. For a
document IA where every customer brings a new vertical, the triple +
ontology model has been measurably easier to evolve.

---

## 5. What the KG brings to RAG — three concrete scenarios

This section answers the third part of "why a KG": **what does it give
the RAG agent that vector search alone cannot?**

For each scenario we show:
- The user query.
- What pure vector RAG would do.
- What the KG path adds.
- The actual code path in the repo (so you can trace it).

### Scenario A — "Who signed contract `2025-001`?"

A contract PDF. The signature page mentions Juan García in the
signature block at the very end. The body of the contract talks about
*the obligations of the contracting party* without naming Juan.

**Pure vector RAG:** the query "who signed contract 2025-001" embeds
poorly against the signature page (which is mostly stamps and short
strings). It retrieves the chunks that *talk about the contract* —
i.e. the body — and the LLM has to guess. Often the answer is "the
contract was signed by the contracting party", which is technically
correct and useless.

**KG path:** at extraction time, the `relationships` extractor on the
signature chunk produced the triple

```
(contrato-2025-001) -[legal/firmante-de]-> (juan-garcia)
```

with `source_chunk = chunk-12-signatures`. At query time, the
`graph_rag` tool seeds on the document URI, traverses out via
`legal/firmante-de`, and returns the answer with provenance. The user
sees:

> Contract 2025-001 was signed by Juan García
> ([source: contrato-2025-001 — page 8](#)).

**Code path:**
- Indexing: `extractors/relationships.py` → `triple_store.batch_store_triples`
- Query: `tools/graph_rag.py` Stage 2 BFS → Stage 7 `trace_sources`
- Synthesis: `nodes/synthesize_react.py` (cited sources are filtered by
  the `_filter_cited_sources` helper added in commit `491d2a80`)

### Scenario B — "What is the average gross salary of TechCorp employees?"

A folder of payslips and contracts. Forty employees, one PDF each.

**Pure vector RAG:** the query embeds against all payslips. The agent
gets back the top-K most relevant payslip chunks. With K=10 and 40
employees, you have already lost the answer — even if the LLM could
mentally average the numbers, the input is incomplete.

**KG path:** every payslip extraction produced

```
(employee_X) -[legal/empleado-de]-> (techcorp)
(employee_X) -[legal/salario-bruto-anual]-> (:Literal {value: "29 000 EUR"})
```

At query time the `structural_query` tool (or the `generate_knowledge_report`
tool for richer reports) issues a Cypher that:

```cypher
MATCH (e:Node)-[:Rel {uri: "...legal/empleado-de"}]->(c:Node {uri: "...techcorp"})
MATCH (e)-[:Rel {uri: "...legal/salario-bruto-anual"}]->(s:Literal)
RETURN avg(toFloat(s.value)) AS avg_salary
```

The agent gets a single number, plus per-employee citations, and writes
a verifiable answer.

**Code path:**
- Indexing: `relationships` + `objects` extractors
- Query: `tools/structural_query.py` (or the GraphAssembler templates in
  `services/graph_assembler.py` for full reports)
- KPIs: `services/kpi_engine.py`

### Scenario C — "Are there contradictions in patient X's medical reports?"

Multiple medical PDFs from different visits. One says "patient is
diabetic", another says "non-diabetic". Vector RAG can return both
chunks but has no concept of *contradiction*; it relies on the LLM to
notice and reconcile.

**KG path:** the `ContradictionDetector` ran at extraction time. It
found that

```
(patient-x) -[medical/diagnosticado-con]-> "diabetes"           (from report A)
(patient-x) -[medical/diagnosticado-con]-> "no diabetes"        (from report B)
```

share subject + predicate but disagree on object. It materialised a
contradiction node:

```
(:Node {uri: "nouxcube://contradiction/abc-123"})
    -[contradicts]-> (triple-A)
    -[contradicts]-> (triple-B)
    -[about]-> (patient-x)
```

The agent retrieves the contradiction node directly, surfaces it, and
the answer becomes:

> There is a discrepancy: report A (2024-11-12) records "diabetes",
> report B (2025-02-04) records "no diabetes". Both are cited; please
> review.

**Code path:**
- Detection: `services/contradiction.py` → `detect_and_mark`
- Confidence penalty: `apply_confidence_penalty` (also reduces the
  weight of contradicted edges in retrieval scoring)
- Frontend surface: `SourceEvidence` panel, contradiction badge

### What ties the three scenarios together

In all three, the KG turned a *retrieval* problem into a *graph query*.
The vector index is still used — for free-text search, for entity
seeding in `graph_rag` (the `TrustGraphEntities` Weaviate collection
gives the seed URIs), and for hybrid ranking. But the graph carries the
structured weight: who-did-what-to-whom, with what confidence, from
which source.

That is the value proposition. Pure vector RAG is good at "find me
chunks that look like this question". The KG is good at "answer this
question, cite each fact, surface disagreements, and let me audit the
chain". Combined, they do both.

---

## 6. The five trust signals (composite scoring)

When `graph_rag` ranks edges in its 8-stage pipeline, it does **not**
use raw vector similarity. It blends five signals into a composite
score. This is the second-most distinctive feature of the system after
the triple model.

| Signal | What it measures | Default weight | Stored on |
|--------|------------------|----------------|-----------|
| `semantic` | Cosine similarity between the edge label embedding and the query embedding | 0.35 | Computed at query time |
| `confidence` | Base score per `extraction_method` (e.g. `llm_definitions=0.90`, `llm_relationships_freeform=0.60`), penalised on contradiction | 0.20 | `confidence` property on `:Rel` |
| `authority` | Trust of the source document type — legislation > corporate report > internal email | 0.20 | Resolved via `_authority` collection triples |
| `consensus` | How many independent sources back this same triple | 0.15 | `consensus_count` on `:Rel` |
| `recency` | Exponential decay with 90-day half-life | 0.10 | Derived from document timestamp |

A triple that is semantically a perfect match but extracted once with
low confidence and from an internal memo will rank below a triple that
is a slightly worse semantic match but consensus-backed by five
independent legislation documents. This is the difference between
"relevant text" and "trustworthy fact" — and it is what lets the agent
cite confidently.

(`smart_search` uses a different 5-signal composite for *document*
ranking — see `RAG_PIPELINE.md` Part 5. Don't confuse the two scoring
functions; one ranks edges in the KG, the other ranks documents in
hybrid search.)

---

## 7. Where the KG plugs into the RAG pipeline

```
┌─ Indexing ────────────────────────────────────────────────────┐
│                                                               │
│  doc upload ─► intelligence-docs (Tika/Docling) ─► chunks     │
│                                                               │
│  chunks ──┬─► weaviate-service (BGE-M3 embeddings)            │
│           │      └─► Nouxcube_documents (vector + BM25)       │
│           │                                                   │
│           └─► knowledge-tree-service (TrustGraph)             │
│                  └─► 4 LLM extractors → FalkorDB triples      │
│                       └─► entity-resolution per doc           │
│                       └─► auto-embed touched entities         │
│                            into TrustGraphEntities (Weaviate) │
└───────────────────────────────────────────────────────────────┘

┌─ Retrieval ───────────────────────────────────────────────────┐
│                                                               │
│  user query ─► Emma ReAct agent ─► tool selection             │
│                                                               │
│       ┌─ smart_search ─► hybrid Weaviate + graph expansion    │
│       │                  (5-signal doc re-rank)               │
│       │                                                       │
│       ├─ graph_rag    ─► 8-stage TrustGraph pipeline          │
│       │                  (5-signal edge composite scoring)    │
│       │                                                       │
│       ├─ structural_query ─► Cypher count/list/aggregate      │
│       │                                                       │
│       └─ generate_knowledge_report ─► GraphAssembler templates│
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

Two stores, two complementary roles:

- **Weaviate** answers "find me chunks that look like this question".
- **FalkorDB** answers "what facts do we know, with what trust, from
  which source?".

The ReAct agent picks the right tool per turn. The agent is told via
the `emma_react_system` prompt to prefer `graph_rag` for entity-centric
or relationship questions, `smart_search` for keyword / topical
questions, and `structural_query` for counts and aggregates.

For full retrieval detail see [`RAG_PIPELINE.md`](RAG_PIPELINE.md).

---

## 8. Design decisions worth knowing about

These decisions surprise newcomers. Each has a reason; if you are about
to argue against one, read this section first.

| Decision | Rationale |
|----------|-----------|
| Triple model on FalkorDB instead of native property graph | Schema stability across heterogeneous documents; provenance as a sub-graph; ontology evolves without migrations |
| 4 separate LLM extractors instead of one big prompt | Specialisation reduces hallucination; cross-extractor consensus is a free trust signal |
| Predicate URIs are first-class instead of edge type names | All edges share the `:Rel` shape, so generic Cypher patterns work for any predicate |
| Predicates live in a curated ontology, semantically resolved | Without it, the LLM invents a new variant per document and the graph becomes unqueryable |
| Contradictions become `:Node`s, not deduplication targets | Disagreement is a fact about the corpus that the user must see |
| Entity resolution runs per-document but on the whole collection | Cross-document duplicates collapse as soon as a clearer label arrives |
| Chunks are first-class `:Chunk` nodes, not just edge metadata | Provenance becomes graph-traversable; the agent can show "this fact came from page 8" |
| Auto-embed only the subset of entities touched by the latest extraction | Cost is O(touched), not O(scope); a weekly cron does the full re-embed for drift |
| Confidence is not boolean — five signals are blended | "Relevant" and "trustworthy" are different concepts; the agent needs both |
| Langfuse is the only prompt source (no YAML fallback) | Drift between code and prompts was the #1 source of "it works on my machine" bugs |

---

## 9. Glossary

These terms are used everywhere; learn them before reading the reference docs.

| Term | Meaning |
|------|---------|
| **Triple** | A `(subject, predicate, object)` statement. The atomic unit of the KG. |
| **Predicate URI** | The canonical name of a relation type, e.g. `nouxcube://predicate/legal/empleado-de`. Lives in the ontology. |
| **Ontology** | The curated set of 72 predicates, seeded into FalkorDB and embedded into Weaviate `OntologyTerms` for semantic resolution. |
| **PROV-O** | W3C provenance vocabulary. We use it for `derived-from`, `model`, `timestamp`, etc. |
| **`:Chunk` node** | A first-class node representing a chunk of a document. Every triple has a chunk URI as `source_chunk` and edges back to `:Chunk`. |
| **Entity resolution** | The process of merging duplicate `:Node`s that represent the same real-world entity. Two phases: heuristic (Levenshtein + prefix) and LLM clustering. |
| **Contradiction node** | A `:Node {uri: "nouxcube://contradiction/..."}` materialised when the same subject + predicate has conflicting literal objects from different sources. |
| **Consensus count** | A property on `:Rel` counting how many independent sources back the same triple. One of the trust signals. |
| **Authority weight** | A score per document type stored as triples in the `_authority` collection. Resolved at query time, not hardcoded. |
| **`graph_rag`** | The 8-stage retrieval tool that queries the KG. See `RAG_PIPELINE.md` Part 4. |
| **`smart_search`** | The hybrid retrieval tool that blends Weaviate hybrid search with optional graph expansion. |
| **`structural_query`** | The Cypher-style tool used for counts, lists, and aggregates over the KG. |
| **TrustGraph** | The open-source RDF-style triple model NouxCube adopted (Apache 2.0). See [trustgraph.ai](https://trustgraph.ai). |

---

## 10. Where to go from here

After reading this primer:

- **To understand the schema and extraction pipeline**, read
  [`TRUSTGRAPH.md`](TRUSTGRAPH.md). That doc has the FalkorDB indexes,
  the 4 extractors, the PROV-O detail, and the reindex script.
- **To understand retrieval end-to-end**, read
  [`RAG_PIPELINE.md`](RAG_PIPELINE.md). It covers indexing on the
  Weaviate side, the 8-stage `graph_rag`, the `smart_search` re-ranking
  formula, and all caches.
- **To understand which microservice does what**, read
  [`MODULAR_ARCHITECTURE.md`](MODULAR_ARCHITECTURE.md). Service ports,
  inter-service contracts, and persistence layout.
- **To touch the agent**, read [`EMMA_AI.md`](EMMA_AI.md) and
  [`AGENTS.md`](AGENTS.md).
- **To touch prompts**, read [`PROMPT_MANAGEMENT.md`](PROMPT_MANAGEMENT.md).
  Langfuse is the only source of truth.

---

## 11. Known gaps and open questions

This section is honest about where the KG falls short today. Update it
as state changes.

- **Untyped entities escape entity resolution.** The resolver filters by
  `core/type → "person|organization|place"`. Entities mentioned only by
  the `relationships`/`definitions`/`topics` extractors (which do not
  emit `core/type`) become invisible to the resolver. Tracked under
  *entity extraction bugs pending* in project memory.
- **Common single-token names can false-merge.** A subject extracted as
  just `Juan` from two different real people produces the same URI
  (`entity/{coll}/juan`) and merges silently. Blacklist does not yet
  cover bare first names. Same tracker.
- **Cross-type disambiguation is not designed.** `Movistar Plus+` legitimately
  appears as both an organisation and a product. There is no policy yet
  for whether to keep two nodes or merge them.
- **Memory bank tools (`store_memory`, `recall_memories`) are stubs.**
  Returns `success=False`. Listed under priority stack in MEMORY.md as
  Issue 15c.
- **`graph_rag` Stage 7 depends on `TrustGraphEntities` being populated.**
  An empty entity collection short-circuits the pipeline with "No
  entities found". Auto-embed on extract was added in commit `16fca3a7`
  to prevent drift; weekly cron is the safety net (commit `97a2a530`).

The existence of this section is on purpose: a primer that pretends the
system has no rough edges loses credibility fast. Newcomers should know
where the gaps are before they hit them.
