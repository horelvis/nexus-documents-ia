# TrustGraph Phase 3: Knowledge Expert — Design Spec

**Date**: 2026-04-01
**Branch**: `feat/trustgraph-phase3`
**Depends on**: Phase 1 (Automated Ingest) COMPLETE, Phase 2 (Semantic Similarity Retrieval) COMPLETE
**Goal**: Transform the knowledge graph from a retrieval aid into a **verified knowledge expert** capable of generating documents, reports, and KPIs with full provenance and trust scoring.

---

## Approach: Capability Slices (3 Sub-Phases)

Each sub-phase delivers a complete, independently testable capability:

| Sub-Phase | Capability | Deliverable |
|-----------|-----------|-------------|
| **3a: Clean Graph** | Graph data is clean, deduplicated, and ontology-validated | graph_rag returns cleaner results without query-side changes |
| **3b: Smart Traversal** | Queries are trust-scored and multi-hop aware | graph_rag reasons over paths with authority/consensus weighting |
| **3c: Knowledge Expert** | System generates documents, reports, and KPIs from graph | New `generate_knowledge_report` tool in ReAct agent |

---

## Phase 3a: Clean Graph

### 3a.1 — Entity Blacklist

**Problem**: Nodes like "mayor de edad", "conyuge", "herederos forzosos" are generic legal concepts extracted as `:Node` entities. They contaminate BFS subgraphs and dilute graph_rag results.

**Design**:

- **Static blacklist** in `knowledge-tree-service/config/entity_blacklist.yaml`:
  ```yaml
  # Generic legal concepts that are not real entities
  legal_concepts:
    - "mayor de edad"
    - "menor de edad"
    - "conyuge"
    - "herederos forzosos"
    - "parte contratante"
    - "representante legal"
  # Overly generic terms
  generic:
    - "empresa"
    - "persona"
    - "documento"
    - "articulo"
  ```

- **Interception point**: `ExtractionCoordinator._deduplicate_triples()` — before storage, check subject and object against blacklist. If match, drop the triple.

- **Heuristic complement**: If a candidate node has <=2 words and contains no uppercase (and is not an acronym), flag as suspicious. Not auto-deleted — logged for review. This feeds the blacklist over time.

- **Retroactive cleanup script**: `scripts/cleanup_blacklisted_entities.py`:
  - Scans existing nodes against blacklist
  - Migrates useful relationships to other nodes or deletes them
  - Removes blacklisted nodes
  - `--dry-run` by default
  - Reports: total nodes, removed, orphaned relationships, low-degree nodes

### 3a.2 — Entity Deduplication

**Problem**: "carlos-ruiz-fernandez" and "d-carlos-ruiz-fernandez" generate different URIs. BFS treats them as separate entities, fragmenting knowledge.

**Design**:

- **Canonical name resolution** in `URIBuilder`:
  - Strip honorific prefixes: `d.`, `dna.`, `don`, `dona`, `sr.`, `sra.`, `dr.`, `dra.`
  - Strip corporate suffixes: `s.l.`, `s.a.`, `s.l.u.`, `s.c.`
  - Normalize whitespace, accents, case (partially exists)

- **Merge strategy in FalkorDB**:
  1. Choose canonical URI (oldest or highest degree)
  2. Re-point all `:Rel` from duplicate to canonical
  3. Merge labels/definitions (keep most complete)
  4. Create `(:Node)-[:Rel {uri: "nouxcube://predicate/core/same-as"}]->(:Node)` for audit trail
  5. Mark duplicate node as `merged=true` (soft delete)

- **Offline dedup script**: `scripts/dedup_entities.py`:
  - Step 1: Group by normalized name (exact match post-normalization)
  - Step 2: For fuzzy candidates (>0.85 Jaro-Winkler), verify they share at least 1 common predicate relationship
  - Output: JSON with merge candidates + confidence
  - `--apply` to execute merges

- **Ingestion-time prevention**: `ExtractionCoordinator` applies canonical name resolution before URI generation. New documents won't create duplicates.

### 3a.3 — Ontology RAG

**Problem**: The 32 seed predicates are limited. The LLM invents predicates in Tier 3 (`extracted/` namespace) with confidence 0.60. There's no semantic way to find the right predicate if the LLM uses synonyms.

