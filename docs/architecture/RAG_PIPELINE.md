# RAG Pipeline — NouxCubeIA

**As of 2026-04-22 — post-domain-removal refactor.**

This document describes the Retrieval-Augmented Generation (RAG) pipeline as implemented across two microservices: **weaviate-service** (indexing) and **emma-agent-service** (retrieval via the `smart_search` and `graph_rag` tools). It reflects the current single-tenant architecture after the removal of multi-tenancy, sectors, and the `domain` field.

---

## Part 1: Overview

### What the RAG Pipeline Is

The RAG pipeline converts uploaded or synced documents into searchable vector embeddings (indexing) and then retrieves the most relevant chunks at query time to feed the Emma LangGraph agent (retrieval). It spans four data stores:

| Store | Role |
|-------|------|
| **Weaviate** | Vector index — HNSW (cosine), hybrid BM25 + dense search |
| **FalkorDB** | TrustGraph triple store — entity relationships, provenance |
| **Redis** | Short-lived embedding cache (5 s TTL), RLM result cache (1 h TTL), semantic cache |
| **PostgreSQL** | `indexed_documents` table (canonical document metadata) |

### Weaviate Collections

All collection names are fixed for the single-tenant deployment:

| Collection | Purpose |
|-----------|---------|
| `Nouxcube_documents` | Document chunks — primary retrieval target |
| `Nouxcube_documents_summaries` | Document-level summaries for hierarchical retrieval (long docs) |
| `Nouxcube_knowledge` | Extracted knowledge entities with embeddings |
| `Nouxcube_visual` | Visual content embeddings (images, tables, diagrams from PDFs) |
| `TrustGraphEntities` | Entity vectors — used by `graph_rag` Stage 1 seed lookup |
| `OntologyTerms` | Predicate ontology for semantic predicate resolution in TrustGraph |

### Where the Code Lives

```
backend/microservices/
  weaviate-service/app/services/rag/         Indexing pipeline classes
  weaviate-service/app/services/             WeaviateService (hybrid_search)
  weaviate-service/app/core/config.py        All RAG env vars
  intelligence-docs-service/app/pipeline/   classify_document, text extraction
  emma-agent-service/app/agents/langgraph/tools/smart_search.py  Retrieval
  emma-agent-service/app/agents/langgraph/tools/graph_rag.py     TrustGraph retrieval
  emma-agent-service/app/agents/langgraph/nodes/rlm_processor.py RLM long-doc cache
```

---

## Part 2: Indexing Pipeline

### Flow

```
Upload or Connector Sync
        |
        v
intelligence-docs-service (classify_document + text extraction)
        |
        |  file_bytes + filename + metadata
        v
IndexingPipeline.process_file()                [weaviate-service]
  |
  +-- Stage 1:   Text Extraction (Tika via intelligence-docs-service)
  |                 └─ Stage 1.5: Enhanced OCR fallback (EasyOCR/Tesseract)
  |                               triggered when quality < ENHANCED_OCR_QUALITY_THRESHOLD
  |
  +-- Stage 2:   DocumentIntelligence.analyze()
  |                 └─ quality: HIGH/MEDIUM/LOW/FAILED
  |                 └─ confidence score 0.0-1.0
  |                 └─ detects: tables, headers, lists, encoding issues
  |                 └─ cleaned text if needs_cleaning=True
  |
  +-- Stage 3:   SemanticChunker.chunk_document()
  |                 └─ document_type → chunking strategy
  |                 └─ Stage 3b (optional): parent-child chunker
  |                    small children (~300 tok) indexed; parent (~1500 tok) stored in metadata
  |
  +-- Stage 4:   ContextualRetrievalService.analyze_document()   [Anthropic pattern]
  |                 └─ reads document_type from metadata (set by classifier)
  |                 └─ extracts key entities (dates, amounts, NIFs) via regex
  |                 └─ generates context_prefix
  |                 └─ prepends prefix to each chunk before embedding
  |                 └─ Stage 4a (optional): per-chunk LLM enrichment via context_enricher
  |
  +-- Stage 4.5: Entity Extraction (LangExtract via intelligence-docs-service)
  |                 └─ LLM-based named entity recognition (PERSON, ORG, etc.)
  |
  +-- Stage 5a:  KnowledgeExtractionService.extract_from_document()
  |                 └─ sends entities → knowledge-tree-service /extract/triples
  |                 └─ TrustGraph: 4 parallel LLM extractors → FalkorDB MERGE
  |
  +-- Stage 5b:  HierarchicalIndexer.generate_document_summary()
  |                 └─ LLM summary + key_topics
  |                 └─ indexed in Nouxcube_documents_summaries
  |                 └─ enabled when RAG_HIERARCHICAL_ENABLED=true
  |
  +-- Stage 6:   VisualExtractor (optional, PDF only)
  |                 └─ extracts images, tables, diagrams
  |                 └─ multimodal embeddings → Nouxcube_visual
  |                 └─ enabled when MULTIMODAL_EMBEDDING_ENABLED=true
  |
  +-- Stage 7:   Write chunks to Weaviate (Nouxcube_documents)
  |                 └─ embedding: title + chunk_content → intelligence-docs-service (BGE-M3 / Jina v3)
  |                 └─ properties: roles[], document_type, semantic_type, quality_score,
  |                               associated_person, folder_path, chunk_index, parent_chunk_id
  |
  +-- Event:     publish document.indexed → Redis Streams → Emma Reactive
```

