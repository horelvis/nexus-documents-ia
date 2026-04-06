# TrustGraph Phase 3b — Document Provenance Tracing

**Date**: 2026-03-30
**Status**: Draft
**Depends on**: Phase 3a (confidence scoring — complete)
**Branch**: `feat/trustgraph-phase2`

## Problem Statement

When Emma answers questions using graph knowledge, the user has no way to verify WHERE a fact came from. Phase 3a added inline `[fuente: doc#chunk]` citations in the LLM context, but:

1. The LLM sees document IDs and chunk offsets — not the actual text
2. The user never sees the source evidence directly
3. There's no way to click through to the original document passage

## Design

### 1. Provenance Resolver in KTS

New endpoint `POST /triples/trace-sources` in knowledge-tree-service.

**Input**: List of edges to trace (from graph_rag scored results).

```json
{
  "edges": [
    {"subject_uri": "nouxcube://entity/...", "predicate_uri": "nouxcube://predicate/...", "object_uri": "nouxcube://entity/..."}
  ],
  "tenant_id": "00000000-..."
}
```

**Logic**:
1. For each edge, query FalkorDB for the `:Rel` edge's `source_chunk` property
2. Parse `source_chunk` URI: `nouxcube://document/{collection}/{doc_id}#offset={n}` → extract `doc_id` and `chunk_offset`
3. Batch-fetch chunk texts from weaviate-service: `GET /weaviate/documents/{tenant_id}/{doc_id}/chunks?offset={n}&limit=1`
4. Batch-resolve document titles from FalkorDB: query `core/label` literal for each document URI

**Output**:
```json
{
  "sources": [
    {
      "subject_uri": "nouxcube://entity/default/juan-garcia",
      "predicate_uri": "nouxcube://predicate/legal/empleado-de",
      "object_uri": "nouxcube://entity/default/empresa-abc",
      "document_id": "1103ac54-...",
      "document_title": "Contrato de Trabajo 2025",
      "chunk_offset": 3,
      "chunk_text": "Juan García, con DNI 12345678A, presta sus servicios como desarrollador senior en Empresa ABC S.L. desde el 1 de enero de 2025...",
      "confidence": 0.90
    }
  ]
}
```

Chunk text truncated to 300 chars. Only traces edges that have a `source_chunk` property.

### 2. graph_rag Source Resolution

After Stage 6 (context formatting), graph_rag calls the provenance resolver for the top scored edges (up to `graph_rag_edge_limit`, default 25). The resolved sources are:

1. **Appended to context text** (for LLM): A "Fuentes" section at the end with chunk excerpts
2. **Added to ToolResult.data**: New `"source_evidence"` field with the full source list

Context text enrichment:
```markdown
## Knowledge Graph Context

### Entities
[...]

### Relationships
[...]

### Fuentes
- "Juan García empleado-de Empresa ABC" — Contrato de Trabajo 2025 (chunk 3): "Juan García, con DNI 12345678A, presta sus servicios como..."
- "Contrato vigente-desde 2025-01-01" — Contrato de Trabajo 2025 (chunk 1): "El presente contrato entrará en vigor el día 1 de enero..."
```

### 3. SSE Event `source_evidence`

In the `react_loop` node, after processing graph_rag tool result, if `source_evidence` is present in the tool data, emit an SSE event:

```json
{
  "event": "source_evidence",
  "data": {
    "tool": "graph_rag",
    "sources": [
      {
        "document_id": "1103ac54-...",
        "document_title": "Contrato de Trabajo 2025",
        "chunk_offset": 3,
        "chunk_text": "Juan García, con DNI 12345678A...",
        "relationship": "Juan García empleado-de Empresa ABC",
        "confidence": 0.90
      }
    ]
  }
}
```

### 4. Frontend — SourceEvidence Component

New `SourceEvidence.tsx` component rendered below the message bubble when `source_evidence` SSE events are received.

**UI**:
- Collapsable section titled "Fuentes consultadas" (collapsed by default)
- Each source shows:
  - Document name (as a clickable link → navigates to document viewer)
  - Relationship it supports (small text)
  - Chunk excerpt (truncated, expandible on click)
  - Confidence badge: green (>0.8), yellow (0.5-0.8), red (<0.5)

**Integration**: `MessageBubble.tsx` checks if the message has associated `source_evidence` data (stored alongside the message in state) and renders `<SourceEvidence sources={...} />` below the message text.

## Files Changed

| File | Service | Change | Lines |
|------|---------|--------|-------|
| `KTS/app/api/triples.py` | KTS | `POST /triples/trace-sources` endpoint | ~30 |
| `KTS/app/services/triple_query.py` | KTS | `trace_sources()` method | ~40 |
| `Emma/app/clients/knowledge_tree_client.py` | Emma | `trace_sources()` client method | ~15 |
| `Emma/app/agents/langgraph/tools/graph_rag.py` | Emma | Resolve sources after Stage 6, add to ToolResult | ~30 |
| `Emma/app/agents/langgraph/nodes/react_loop.py` | Emma | Emit `source_evidence` SSE event | ~10 |
| `frontend/src/components/emma-chat/SourceEvidence.tsx` | Frontend | New component | ~80 |
| `frontend/src/components/emma-chat/MessageBubble.tsx` | Frontend | Render SourceEvidence | ~10 |

**Total**: ~215 lines across 7 files.

## Configuration

No new config settings needed. Uses existing `graph_rag_edge_limit` to determine how many edges to trace.

## Validation Plan

1. **KTS endpoint test**: POST to `/triples/trace-sources` with known edges → verify chunk text returned
2. **graph_rag integration**: Query "relaciones de Juan García" → verify context text includes "Fuentes" section with chunk excerpts
3. **SSE event**: Verify `source_evidence` event emitted in stream response
4. **Frontend**: Verify "Fuentes consultadas" panel appears, collapses/expands, document links work

## Out of Scope

- Entity profiles / dossiers (Phase 3c candidate)
- Source evidence for SmartSearch results (only graph_rag for now)
- Source evidence caching (edges rarely change, but chunk fetch is fast enough)
- Highlighting the exact span within the chunk that produced the triple