**Current mechanism** (3-tier fallback in `RelationshipsExtractor`):
1. Exact match in registry → ontology namespace (confidence 0.90)
2. Fuzzy match via `SequenceMatcher` >0.8 → ontology namespace + `_fuzzy` tag (confidence 0.75)
3. Free-form → `extracted/` namespace + `_freeform` tag (confidence 0.60)

**New mechanism** (semantic matching replaces string matching):

- **Weaviate collection `OntologyTerms`**: Each predicate vectorized with BGE-M3:
  ```python
  {
      "predicate_name": "empleado-de",
      "namespace": "legal",
      "description": "Relacion laboral entre persona y organizacion",
      "examples": ["Juan es empleado de TechCorp", "Maria trabaja en Acme"],
      "embedding": [...]  # BGE-M3 from description + examples
  }
  ```

- **Per-sector predicate catalog** — extend `seed_ontology.py`:
  | Namespace | Current | Target | New predicates (examples) |
  |-----------|---------|--------|--------------------------|
  | `core/` | 12 | ~15 | `same-as`, `authority-weight`, `supersedes` |
  | `legal/` | 14 | ~25 | `parte-de-contrato`, `beneficiario-de`, `garante-de`, `obligacion-de`, `duracion`, `importe` |
  | `medical/` | 0 | ~20 | `diagnosticado-con`, `prescrito-por`, `tratado-en`, `alergia-a` |
  | `documental/` | 0 | ~15 | `autor-de`, `revisado-por`, `aprobado-por`, `version-de` |
  | `trust/` | 0 | 4 | `authority-weight`, `source-reliability`, `temporal-validity`, `consensus-score` |
  | `prov/` | 6 | 6 | (unchanged) |
  | **Total** | **32** | **~85** | |

- **Predicate resolution rewrite** in `RelationshipsExtractor`:
  ```
  LLM output "trabaja en"
    -> Step 1: exact match in registry (fail)
    -> Step 2: vector search in OntologyTerms top-3 (match: "empleado-de", score 0.91)
    -> Step 3: If score > 0.80 -> use ontology predicate, tag "semantic_match"
    -> Step 4: If score < 0.80 -> binary validation LLM call (~50 tokens):
               "Is '{predicate}' a valid semantic relation between two entities? Yes/No"
               If no -> DROP
               If yes -> namespace "extracted/", confidence 0.50
  ```

- **Binary validation**: Short LLM call that eliminates noise like "es", "tiene", "hay" that carry no semantic meaning as predicates.

- **Predicate promotion pipeline**: `scripts/promote_predicates.py`:
  1. Query all `extracted/` predicates with frequency >= N and mean confidence > 0.65
  2. For each candidate: vector search in `OntologyTerms` — if match >0.85, it's a synonym, merge
  3. If no match -> candidate for new predicate. Output for human review.
  4. `--apply` -> seed in `OntologyTerms` + update registry

### 3a.4 — FalkorDB Schema Updates

New indexes to support Phase 3:

```cypher
-- Confidence filtering (graph_rag pre-filter, authority queries)
CREATE INDEX FOR ()-[r:Rel]-() ON (r.confidence);

-- Extraction method auditing
CREATE INDEX FOR ()-[r:Rel]-() ON (r.extraction_method);

-- Merged entity lookups
CREATE INDEX FOR (n:Node) ON (n.merged);

-- Contradiction quick lookups
CREATE INDEX FOR ()-[r:Rel]-() ON (r.has_contradiction);
```

### 3a Validation Criteria

- Blacklisted entities removed from graph (count before/after)
- Zero new duplicates created during ingestion of test document
- Predicate resolution uses vector search (OntologyTerms collection populated)
- `extracted/` namespace predicates reduced by >50% after promotion pipeline
- All new indexes created and used in query plans

---

## Phase 3b: Smart Traversal

### 3b.1 — Authority Weight Triples

**Problem**: All triples have the same implicit weight. A notarized contract should weigh more than an internal email when graph_rag decides which information to present.

**Design**:

- **Authority weight as graph triple** (zero hardcode):
  ```cypher
  (:Node {uri: "nouxcube://entity/_system/contrato-notarial"})
    -[:Rel {uri: "nouxcube://predicate/trust/authority-weight"}]->
    (:Literal {value: "0.95"})

  (:Node {uri: "nouxcube://entity/_system/email-interno"})
    -[:Rel {uri: "nouxcube://predicate/trust/authority-weight"}]->
    (:Literal {value: "0.40"})
  ```

- **New `trust/` namespace** in ontology (4 predicates):
  - `trust/authority-weight` — weight 0.0-1.0 per document type
  - `trust/source-reliability` — source reliability (manual/extracted/imported)
  - `trust/temporal-validity` — is the triple still valid? (linked to `valid_from`/`valid_until`)
  - `trust/consensus-score` — how many independent sources confirm the same triple

- **Authority resolution via Cypher**:
  ```cypher
  MATCH (e:Node)-[:Rel {uri: "nouxcube://predicate/prov/derived-from"}]->(doc:Node)
  WHERE e.uri = $extraction_uri
  MATCH (doc)-[:Rel {uri: "nouxcube://predicate/core/semantic-type"}]->(st:Literal)
  MATCH (aw:Node)-[:Rel {uri: "nouxcube://predicate/trust/authority-weight"}]->(w:Literal)
  WHERE aw.uri CONTAINS st.value
  RETURN w.value AS authority
  ```

- **Seed defaults** via `scripts/seed_authority_weights.py`:

  | semantic_type | authority | Rationale |
  |--------------|-----------|-----------|
  | `escritura-publica` | 0.95 | Notarized document |
  | `contrato` | 0.90 | Signed agreement |
  | `sentencia` | 0.95 | Court ruling |
  | `legislacion` | 1.00 | Standing law |
  | `factura` | 0.85 | Fiscal document |
  | `nomina` | 0.85 | Payroll document |
  | `informe` | 0.70 | Internal analysis |
  | `email` | 0.40 | Informal communication |
  | `nota` | 0.30 | Internal note |

- **Composite edge score** — graph_rag Stage 4 (Semantic Pre-Filter) incorporates authority:
  ```python
  final_score = (
      0.35 * semantic_similarity +
      0.20 * confidence +
      0.20 * authority_weight +
      0.15 * consensus_score +
      0.10 * recency_decay
  )
  ```

### 3b.2 — Multi-Hop Cypher Templates

**Problem**: BFS at 2 hops retrieves a flat subgraph. It doesn't reason over paths. Structured queries like "Which group companies have public sector contracts?" require directed traversal.

**Design**:

- **Template registry** in `knowledge-tree-service/config/cypher_templates.yaml`:
  ```yaml
  templates:
    entity_relations:
      description: "All direct relationships of an entity"
      pattern: "MATCH (s:Node {uri: $entity_uri})-[r:Rel]->(o) RETURN s, r, o"
      hops: 1

    corporate_chain:
      description: "Ownership chain: company -> group -> subsidiaries"
      pattern: |
        MATCH path = (start:Node {uri: $entity_uri})
          -[:Rel*1..4]->(end:Node)
        WHERE ALL(r IN relationships(path) WHERE
          r.uri IN ['nouxcube://predicate/legal/filial-de',
                     'nouxcube://predicate/legal/parte-de',
                     'nouxcube://predicate/core/part-of'])
        RETURN path
      hops: 4

    org_people:
      description: "People related to an organization at N hops"
      pattern: |
        MATCH (org:Node {uri: $entity_uri})
        MATCH path = (p:Node)-[:Rel*1..3]->(org)
        WHERE ANY(r IN relationships(path) WHERE
          r.uri CONTAINS 'empleado' OR r.uri CONTAINS 'firmante'
          OR r.uri CONTAINS 'representante')
        MATCH (p)-[:Rel {uri: 'nouxcube://predicate/core/type'}]->(t:Literal)
        WHERE t.value = 'person'
        RETURN DISTINCT p, path
      hops: 3

    count_by_predicate:
      description: "Count relations of a type for an entity"
      pattern: |
        MATCH (s:Node {uri: $entity_uri})-[r:Rel]->(o)
        WHERE r.uri = $predicate_uri
        RETURN count(o) AS total, collect(o.uri)[..10] AS sample
      hops: 1

    applicable_regulations:
      description: "Laws and regulations applicable to an entity"
      pattern: |
        MATCH (entity:Node {uri: $entity_uri})
        MATCH (entity)-[r1:Rel]->(mid:Node)-[r2:Rel]->(law:Node)
        WHERE r2.uri CONTAINS 'regulado' OR r2.uri CONTAINS 'sujeto-a'
        MATCH (law)-[:Rel {uri: 'nouxcube://predicate/core/type'}]->(t:Literal)
        WHERE t.value = 'legislation'
        RETURN DISTINCT law, r1, r2
      hops: 2
  ```