### Stage Details

#### Stage 1 — Text Extraction

| | |
|-|-|
| **Class/Method** | `IntelligenceExtractClient.extract_from_bytes()` |
| **Input** | raw file bytes, filename, extraction_strategy (`auto`/`fast`/`hi_res`) |
| **Output** | `TextExtractResult` (text, language, characters, metadata) |
| **Notes** | MIME type detected from magic bytes by intelligence-docs-service (Tika backend). Strategy `hi_res` uses Docling. |

#### Stage 1.5 — Enhanced OCR Fallback

Triggered when `ENHANCED_OCR_ENABLED=true` and either the file is an image, the PDF produced fewer than 50 chars, or `DocumentIntelligence.should_trigger_enhanced_ocr()` returns True.

| | |
|-|-|
| **Config** | `ENHANCED_OCR_ENABLED=true`, `ENHANCED_OCR_QUALITY_THRESHOLD=0.60`, `ENHANCED_OCR_LANGUAGES=es,en` |
| **Failure mode** | Non-blocking — warns in `IndexingResult.warnings`, continues with Tika text |

#### Stage 2 — Document Intelligence

| | |
|-|-|
| **Class** | `DocumentIntelligence` (`document_intelligence.py`) |
| **Output** | `DocumentAnalysis` — quality enum, confidence 0-1, structural flags, cleaned text |
| **Quality tiers** | HIGH (>0.85), MEDIUM (0.60-0.85), LOW (<0.60), FAILED |

#### Stage 3 — Semantic Chunking

`SemanticChunker.chunk_document()` selects a chunking strategy from the `document_type` derived from metadata:

| `DocumentType` | Strategy |
|---------------|---------|
| `LEGAL_CONTRACT` | Clause-aware splitting (target 1500 tok) |
| `LEGAL_BRIEF` | Section-aware |
| `TECHNICAL_MANUAL` | Markdown/header-aware |
| `FINANCIAL_REPORT` | Table-preserving |
| `MEDICAL_RECORD` | Paragraph splitting |
| `GENERAL` | Default semantic splitting (target 1000 tok) |

`ACTIVE_SECTOR` env var can override chunking parameters via `_get_sector_strategy()`, but the unified config makes this a pass-through by default.

| Config | Default |
|--------|---------|
| `MAX_CHUNK_SIZE` | 1000 |
| `CHUNK_OVERLAP` | 200 |
| `PARENT_CHILD_CHUNKING_ENABLED` | false |
| `PARENT_CHUNK_SIZE` | 1500 |
| `CHILD_CHUNK_SIZE` | 300 |

