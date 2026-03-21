# BKG Phase 6: Unified Knowledge Tree — Design Spec

**Date:** 2026-03-21
**Status:** Approved
**Scope:** Unify tenant sector graph with legal proxies, real edges, and anti-hallucination context
**References:**
- [NVIDIA: Insights, Techniques and Evaluation for LLM-Driven Knowledge Graphs](https://developer.nvidia.com/blog/insights-techniques-and-evaluation-for-llm-driven-knowledge-graphs/)
- [NVIDIA: Workbench Agentic RAG Example](https://github.com/NVIDIA/workbench-example-agentic-rag)
- BKG Phases 1-5 (completed Mar 2026) — see memory `bkg_refactoring.md`

---

## Important Notes

### Node labels

`structural_document` and `structural_folder` are created dynamically by the structural indexer at indexing time — they do NOT appear in the `.cypher` schema files. They exist across all sectors. The sector-specific schemas define domain labels (e.g., `Ley`, `Contrato` in legal; `Paciente`, `HistoriaClinica` in medical). Both coexist in the same graph.

`LegalLaw` is a NEW vlabel introduced by this spec. It is distinct from the existing `Ley` label in the legal sector schema. `LegalLaw` represents proxy nodes synced from `knowledge_graph_public` with `shared: true`. In the legal sector, both `Ley` (tenant-owned) and `LegalLaw` (public proxy) will coexist.

### EntityType proxy backfill

Existing EntityType proxy nodes (created by BKG Phase 2) do not have a `shared` property. A backfill step must add `shared: true` to all existing EntityType nodes before the unified query can filter by `neighbor.shared = true`. This is a one-time migration in `graph_bootstrap.py`.

---

## Context

After BKG Phases 1-5, the knowledge-tree-service has 3 separate Apache AGE graphs:

| Graph | Content | Query Pattern |
|-------|---------|---------------|
| `{sector}_graph` | Tenant documents, folders, persons, entities, ontology proxies, memories | SmartSearch, structural_query, SubgraphExtractor |
| `knowledge_graph_public` | BOE legislation (47 laws, articles, inter-law relations) | LegalGraphService, SubgraphExtractor._lookup_legal() |
| `business_ontology` | EntityType + RelationType (type system) | OntologyService (already uses proxy pattern) |

Cross-graph relationships exist only at runtime — SubgraphExtractor runs 3 sequential queries and merges results in Python with synthetic edges. This causes two hallucination patterns:

- **Type D (person/tenant mixing):** Without explicit `ASOCIADO_A` edges in the LLM context, the model infers relationships by semantic proximity and attributes documents to wrong persons
- **Type E (unsourced answers):** When RAG context lacks relational evidence, the LLM fills gaps with parametric knowledge (fabricated)

---

## Architecture

### Before (3 graphs, runtime cross-reference)

```
{sector}_graph          knowledge_graph_public       business_ontology
+-- structural_folder   +-- LegalLaw                 +-- EntityType
+-- structural_document |   +-- LegalArticle          +-- RelationType
+-- Persona             +-- edges: MODIFIES,
+-- Organizacion             DEROGATES, REFERENCES
+-- EntityType (proxy)
+-- DocumentMemory
+-- edges: HAS_DOCUMENT, ASOCIADO_A,
    INSTANCE_OF, EXTRACTED_FROM, HAS_MEMORY
```

Cross-reference: 3 sequential queries, synthetic edges in Python.

### After (1 graph per tenant, real edges)

```
{sector}_graph (unified)
|
+-- DOCUMENTARY BRANCH (tenant-owned)
|   +-- structural_folder --[:HAS_DOCUMENT]--> structural_document
|   +-- structural_document --[:ASOCIADO_A]--> Persona
|   +-- structural_document <--[:EXTRACTED_FROM]-- Organizacion
|   +-- structural_document --[:HAS_MEMORY]--> DocumentMemory
|
+-- LEGAL BRANCH (shared=true, synced from knowledge_graph_public)
|   +-- LegalLaw {boe_id, short_name, domain, status, shared: true}
|   +-- LegalLaw --[:MODIFIES]--> LegalLaw
|   +-- LegalLaw --[:DEROGATES]--> LegalLaw
|   +-- LegalLaw --[:REFERENCES]--> LegalLaw
|
+-- ONTOLOGY BRANCH (shared=true, synced from business_ontology)
|   +-- EntityType {name, display_name, category, parent, shared: true}
|
+-- CROSS-BRANCH EDGES (created during indexing)
|   +-- structural_document --[:APLICA]--> LegalLaw
|   +-- structural_document --[:INSTANCE_OF]--> EntityType
|   +-- Persona --[:INSTANCE_OF]--> EntityType
|
+-- Property `shared: true` distinguishes public nodes from tenant-owned
```

### What changes

| Component | Before | After |
|-----------|--------|-------|
| LegalLaw nodes | Only in `knowledge_graph_public` | Proxy + inter-law relations in `{sector}_graph` |
| Edge doc-to-law | Synthetic in Python (runtime) | Real in AGE (`:APLICA`, created at indexing) |
| SubgraphExtractor | 3 sequential queries | 1 Cypher query, multi-hop |
| `knowledge_graph_public` | Primary source queried at RAG time | Source of truth for sync only, not queried at RAG time |
| `business_ontology` | Ontology source | No changes (already uses proxy pattern) |

### What does NOT change

- `knowledge_graph_public` continues to exist as source of truth for BOE
- `business_ontology` continues to exist as ontology source
- EntityType proxy pattern already works — we extend the same pattern to LegalLaw
- Weaviate `PublicKnowledge` continues serving article content via `smart_search`
- Multi-tenant isolation via `tenant_id` on tenant nodes (laws have `shared: true`)

---

## Component 1: LegalProxySyncService

**New file:** `knowledge-tree-service/app/services/legal_proxy_sync.py`

Syncs LegalLaw nodes + inter-law relations from `knowledge_graph_public` to `{sector}_graph` as proxy nodes with `shared: true`.

### Sync flow

```
knowledge_graph_public                    {sector}_graph
+----------------------+                 +----------------------+
| LegalLaw "ET"        |   --MERGE-->   | LegalLaw "ET"        |
|   boe_id, title,     |                |   boe_id, short_name,|
|   short_name, domain,|                |   domain, status,    |
|   status, ...        |                |   title, shared:true,|
|                      |                |   synced_at          |
| ET -[:MODIFIES]->LGSS|   --MERGE-->   | ET -[:MODIFIES]->LGSS|
+----------------------+                 +----------------------+
```

### Proxy node properties (lightweight subset)

| Property | Copied | Reason |
|----------|--------|--------|
| `boe_id` | Yes | MERGE key |
| `short_name` | Yes | For regex matching ("ET", "LIVA") |
| `domain` | Yes | For domain_match fallback |
| `status` | Yes | Filter derogated laws |
| `title` | Yes | Display in subgraph formatter |
| `shared` | Yes (= true) | Distinguish from tenant nodes |
| `synced_at` | Yes | Track last sync |
| `eli_uri`, `summary`, `keywords`, `weaviate_uuid` | No | Heavy content, not needed for edges |

### Sync Cypher

```sql
-- Sync a proxy LegalLaw
SELECT * FROM cypher('{sector}_graph', $$
    MERGE (law:LegalLaw {boe_id: '{boe_id}', shared: true})
    SET law.short_name = '{short_name}',
        law.domain = '{domain}',
        law.status = '{status}',
        law.title = '{title}',
        law.synced_at = '{now}'
    RETURN law
$$) AS (law agtype)

-- Sync an inter-law relation
-- IMPORTANT: rel_type MUST be validated against whitelist before interpolation
-- Valid values: {"MODIFIES", "DEROGATES", "REFERENCES"}
SELECT * FROM cypher('{sector}_graph', $$
    MATCH (a:LegalLaw {boe_id: '{source_boe_id}', shared: true}),
          (b:LegalLaw {boe_id: '{target_boe_id}', shared: true})
    MERGE (a)-[r:{rel_type}]->(b)
    RETURN r
$$) AS (r agtype)
```

Idempotent: all operations are MERGE (upsert). Running sync multiple times produces the same result.

### API

**New endpoint:** `POST /tree/legal-sync`

```json
// Request (optional body)
{"force": false}

// Response
{
  "synced_laws": 47,
  "synced_edges": 152,
  "new_laws": 0,
  "updated_laws": 3,
  "elapsed_ms": 340
}
```

### When sync runs

| Trigger | Mechanism | Automatic? |
|---------|-----------|------------|
| Service startup | `graph_bootstrap.py` after creating sector graph | Yes |
| Post-BOE download | Admin calls `POST /tree/legal-sync` | Manual |
| Onboarding script | `./onboarding.sh` adds sync step after BOE download | Yes (within onboarding) |
| Existing law update | `POST /boe/sync/{boe_id}` callback to legal-sync | Semi-automatic |

### Sector applicability

BOE downloads are **manual per admin**. Whatever laws exist in `knowledge_graph_public` get synced to the tenant graph. No preset filtering by sector — admin decides which laws to download.

| Sector | Typical laws | Scale |
|--------|-------------|-------|
| Legal | All 47 laws (13 presets) | ~47 nodes + ~150 edges |
| Medical | LOPDGDD + future healthcare laws | ~1-5 nodes |
| Documental | LOPDGDD + sector-specific (LAU, LOMLOE) | ~2-10 nodes |

---

## Component 2: LegalReferenceBridge

**New file:** `knowledge-tree-service/app/services/legal_reference_bridge.py`

Detects legal references in documents during indexing and creates real `:APLICA` edges in the tenant graph.

### Detection strategy (2 levels, no LLM)

| Level | Method | Latency | When |
|-------|--------|---------|------|
| 1 | Regex patterns (BOE IDs, short_names, "Ley X/YYYY", "art. N del ET") | ~3ms | Always |
| 2 | Domain fallback — if regex matches 0 but `domain` coincides with a law's domain | ~1ms | Only if regex = 0 matches |

**No LLM in this step:** Regex + domain matching is sufficient and predictable. Using the LLM for reference detection would add ~200ms and risk hallucination in the indexing pipeline itself — counterproductive.

**Reuse existing patterns:** The existing `LegalReferenceExtractor` (`knowledge-tree-service/app/services/extractors/legal_reference_extractor.py`) already has extensive regex patterns for BOE IDs, article references, and law names. `LegalReferenceBridge` should delegate regex detection to `LegalReferenceExtractor` rather than reimplementing patterns.

### Edge properties (`:APLICA`)

```
{
  confidence: float,      // 0.95 (regex) or 0.6 (domain_match)
  source: str,            // 'regex' | 'domain_match'
  article: str | null,    // '15' if specific article detected
  created_at: str         // ISO timestamp
}
```

### API

**New endpoint:** `POST /tree/legal-links/extract-and-store`

```json
{
  "tenant_id": "uuid",
  "document_id": "uuid",
  "text_sample": "first 2000 chars of document",
  "semantic_type": "contrato",
  "domain": "labor"
}
```

### Indexing flow

```
Document indexed --> weaviate-service
    --> EntityGraphBridge.store_entities()           [existing, no changes]
    --> MemoryGenerator.generate()                   [existing, no changes]
    --> LegalReferenceBridge.extract_and_link()       [NEW]
        +-- Step 1: Regex (~3ms) detects patterns:
        |   "art. 15 del ET", "Ley 1/2015", "BOE-A-2015-11430",
        |   "Estatuto de los Trabajadores", "LIRPF"
        |
        +-- Step 2: Resolve against proxy LegalLaw in {sector}_graph
        |   regex match "ET" --> MATCH (law:LegalLaw {short_name: 'ET', shared: true})
        |   If no proxy exists --> skip (law not in system)
        |
        +-- Step 3: MERGE edge in AGE
            MERGE (doc)-[r:APLICA]->(law)
            SET r.confidence = 0.95, r.source = 'regex', r.article = '15', r.created_at = '{now}'
```

### Integration with weaviate-service

In `extraction_service.py`, after `store_entities()`:

```python
# Fire-and-forget (does not block indexing)
asyncio.create_task(
    knowledge_tree_client.extract_and_link_legal(
        tenant_id=tenant_id,
        document_id=document_id,
        text_sample=text[:2000],
        semantic_type=semantic_type,
        domain=domain,
    )
)
```

---

## Component 3: Unified SubgraphExtractor

### Current flow (3 queries)

```python
seeds = await self._resolve_seeds(graph_name, tenant_id, entities)           # Query 1
raw_nodes, raw_edges = await self._traverse(graph_name, tenant_id, ...)      # Query 2
legal_nodes, legal_edges = await self._lookup_legal(raw_nodes)                # Query 3
# Merge in Python with synthetic APLICA edges
```

### New flow (1 query)

```python
seeds = await self._resolve_seeds(graph_name, tenant_id, entities)
nodes, edges = await self._traverse_unified(graph_name, tenant_id, seeds, max_hops, max_nodes)
# No _lookup_legal — laws are already in the same graph with real edges
return self._prune(nodes, edges, seeds, max_nodes)
```

### Unified Cypher query

```sql
SELECT * FROM cypher('{sector}_graph', $$
    MATCH (seed)
    WHERE seed.tenant_id = '{tenant_id}'
      AND (seed.name =~ '(?i).*{entity}.*'
           OR seed.associated_person =~ '(?i).*{entity}.*')

    MATCH path = (seed)-[r*1..{max_hops}]-(neighbor)
    WHERE neighbor.tenant_id = '{tenant_id}'
       OR neighbor.shared = true

    UNWIND relationships(path) AS rel
    RETURN DISTINCT
        startNode(rel) AS source,
        type(rel) AS relation,
        endNode(rel) AS target
    LIMIT {max_nodes * 3}
$$) AS (source agtype, relation agtype, target agtype)
```

Key change: `OR neighbor.shared = true` includes proxy LegalLaw and EntityType nodes in the traversal. One query, ~50-100ms vs ~200ms current.

### `_lookup_legal()` removal

The `_lookup_legal()` method is deleted entirely. Its cross-graph domain matching is replaced by real `:APLICA` edges created during indexing.

The `include_legal` parameter on `extract()` and `SubgraphRequest` becomes dead code. It should be deprecated: keep the parameter for API backwards compatibility but ignore it (all shared nodes are now included via `neighbor.shared = true`).

---

## Component 4: Anti-Hallucination Context

### SubgraphFormatter improvements

Enhanced format with source traceability:

```
[SUBGRAFO RELEVANTE -- relaciones verificadas del repositorio]

Factura_2024-001 (factura, carpeta: Javier Martinez/Facturas)
   +-- ASOCIADO_A -> Javier Martinez [persona]
   +-- APLICA -> Ley 37/1992 (LIVA) [ley, confidence: 0.95, source: regex]
   +-- APLICA -> LOPDGDD [ley, confidence: 0.6, source: domain_match]
   +-- INSTANCE_OF -> factura -> financial_document [ontologia]

Contrato_Laboral_JM (contrato, carpeta: Javier Martinez/Contratos)
   +-- ASOCIADO_A -> Javier Martinez [persona]
   +-- FIRMADO_POR -> ACME Corp [organizacion]
   +-- APLICA -> Real Decreto Legislativo 2/2015 (ET) [ley, confidence: 0.95, source: regex]
   |   +-- ET --MODIFIES--> LGSS
   +-- INSTANCE_OF -> contrato -> legal_document [ontologia]

Sin referencias legales encontradas: [documento sin APLICA edges]

IMPORTANTE: Solo se muestran relaciones verificadas del grafo.
No inventes relaciones adicionales entre documentos y leyes.
```

Changes:
1. **Explicit header:** "relaciones verificadas del repositorio" — primes LLM not to fabricate
2. **Confidence + source on APLICA edges:** LLM knows if regex (reliable) or domain_match (inferred)
3. **Explicit person per document:** `ASOCIADO_A -> Javier Martinez` prevents person mixing (type D)
4. **Guard footer:** "No inventes relaciones adicionales" — in-context guardrail
5. **Law-to-law chains:** LLM sees `ET --MODIFIES--> LGSS` without needing to invent

### ReAct agent prompt guardrails

New section in `react_loop` system prompt (Langfuse key: `emma_react_system`):

```
## Sobre las fuentes documentales
- El [SUBGRAFO RELEVANTE] contiene SOLO relaciones verificadas del repositorio.
- Si un documento NO tiene edge ASOCIADO_A hacia una persona, NO atribuyas ese documento a ninguna persona.
- Si un documento NO tiene edge APLICA hacia una ley, NO cites esa ley como aplicable.
- Prefiere decir "no se encontre relacion directa" antes que inferir relaciones no presentes.
```

---

## Files Changed Summary

### New files (4)

| File | Service | Purpose |
|------|---------|---------|
| `knowledge-tree-service/app/services/legal_proxy_sync.py` | LegalProxySyncService | Sync LegalLaw + inter-law edges to sector graph |
| `knowledge-tree-service/app/services/legal_reference_bridge.py` | LegalReferenceBridge | Regex detection of legal refs + APLICA edge creation |
| `knowledge-tree-service/app/api/legal_sync.py` | API | `POST /tree/legal-sync`, `GET /tree/legal-sync/status` |
| Langfuse prompt (via seed script) | — | Anti-hallucination guardrails for react_loop |

### Modified files (7)

| File | Change |
|------|--------|
| `knowledge-tree-service/app/services/graph_bootstrap.py` | Call `legal_proxy_sync.sync()` after sector graph creation |
| `knowledge-tree-service/app/services/subgraph_extractor.py` | Delete `_lookup_legal()`, add `_traverse_unified()` single query |
| `knowledge-tree-service/config/graphs/legal_graph_schema.cypher` | Add LegalLaw vlabel, MODIFIES/DEROGATES/REFERENCES/APLICA elabels |
| `knowledge-tree-service/config/graphs/medical_graph_schema.cypher` | Same schema additions |
| `knowledge-tree-service/config/graphs/documental_graph_schema.cypher` | Same schema additions |
| `knowledge-tree-service/app/main.py` | Register legal_sync_router, initialize legal_reference_bridge |
| `weaviate-service/app/services/knowledge/extraction_service.py` | Fire-and-forget call to LegalReferenceBridge post-indexing |
| `weaviate-service/app/clients/knowledge_tree_client.py` | New method `extract_and_link_legal()` |
| `emma-agent-service/app/agents/langgraph/tools/subgraph_formatter.py` | Enhanced format with traceability |

### Implementation order

1. Schema updates — vlabels + elabels in 3 sector schemas + `LegalLaw` vlabel
2. EntityType backfill — add `shared: true` to existing EntityType proxy nodes
3. LegalProxySyncService — sync laws to sector graph
4. Bootstrap integration — auto-sync on startup + EntityType backfill
5. LegalReferenceBridge — regex detection + edge creation (reuse LegalReferenceExtractor)
6. Weaviate integration — fire-and-forget post-indexing
7. SubgraphExtractor refactor — unified query, delete `_lookup_legal`, deprecate `include_legal`
8. SubgraphFormatter — format with traceability + absence rendering
9. Langfuse prompts — anti-hallucination guardrails (`emma_react_loop_system`)
10. Sanity checks — verify real edges in graph + E2E test

---

## Expected Impact

| Problem | Root Cause | How This Resolves It |
|---------|-----------|---------------------|
| D: Person mixing | No explicit ASOCIADO_A edges in LLM context | Subgraph includes `doc -[:ASOCIADO_A]-> Persona` explicitly. Prompt: "if no edge, don't attribute" |
| E: Unsourced answers | Insufficient relational context, LLM fills with parametric knowledge | Traceable chains `doc -> law -> related law`. Format with confidence. Footer: "don't invent relations" |

### Performance

| Metric | Before | After |
|--------|--------|-------|
| SubgraphExtractor queries | 3 sequential | 1 unified |
| Subgraph extraction latency | ~200ms | ~50-100ms |
| Indexing overhead (legal refs) | 0ms | ~5ms (regex, fire-and-forget) |
| Bootstrap overhead (sync) | 0ms | ~300ms one-time |

### Scale per tenant

| Component | Legal sector | Medical sector | Documental sector |
|-----------|-------------|----------------|-------------------|
| Proxy LegalLaw nodes | ~47 | ~1-5 | ~2-10 |
| Inter-law edges | ~150 | ~0-3 | ~0-10 |
| APLICA edges | Varies by doc count | Few | Few |
| Total proxy overhead | ~50KB | ~1KB | ~5KB |