- **Template executor** — new method `TripleQuery.execute_template()`:
  - Input: template_name + params dict
  - Loads template from registry
  - Injects tenant isolation (`user`, `collection`) automatically
  - Applies authority weight join if template requires it
  - Returns results + metadata (hops used, edges traversed)

- **API endpoint**: `POST /triples/template` on KTS

### 3b.3 — LLM-Guided Traversal

**Problem**: Cypher templates cover known patterns. For ad-hoc queries ("What connection is there between Carlos and the Portuguese company?"), exploratory traversal is needed.

**Design**:

- **New graph_rag stage** — Stage 2.5 "Guided Expansion" between BFS and Semantic Pre-Filter:
  ```
  Stage 1:   Entity Retrieval (unchanged)
  Stage 2:   BFS Subgraph (unchanged, 2 hops base)
  Stage 2.5: Guided Expansion (NEW)
             -> LLM Planner evaluates: "Does the BFS subgraph contain enough info?"
             -> If NO: selects 1-3 most promising frontier nodes
             -> Expands 1-2 additional hops ONLY from those nodes
             -> Max total: 4 hops (2 BFS + 2 guided)
  Stage 3-7: (unchanged)
  ```

- **Planner prompt** (Langfuse: `trustgraph_guided_expansion`):
  ```
  Given the user query and the current subgraph, determine if more traversal is needed.

  Query: {query}
  Current entities: {entity_list}
  Current relationships: {relationship_summary}

  Respond with JSON:
  {"sufficient": true/false, "expand_from": ["uri1", "uri2"], "reason": "..."}
  ```

- **Guardrails**:
  - Max 1 guided expansion call per query (prevents loops)
  - Max 2 additional hops from guided expansion
  - Total edge budget: `graph_rag_max_edges` remains the global limit
  - If Planner fails (parse error, timeout): skip silently, proceed to Stage 3

- **Chain-of-thought path formatting** in Stage 6 (Context Formatting):
  ```markdown
  ### Relationship chain found
  Carlos Ruiz -> representante-de -> Fernando Lopez -> vinculado-a -> TechCorp SL
  (confidence: 0.88, source: contrato-2025-001)
  ```

### 3b.4 — Consensus Scoring

**Problem**: If 3 documents state that Juan works at TechCorp, that weighs more than if only 1 email mentions it.

**Design**:

- **Post-ingestion aggregation** — new step after `contradiction.py`, in `consensus.py`:
  - For each triple (S, P, O) in the batch, count how many independent extractions (different `source_chunk`) produce the same triple
  - `consensus_count` stored as `:Rel` property
  - Score: `consensus_score = min(1.0, consensus_count / 3)` — 3+ sources = maximum confidence

- **Integration in composite score** (see 3b.1 formula)

### 3b Validation Criteria

- Authority weights seeded and resolved via Cypher (zero hardcode)
- Cypher templates execute with correct tenant isolation
- LLM-guided expansion triggers on insufficient subgraph, stays within guardrails
- Consensus scores computed and visible in graph_rag context output
- Composite score formula produces measurably better ranking than confidence-only

---

## Phase 3c: Knowledge Expert

### 3c.1 — Graph Data Assembly

**Problem**: Document generation requires collecting data from multiple graph paths, organizing thematically, and presenting to the LLM in a structured way. Current graph_rag formats for Q&A, not for generation.

**Design**:

- **New service `GraphAssembler`** in `knowledge-tree-service/app/services/graph_assembler.py`:
  - Input: entity_uri + report_type (or list of Cypher templates to execute)
  - Executes N templates in parallel (`asyncio.gather`)
  - Resolves labels, authority weights, consensus scores for each result
  - Output: `AssembledGraph` structure:
    ```python
    @dataclass
    class AssembledGraph:
        subject: EntitySummary           # Main entity
        sections: List[GraphSection]     # Grouped by theme
        kpis: List[KPIResult]           # Computed metrics
        sources: List[SourceRef]        # Source documents (for citations)
        trust_summary: TrustSummary     # Aggregated authority/consensus

    @dataclass
    class GraphSection:
        title: str                       # "Labor relations"
        facts: List[GraphFact]          # Graph facts
        paths: List[GraphPath]          # Relevant multi-hop chains
        confidence: float               # Mean section confidence

    @dataclass
    class KPIResult:
        name: str                        # "total_empleados"
        value: Any                       # 47
        query_template: str             # "count_by_predicate"
        confidence: float               # Data confidence
    ```

- **API endpoint**: `POST /graph/assemble` on KTS

### 3c.2 — Report Templates

**Problem**: Different document types require different graph data and output structure.

**Design**:

- **Report registry** in `knowledge-tree-service/config/report_templates.yaml`:
  ```yaml
  reports:
    entity_profile:
      description: "Complete profile of an entity (person or organization)"
      sections:
        - name: "Identificacion"
          templates: [entity_relations]
          predicates: [core/label, core/type, core/definition]
        - name: "Relaciones laborales"
          templates: [org_people]
          predicates: [legal/empleado-de, legal/cargo-de]
        - name: "Relaciones contractuales"
          templates: [entity_relations]
          predicates: [legal/firmante-de, legal/parte-de-contrato]
        - name: "Marco normativo"
          templates: [applicable_regulations]
      kpis:
        - name: "total_relaciones"
          template: count_by_predicate
          params: { predicate_uri: "*" }
        - name: "documentos_fuente"
          template: count_by_predicate
          params: { predicate_uri: "nouxcube://predicate/prov/derived-from" }

    compliance_report:
      description: "Regulatory compliance report"
      sections:
        - name: "Normativa aplicable"
          templates: [applicable_regulations]
        - name: "Obligaciones contractuales"
          templates: [entity_relations]
          predicates: [legal/clausula, legal/obligacion-de]
        - name: "Riesgos identificados"
          templates: [entity_relations]
          predicates: [core/contradicts]
      kpis:
        - name: "leyes_aplicables"
          template: count_by_predicate
          params: { predicate_uri: "nouxcube://predicate/legal/regulado-por" }
        - name: "contradicciones"
          template: count_by_predicate
          params: { predicate_uri: "nouxcube://predicate/core/contradicts" }

    contract_summary:
      description: "Contract summary with verified graph data"
      sections:
        - name: "Partes"
          templates: [entity_relations]
          predicates: [legal/firmante-de, legal/representante-de]
        - name: "Condiciones economicas"
          templates: [entity_relations]
          predicates: [legal/salario-bruto, legal/importe, legal/duracion]
        - name: "Obligaciones"
          templates: [entity_relations]
          predicates: [legal/clausula, legal/obligacion-de]
      kpis:
        - name: "partes_involucradas"
          template: count_by_predicate
          params: { predicate_uri: "nouxcube://predicate/legal/firmante-de" }
  ```

- **Extensible**: New report types added in YAML without code changes.

### 3c.3 — Document Generation Tool

**Problem**: Emma needs a tool that takes assembled graph data and produces a structured document.

**Design**:

- **New tool `generate_knowledge_report`** in ReAct agent (tool #15):
  ```python
  class GenerateKnowledgeReportTool:
      name = "generate_knowledge_report"
      description = "Generate a structured report from knowledge graph data"

      # Input schema
      entity_uri: str          # Main entity for the report
      report_type: str         # entity_profile | compliance_report | contract_summary | custom
      custom_sections: List    # Only for report_type=custom
      output_format: str       # markdown | pdf (via forge_document)
  ```

- **Generation pipeline**:
  ```
  1. GraphAssembler.assemble(entity_uri, report_type)
     -> AssembledGraph with facts, paths, KPIs, sources

  2. LLM Generation (CHAT model, Langfuse prompt: trustgraph_report_generation)
     -> Prompt includes: AssembledGraph serialized + report template structure
     -> LLM writes the document following the template structure
     -> Every claim must cite its source: [Source: contrato-2025-001, confidence: 0.92]

  3. Post-processing
     -> Verify all citations reference real sources from AssembledGraph
     -> Insert KPIs in corresponding sections
     -> If output_format=pdf -> call forge_document with generated markdown
  ```

- **Langfuse prompt** (`trustgraph_report_generation`):
  ```
  You are a knowledge expert. Generate a {report_type} for {entity_name}.

  VERIFIED DATA FROM KNOWLEDGE GRAPH:
  {assembled_graph_markdown}

  RULES:
  - Use ONLY the provided data. Do not invent information.
  - Every claim must include [Source: doc_id, confidence: X.XX]
  - KPIs go in a dedicated section with table format.
  - If a fact has confidence < 0.60, mark it as "unverified data".
  - If contradictions exist, report them explicitly.
  - Language: {language}
  ```

### 3c.4 — KPI Engine

**Problem**: KPIs are not just counts — they can be ratios, temporal trends, and comparisons requiring aggregation over the graph.

**Design**:

- **KPI types supported**:

  | Type | Example | Cypher Pattern |
  |------|---------|---------------|
  | `count` | Total employees: 47 | `count(o)` |
  | `ratio` | Active contracts/total: 0.73 | `count(active) / count(total)` |
  | `list` | Top 5 suppliers by billing | `collect + sort` |
  | `temporal` | Contracts per quarter | `GROUP BY valid_from quarter` |
  | `comparison` | Employees vs. previous year | Dual query + diff |

- **KPI resolution** in `GraphAssembler`:
  - Each report template KPI executes its Cypher template
  - Result normalized to `KPIResult(name, value, confidence, trend?)`
  - For `ratio` or `comparison` KPIs: assembler executes 2 queries and computes

- **KPI confidence**: The confidence of a KPI is the **minimum** of the confidence values of edges that participated in the calculation. If an employee count includes an edge with confidence 0.45, the KPI inherits 0.45 and is flagged with a warning.

### 3c.5 — Integration with Emma Agent

- **Tool registration**: `generate_knowledge_report` registered in `tools/registry.py`
- **Intent detection**: `classify_node` detects generation intents: "genera un informe de...", "dame un resumen de...", "KPIs de..."
- **SSE events** (new):
  - `report_assembling` — "Gathering graph data..."
  - `report_generating` — "Generating report..."
  - `report_kpi` — Each computed KPI emitted individually for progressive feedback
- **Fallback**: If graph lacks data for a section, the tool indicates this instead of hallucinating. The LLM can then complement with `smart_search` if the user permits.

### 3c Validation Criteria

- `GraphAssembler` returns structured data for all 3 report types
- Generated reports cite only real graph sources (zero hallucinated citations)
- KPIs computed correctly with confidence propagation
- PDF output via `forge_document` integration works end-to-end
- SSE events stream progressively during generation

---

## Key Files (New + Modified)

### Phase 3a
| File | Action | Purpose |
|------|--------|---------|
| `knowledge-tree-service/config/entity_blacklist.yaml` | NEW | Static entity blacklist |
| `knowledge-tree-service/scripts/cleanup_blacklisted_entities.py` | NEW | Retroactive cleanup |
| `knowledge-tree-service/scripts/dedup_entities.py` | NEW | Offline entity deduplication |
| `knowledge-tree-service/scripts/promote_predicates.py` | NEW | Predicate promotion pipeline |
| `knowledge-tree-service/app/services/uri_builder.py` | MODIFY | Canonical name resolution (honorifics, corporate suffixes) |
| `knowledge-tree-service/app/services/extractors/coordinator.py` | MODIFY | Blacklist check + canonical names before storage |
| `knowledge-tree-service/app/services/extractors/relationships.py` | MODIFY | Vector search predicate resolution + binary validation |
| `knowledge-tree-service/app/services/ontology_registry.py` | MODIFY | Vector search integration (OntologyTerms) |
| `knowledge-tree-service/scripts/seed_ontology.py` | MODIFY | Expand to ~85 predicates + seed OntologyTerms |
| `knowledge-tree-service/config/graphs/trustgraph_schema.cypher` | MODIFY | 4 new indexes |
| `weaviate-service/` | MODIFY | OntologyTerms collection creation + seeding |

### Phase 3b
| File | Action | Purpose |
|------|--------|---------|
| `knowledge-tree-service/config/cypher_templates.yaml` | NEW | Multi-hop Cypher template registry |
| `knowledge-tree-service/app/services/consensus.py` | NEW | Consensus scoring post-ingestion |
| `knowledge-tree-service/scripts/seed_authority_weights.py` | NEW | Seed authority weight triples |
| `knowledge-tree-service/app/services/triple_query.py` | MODIFY | `execute_template()` method |
| `knowledge-tree-service/app/api/triples.py` | MODIFY | `POST /triples/template` endpoint |
| `emma-agent-service/app/agents/langgraph/tools/graph_rag.py` | MODIFY | Stage 2.5 guided expansion + composite score |
| `knowledge-tree-service/app/services/extractors/coordinator.py` | MODIFY | Consensus step after contradiction detection |

### Phase 3c
| File | Action | Purpose |
|------|--------|---------|
| `knowledge-tree-service/app/services/graph_assembler.py` | NEW | Graph data assembly service |
| `knowledge-tree-service/config/report_templates.yaml` | NEW | Report template registry |
| `knowledge-tree-service/app/api/reports.py` | NEW | `POST /graph/assemble` endpoint |
| `emma-agent-service/app/agents/langgraph/tools/knowledge_report.py` | NEW | `generate_knowledge_report` tool |
| `emma-agent-service/app/agents/langgraph/tools/registry.py` | MODIFY | Register new tool |
| `emma-agent-service/app/agents/langgraph/nodes/classify.py` | MODIFY | Report generation intent detection |

---

## New Langfuse Prompts

| Prompt Key | Phase | Purpose |
|-----------|-------|---------|
| `trustgraph_binary_validation` | 3a | "Is this a valid semantic predicate?" Yes/No |
| `trustgraph_guided_expansion` | 3b | Evaluate subgraph sufficiency, select expansion nodes |
| `trustgraph_report_generation` | 3c | Generate structured report from assembled graph data |

---

## Configuration (Environment Variables)

| Variable | Default | Phase | Description |
|----------|---------|-------|-------------|
| `ONTOLOGY_RAG_ENABLED` | `true` | 3a | Enable vector-based predicate resolution |
| `ONTOLOGY_BINARY_VALIDATION` | `true` | 3a | Enable binary validation for unknown predicates |
| `ENTITY_BLACKLIST_ENABLED` | `true` | 3a | Enable entity blacklist filtering |
| `AUTHORITY_WEIGHTS_ENABLED` | `true` | 3b | Enable authority weight resolution |
| `GUIDED_EXPANSION_ENABLED` | `true` | 3b | Enable LLM-guided traversal expansion |
| `GUIDED_EXPANSION_MAX_HOPS` | `2` | 3b | Max additional hops from guided expansion |
| `CONSENSUS_SCORING_ENABLED` | `true` | 3b | Enable consensus score computation |
| `REPORT_GENERATION_ENABLED` | `true` | 3c | Enable knowledge report generation tool |

---

## Dependency Graph

```
Phase 3a: Clean Graph
  3a.4 (Schema) ─── no dependencies, do first
  3a.1 (Blacklist) ─── needs schema
  3a.2 (Dedup) ─── needs schema + canonical URIs
  3a.3 (Ontology RAG) ─── needs Weaviate OntologyTerms + expanded seed

Phase 3b: Smart Traversal
  3b.1 (Authority) ─── needs trust/ namespace from 3a.3
  3b.2 (Templates) ─── needs expanded predicates from 3a.3
  3b.4 (Consensus) ─── independent, can parallel with 3b.1
  3b.3 (Guided) ─── needs templates + authority for composite score

Phase 3c: Knowledge Expert
  3c.1 (Assembler) ─── needs templates from 3b.2 + authority from 3b.1
  3c.2 (Report Templates) ─── needs assembler
  3c.4 (KPI Engine) ─── needs assembler + templates
  3c.3 (Generation Tool) ─── needs assembler + KPIs + report templates
  3c.5 (Integration) ─── needs generation tool
```