#### Stage 4 — Contextual Retrieval (Anthropic Pattern)

This stage prepends a short context string to each chunk before it is embedded. The context is constructed from the `document_type` in metadata (set by the upstream classifier) and key entities extracted from the raw text.

**Key class:** `ContextualRetrievalService` in `contextual_retrieval.py`

```python
def generate_context_prefix(self, document_type: str = "", key_entities: Optional[List[str]] = None) -> str:
    # Returns e.g.:
    # "[CONTEXTO] Documento tipo `contrato_laboral`. Entidades: fecha:01/01/2025, importe:2000€. [CONTENIDO]"
```

The prefix is prepended to each chunk's `.content` field before embedding so that the vector space encodes document context rather than relying on query-time prompts. See Part 3 for detail.

| Config | Default |
|--------|---------|
| `CONTEXTUAL_RETRIEVAL_ENABLED` | true |
| `CONTEXTUAL_RETRIEVAL_USE_LLM` | false |
| `CONTEXTUAL_RETRIEVAL_MAX_CONTEXT_LENGTH` | 300 |

#### Stage 5a — TrustGraph Extraction

Knowledge triples extracted via `knowledge-tree-service` are written to FalkorDB. This is a fire-and-forget call from `KnowledgeExtractionService.extract_from_document()`. See [TRUSTGRAPH.md](TRUSTGRAPH.md) for the full extraction pipeline.

#### Stage 5b — Hierarchical Summary

An LLM-generated document summary is stored in `Nouxcube_documents_summaries`. At retrieval time this enables a two-pass strategy: summary search (high recall) then chunk search (precision). Controlled by `RAG_HIERARCHICAL_ENABLED=true`.

#### Stage 6 — Visual Extraction (Optional)

PDF-only. Extracts images, embedded tables (as images), and diagrams. Each visual element is embedded via `MultimodalEmbeddingService` and stored in `Nouxcube_visual`. Disabled by default (`MULTIMODAL_EMBEDDING_ENABLED=false`).

#### Stage 7 — Weaviate Write

Embeddings are generated by intelligence-docs-service (BGE-M3, 1024 dims, GPU). Each chunk object stores:

- `roles: TEXT_ARRAY` — KeyCloak role names + `EVERYONE` sentinel for ACL
- `document_type: TEXT` — classifier output (sole taxonomy, no `domain` field)
- `semantic_type: TEXT` — finer document type (factura, contrato, nomina, etc.)
- `quality_score: NUMBER` — from DocumentIntelligence
- `associated_person: TEXT` — from folder hierarchy or entity extraction
- Position properties: `page_start`, `page_end`, `char_start`, `char_end`, bbox coords

---

## Part 3: Contextual Retrieval (Anthropic Pattern)

### Motivation

Classic RAG embeds raw chunks without document-level context, causing retrieval failures when a chunk's content is ambiguous without knowing it came from a labor contract vs. a fiscal report. The Anthropic Contextual Retrieval pattern addresses this by encoding the context directly in the embedded text.

### Current Implementation (Post-Domain-Removal)

The `domain` field and `detect_domain()` method were removed. The context prefix is now built exclusively from:

1. **`document_type`** — provided by the upstream classifier (intelligence-docs-service `classify_document()`), written into `metadata["document_type"]` before entering the pipeline
2. **Key entities** — regex-extracted from the raw document text

```python
# contextual_retrieval.py — ContextualRetrievalService

def generate_context_prefix(self, document_type: str = "", key_entities: Optional[List[str]] = None) -> str:
    parts = ["[CONTEXTO]"]
    if document_type and document_type != "general":
        parts.append(f" Documento tipo `{document_type}`.")
    if key_entities:
        ent_summary = ", ".join(key_entities[:5])
        parts.append(f" Entidades: {ent_summary}.")
    parts.append(" [CONTENIDO]")
    return "".join(parts)
```

Entity extraction uses lightweight regex patterns (no LLM):

- Dates: `\d{1,2}[/-]\d{1,2}[/-]\d{2,4}` → `fecha:01/01/2025`
- Amounts: pattern matching `€`, `euros`, `EUR` → `importe:2000€`
- NIFs: `[A-Z]?\d{7,8}[A-Z]` → `nif:12345678A`

### `ContextGenerationResult` Schema

```python
@dataclass
class ContextGenerationResult:
    document_id: str
    document_type: str       # From metadata (classifier output)
    context_prefix: str      # Prepended to each chunk
    document_summary: str    # First 500 chars (heuristic)
    key_entities: List[str]  # ["fecha:01/01/2025", "importe:2000€"]
    metadata: Dict[str, Any]
```

Note: `applicable_laws` was removed in the domain-removal refactor. The `metadata` dict is now always `{}`.

### LLM Enhancement Path

When `CONTEXTUAL_RETRIEVAL_USE_LLM=true`, `_enhance_with_llm()` is called after rule-based generation. It sends the first 1000 chars of the document plus the `document_type` and extracted entities to the vLLM SGLang endpoint to produce a richer context prefix (max 200 tokens). The LLM response is stripped of `<think>` blocks before use. This path is disabled by default due to indexing latency cost.

### How Chunks Are Contextualized

In `IndexingPipeline._process_text_internal()`, after `analyze_document()` returns:

```python
context_result = await contextual_retrieval.analyze_document(...)
for chunk in chunks:
    original_text = chunk.content
    chunk.content = f"{context_result.context_prefix} {original_text}"
    chunk.metadata["contextual_prefix_applied"] = True
    chunk.metadata["original_text_length"] = len(original_text)
```

The modified `chunk.content` is what gets embedded. The original text is not stored separately in Weaviate (the prefix is baked into the vector).

### Per-Chunk LLM Enrichment (Stage 4a)

When `CONTEXTUAL_RETRIEVAL_USE_LLM=true`, `context_enricher.enrich_chunks()` additionally generates a 1-2 sentence context for each individual chunk (not just a document-level prefix), further improving retrieval precision for long documents with varied content.

---

## Part 4: Retrieval Pipeline (Query-Time)

### Entry Point

The Emma LangGraph agent uses two tools for RAG retrieval:

1. **`smart_search`** — unified hybrid search across Weaviate + FalkorDB TrustGraph
2. **`graph_rag`** — 8-stage knowledge graph pipeline (entity → BFS → expansion → LLM scoring → provenance)

These are separate tools. `smart_search` calls into Weaviate with optional graph expansion. `graph_rag` queries TrustGraph directly via knowledge-tree-service.

### `smart_search` Input Schema

```python
class SmartSearchInput(BaseModel):
    query: str                         # Required — natural language query
    person_filter: Optional[str]       # Human name only (validated — rejects topic words)
    folder_filter: Optional[str]       # Folder path, e.g. /Contratos/ACME
    date_from: Optional[str]           # ISO 8601, e.g. 2026-02-01
    date_to: Optional[str]             # ISO 8601
    limit: int = 10                    # 1-20
```

There is no `domain_filter` or `semantic_type_filter` parameter in the tool input — the `semantic_type` filter is inferred automatically from query keywords by the tool itself (see keyword map `_SEMANTIC_TYPE_KEYWORDS`).

### Retrieval Pipeline Steps

```
Query
  |
  +-- Step 1: Entity Extraction (~3ms)
  |   regex patterns from UNIFIED_ENTITY_PATTERNS (14 types: ley, articulo,
  |   boe, nif, fecha, importe, persona, referencia, etc.)
  |
  +-- Step 1b: Query Expansion (~0-2ms)
  |   Spanish stem map (static dict) + optional NLTK Snowball
  |   "facturas" → "factura", "firmados" → "firma"
  |
  +-- Step 2: Filter Enrichment
  |   entities["persona"][0] → enriched_person_filter (validated)
  |   query keywords → enriched_semantic_type (factura, contrato, nomina, ...)
  |
  +-- Step 3: Graph Expansion (~20-200ms, optional)
  |   IF GRAPHRAG_ENABLED and entities:
  |     → knowledge-tree-service /subgraph extraction (multi-hop BFS)
  |     → doc_ids for re-ranking boost
  |   ELIF SMART_SEARCH_GRAPH_ENABLED and person:
  |     → FalkorDB lookup by associated_person
  |
  +-- Step 4: Parallel Hybrid Search (~100ms)
  |   Weaviate hybrid_search():
  |     - BM25 (keyword) + dense vector (cosine HNSW)
  |     - alpha weighting (default 0.5, sector-configurable)
  |     - ACL filter: roles CONTAINS_ANY (user_roles + EVERYONE)
  |     - Optional filters: semantic_type, associated_person, folder_path,
  |                         date_from, date_to, min_quality
  |     - Fallback: if BM25 returns 0 results with enrichment filters active,
  |                 retries with filter-only fetch_objects
  |
  +-- Step 5: Merge + Deduplicate
  |
  +-- Step 6: Multi-Signal Re-Rank (~1ms)  [see Part 5]
  |
  +-- Step 6b: Optional Cross-Encoder Re-Rank (~50-100ms)
  |   SMART_SEARCH_CROSS_ENCODER_ENABLED (default: false)
  |
  +-- Step 6c: Parent-Child Expansion
  |   If chunk has parent_content, swap content for LLM context window
  |
  +-- Step 6d: Retrieval Quality Assessment
  |   retrieval_guard.assess_retrieval_quality()
  |
  +-- Step 7: Format for LLM
      Returns ToolResult with structured text + source metadata
```

### ACL Enforcement

Every Weaviate query applies the roles filter before any ranking:

```python
# weaviate_service.py
Filter.by_property("roles").contains_any(allowed_roles(user_roles))
```

`allowed_roles()` always appends `EVERYONE` to the user's role list, so publicly-tagged documents (roles=["EVERYONE"]) are visible to all users.

### `graph_rag` Tool — 8-Stage Pipeline

| Stage | Description |
|-------|-------------|
| 1 | Entity retrieval: concept embeddings → Weaviate TrustGraphEntities near_vector |
| 2 | BFS subgraph: seed URIs → knowledge-tree-service `/triples/neighbors` |
| 2.5 | LLM-guided expansion: planner model selects which node types to traverse |
| 3 | Label resolution: URIs → human labels (TTL cache, maxsize=2000) |
| 4 | Semantic pre-filter: embed edge descriptions → cosine vs. concept embeddings |
| 5 | LLM edge scoring: planner model + Langfuse `trustgraph_edge_scoring` prompt |
| 6 | Context formatting: markdown Entities + Relationships sections |
| 7 | Source provenance: `/triples/trace-sources` → `source_evidence` per edge |

---

## Part 5: Re-Ranking

### 5-Signal Formula

Applied in `_rerank_results()` in `smart_search.py` when `SMART_SEARCH_RERANK_ENABLED=true`.

| Signal | Default Weight | Source |
|--------|---------------|--------|
| `similarity` | 0.40 | Raw Weaviate hybrid score (normalized 0-1) |
| `quality` | 0.20 | `quality_score` from DocumentIntelligence |
| `graph` | 0.20 | Continuous score if doc in graph_rag expanded set; 1.0 binary if in entity match set; 0.0 otherwise |
| `recency` | 0.10 | Exponential decay: `exp(-0.693 * days_old / 90.0)` (half-life 90 days) |
| `entity` | 0.10 | Fraction of extracted query entities matching title + person + semantic_type + folder_path + content |

```python
composite = (
    w_sim * sim_score
    + w_qual * qual_score
    + w_graph * graph_score
    + w_rec * rec_score
    + w_ent * ent_score
)
```

Weights are configurable per-sector via `sector_config["rerank_weights"]`. The unified config returns the defaults above for all queries.

### Cross-Encoder Re-Rank (Optional)

A neural cross-encoder model (`SMART_SEARCH_CROSS_ENCODER_MODEL`) can be applied after the 5-signal pass. Controlled by `SMART_SEARCH_CROSS_ENCODER_ENABLED` (default: false). When enabled, the final ranking is a weighted blend of the heuristic and neural scores.

### RLM Relevance Threshold

Results scoring below `RAG_MIN_RELEVANCE_SCORE=0.55` are dropped at the context assembly stage to prevent feeding irrelevant context to the LLM.

---

## Part 6: Caching

### In-Process Embedding Cache (weaviate-service)

A module-level dict `_embed_cache` deduplicates concurrent embedding calls with a 5-second TTL (max 64 entries). This prevents redundant intelligence-docs-service HTTP calls when multiple chunks are embedded in rapid succession.

```python
_EMBED_CACHE_TTL = 5.0   # seconds
_EMBED_CACHE_MAX = 64
```

### Retrieval Cache (Redis, weaviate-service)

Vector search results (doc IDs + scores) are optionally cached in Redis:

| Config | Default |
|--------|---------|
| `RETRIEVAL_CACHE_ENABLED` | true |
| `RETRIEVAL_CACHE_TTL_SECONDS` | 300 (5 min) |
| `RETRIEVAL_CACHE_MAX_ENTRIES` | 500 |

### Semantic Cache (Redis, weaviate-service)

When `RAG_CACHE_ENABLED=true`, semantically similar queries (cosine similarity > `RAG_CACHE_SIMILARITY_THRESHOLD=0.92`) return cached results without hitting Weaviate:

| Config | Default |
|--------|---------|
| `RAG_CACHE_ENABLED` | true |
| `RAG_CACHE_SIMILARITY_THRESHOLD` | 0.92 |
| `RAG_CACHE_TTL_SECONDS` | 3600 (1 h) |
| `RAG_CACHE_MAX_ENTRIES` | 1000 |
| `RAG_CACHE_MIN_CONFIDENCE` | 0.65 |

### Context Assembly Cache (Redis, weaviate-service)

Context assembled for the LLM (chunked and ranked) is cached separately:

| Config | Default |
|--------|---------|
| `CONTEXT_CACHE_ENABLED` | true |
| `CONTEXT_CACHE_TTL_SECONDS` | 1800 (30 min) |
| `CONTEXT_CACHE_MAX_SIZE_MB` | 100 |

### RLM Processor Cache (Redis, emma-agent-service)

For large documents exceeding `RLM_THRESHOLD_TOKENS=50000`, the Recursive Language Model processor caches its chunked processing results in Redis under the key `rlm:result:{cache_key}` where `cache_key = sha256(query + content_hash)[:16]`. TTL: 3600 s. This prevents re-processing the same large document context for repeated similar queries.

### Graph Label Cache (In-Process, emma-agent-service)

The `graph_rag` tool keeps a `cachetools.TTLCache(maxsize=2000)` for entity URI → human label lookups from TrustGraph, avoiding repeated HTTP calls to knowledge-tree-service.

---

## Part 7: Configuration

All RAG-related env vars for weaviate-service (`app/core/config.py`):

| Variable | Default | Description |
|----------|---------|-------------|
| `RAG_MIN_RELEVANCE_SCORE` | 0.55 | Drop results below this score (prevents hallucinations) |
| `RAG_VALIDATION_SEMANTIC` | false | Enable semantic claim validation |
| `RAG_VALIDATION_THRESHOLD` | 0.7 | Semantic validation threshold |
| `RAG_SOFT_SELECTION_ENABLED` | true | Heuristic diversity-aware result selection |
| `RAG_SOFT_SELECTION_TEMPERATURE` | 0.5 | Selection temperature (lower = sharper) |
| `RAG_MMR_LAMBDA` | 0.7 | MMR formula: λ*relevance - (1-λ)*redundancy |
| `RAG_NUM_CLUSTERS` | 5 | Clusters for stratified selection |
| `RAG_MAX_DOCS` | 20 | Hard cap on documents per query |
| `RAG_MIN_WEIGHT` | 0.02 | Drop docs below 2% weight |
| `RAG_MIN_TOKENS_PER_DOC` | 200 | Minimum tokens before a doc is dropped |
| `RAG_CONTEXT_BUDGET_FRACTION` | 0.85 | Fraction of model max tokens reserved for context |
| `RAG_TRUNCATION_PRIORITY` | sections | Truncation order: sections / paragraphs / sentences |
| `CONTEXTUAL_RETRIEVAL_ENABLED` | true | Prepend document_type + entities to chunks before embedding |
| `CONTEXTUAL_RETRIEVAL_USE_LLM` | false | LLM-enhanced context prefix (adds indexing latency) |
| `CONTEXTUAL_RETRIEVAL_MAX_CONTEXT_LENGTH` | 300 | Max chars for context prefix |
| `PARENT_CHILD_CHUNKING_ENABLED` | false | Index small children, return large parents |
| `PARENT_CHUNK_SIZE` | 1500 | Parent chunk token size |
| `CHILD_CHUNK_SIZE` | 300 | Child chunk token size |
| `RAG_HIERARCHICAL_ENABLED` | true | Generate + index document summaries |
| `RAG_HIERARCHICAL_SUMMARY_WEIGHT` | 0.3 | Summary weight in RRF fusion |
| `RAG_KNOWLEDGE_GRAPH_ENABLED` | true | Send triples to knowledge-tree-service |
| `RAG_GRAPH_MAX_NEIGHBORS` | 10 | Max graph traversal neighbors |
| `RAG_GRAPH_TRAVERSAL_DEPTH` | 2 | BFS depth |
| `RAG_GRAPH_CACHE_TTL` | 3600 | Graph cache TTL (seconds) |
| `RLM_ENABLED` | true | Recursive LM processor for >50K token contexts |
| `RLM_THRESHOLD_TOKENS` | 50000 | Token threshold to activate RLM |
| `RLM_MAX_RECURSION_DEPTH` | 5 | Max RLM recursion |
| `RLM_CHUNK_SIZE_TOKENS` | 8000 | Sub-call size for RLM |
| `RAG_CHUNK_EXPANSION_ENABLED` | true | Include adjacent chunks |
| `RAG_CHUNK_EXPANSION_SIZE` | 1 | Chunks before/after to include |
| `ENHANCED_OCR_ENABLED` | true | OCR fallback for scanned docs |
| `ENHANCED_OCR_QUALITY_THRESHOLD` | 0.60 | Quality score below which OCR is triggered |
| `ENHANCED_OCR_LANGUAGES` | es,en | OCR language codes |
| `MULTIMODAL_EMBEDDING_ENABLED` | false | Visual content extraction for PDFs |
| `SMART_SEARCH_RERANK_ENABLED` | true | Enable 5-signal re-ranking |
| `SMART_SEARCH_GRAPH_ENABLED` | true | Enable TrustGraph expansion |
| `SMART_SEARCH_CROSS_ENCODER_ENABLED` | false | Neural cross-encoder re-rank |

---

## Part 8: Key Files

| File | Service | Purpose |
|------|---------|---------|
| `app/services/rag/indexing_pipeline.py` | weaviate-service | `IndexingPipeline`, `IndexingResult` — orchestrates all stages |
| `app/services/rag/document_intelligence.py` | weaviate-service | `DocumentIntelligence`, `DocumentAnalysis` — quality scoring |
| `app/services/rag/semantic_chunker.py` | weaviate-service | `SemanticChunker`, `DocumentChunk`, `DocumentType` |
| `app/services/rag/contextual_retrieval.py` | weaviate-service | `ContextualRetrievalService`, `ContextGenerationResult` |
| `app/services/rag/context_enricher.py` | weaviate-service | Per-chunk LLM context enrichment (Stage 4a) |
| `app/services/rag/hierarchical_indexer.py` | weaviate-service | `HierarchicalIndexer`, `DocumentSummary` |
| `app/services/rag/visual_extractor.py` | weaviate-service | `VisualContentExtractor` — multimodal PDF extraction |
| `app/services/weaviate_service.py` | weaviate-service | `WeaviateService.search_documents()` — hybrid_search, ACL |
| `app/core/config.py` | weaviate-service | All RAG env vars (`Settings`) |
| `app/pipeline/classifier.py` | intelligence-docs-service | `classify_document()`, `FILENAME_PATTERNS` |
| `app/agents/langgraph/tools/smart_search.py` | emma-agent-service | `SmartSearchTool`, `_rerank_results()` |
| `app/agents/langgraph/tools/graph_rag.py` | emma-agent-service | `GraphRagTool` — 8-stage TrustGraph pipeline |
| `app/agents/langgraph/nodes/rlm_processor.py` | emma-agent-service | RLM — recursive processing of large doc contexts |
| `app/services/knowledge/` | weaviate-service | `KnowledgeExtractionService` — triggers TrustGraph extraction |

---

## Part 9: Common Operations

### Reindex a Single Document

Use the weaviate-service API directly:

```bash
# Via main API (recommended — handles ACL + metadata propagation)
curl -X POST "http://localhost:8000/api/v1/documents/{document_id}/reindex" \
  -H "Authorization: Bearer $TOKEN"

# Or call weaviate-service directly (skips ACL validation)
curl -X POST "http://localhost:8007/index" \
  -H "X-API-Key: $MICROSERVICES_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"document_id": "...", "force": true}'
```

Reindexing deletes all existing chunks for the document (`_delete_document_chunks()`) before reinserting, so it is safe to run repeatedly.

### Tune Chunking for a New File Type

1. Add a new entry to `FILENAME_PATTERNS` in `intelligence-docs-service/app/pipeline/classifier.py`:
   ```python
   FILENAME_PATTERNS: list[tuple[str, str]] = [
       ...
       (r"poliza|policy", "poliza"),   # add here
   ]
   ```

2. Map the `document_type` string to a `DocumentType` enum value in `IndexingPipeline._detect_document_type()` in `indexing_pipeline.py`:
   ```python
   type_mapping = {
       ...
       "poliza": DocumentType.LEGAL_CONTRACT,   # or create a new enum value
   }
   ```

3. If the file type needs custom chunk parameters, add an `indexing_strategy` override to the connector configuration.

4. Reindex affected documents via the API.

### Debug Why a Query Did Not Find an Expected Document

1. **Check the document is indexed** — query Weaviate directly:
   ```bash
   curl "http://localhost:8007/collections/Nouxcube_documents/documents?document_id={id}" \
     -H "X-API-Key: $MICROSERVICES_API_KEY"
   ```

2. **Check ACL** — confirm the document's `roles` array includes either `EVERYONE` or a role the querying user holds. In PostgreSQL:
   ```sql
   SELECT id, title, roles FROM indexed_documents WHERE id = '<uuid>';
   ```

3. **Check relevance score** — if the document is indexed but not returned, its score may be below `RAG_MIN_RELEVANCE_SCORE=0.55`. Temporarily lower this in `.env` to verify:
   ```bash
   RAG_MIN_RELEVANCE_SCORE=0.0
   ```

4. **Check semantic_type filter** — if the query contains a keyword like "factura", the tool auto-applies `semantic_type_filter=factura`. If the document was indexed with `semantic_type=""`, it will be excluded. Verify the enrichment property:
   ```bash
   curl "http://localhost:8007/documents/{id}/metadata" -H "X-API-Key: $MICROSERVICES_API_KEY"
   ```

5. **Check retrieval quality** — the `assess_retrieval_quality()` guard may downgrade results. Enable debug logging in emma-agent-service:
   ```bash
   LOG_LEVEL=DEBUG  # in backend/docker/.env
   ```

6. **Verify embedding model consistency** — all chunks must be embedded with the same model. If `EMBEDDING_MODEL` was changed after initial indexing, re-index the corpus.
