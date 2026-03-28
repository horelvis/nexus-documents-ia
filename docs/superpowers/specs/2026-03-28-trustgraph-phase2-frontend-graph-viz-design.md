# TrustGraph Phase 2 Frontend — Graph Visualization

**Date**: 2026-03-28
**Status**: Approved
**Scope**: Adapt 3D/2D graph visualizations to `:Node`/`:Rel` TrustGraph model
**Depends on**: Phase 2 Backend (Graph RAG pipeline) — entity data and API endpoints must exist first

## 1. Objective

Adapt the existing Knowledge Graph 3D and Knowledge Tree 2D visualizations to render the TrustGraph `:Node`/`:Literal`/`:Rel` model. Users should see entities, their relationships, contradictions, and provenance — validated against the TrustGraph workbench-ui patterns.

### What changes

| Before | After |
|---|---|
| Node types from typed labels (`:Entity`, `:Document`) | Node types derived from `core/type` triple |
| Edge types from relationship label names | Edge labels from `Rel.uri` last segment (predicate name) |
| Static color scheme per label | Dynamic color by entity type (person, law, organization, etc.) |
| No contradiction display | Contradiction panel for selected entities |
| No provenance display | Source document + extraction method metadata |

## 2. Data Source

### API Endpoints (from Phase 2 Backend)

| Endpoint | Method | Returns |
|----------|--------|---------|
| `/triples/query` | POST | Triples matching SPO pattern |
| `/triples/stats` | GET | Node/literal/rel counts + type breakdown |
| `/triples/neighbors` | POST | BFS subgraph from seed entities (new in backend) |
| `/triples/context` | POST | LLM-ready text context with stats |

### Node Data Model (from FalkorDB)

```typescript
interface GraphNode {
  uri: string                    // "nouxcube://entity/default/lgt"
  type: string                   // From core/type triple: "law", "person", "organization"
  label: string                  // From core/label triple: "LGT"
  definition?: string            // From core/definition triple
  connectionCount: number        // Degree centrality
}
```

### Edge Data Model

```typescript
interface GraphEdge {
  source: string                 // Subject entity URI
  target: string                 // Object entity URI or literal value
  predicate: string              // Last segment of Rel.uri: "regulado-por", "empleado-de"
  predicateNamespace: string     // "core", "legal", "prov"
  extractionMethod?: string      // "llm_relationships", "system"
  sourceChunk?: string           // Provenance link
}
```

## 3. Components to Modify

### 3.1 Knowledge Graph 3D (`app/knowledge-graph/`)

**ExplainabilityGraph3D.tsx**
- Data fetching: call `/triples/neighbors` with selected entity as seed
- Node color: by `core/type` value (see color scheme below)
- Node size: proportional to `connectionCount`
- Edge labels: predicate name (last URI segment, humanized)
- Node tooltip: `label (type) — definition`
- Click handler: select node → load its triples in detail panel

**NodeDetailsDrawer.tsx** (new or adapted)
- Selected node's outgoing triples as table
- Contradiction panel: show conflicting values for same subject+predicate
- Provenance: source document + extraction method for each triple

### 3.2 Knowledge Tree 2D (`app/admin/knowledge-tree/`)

**ForceGraph.tsx**
- Same data model changes as 3D
- D3 force simulation parameters may need tuning for new graph density

**graph-theme.ts**
- `NodeKind` enum: derived from `core/type` triple value
- Color palette update for TrustGraph entity types

### 3.3 Color Scheme

Derived from existing `graph-theme.ts`, mapped to `core/type` values:

| Entity Type | Color | Hex |
|-------------|-------|-----|
| document | Blue | `#3b82f6` |
| person | Amber | `#f59e0b` |
| law / legislation | Cyan | `#06b6d4` |
| organization | Emerald | `#22c55e` |
| contract | Rose | `#f43f5e` |
| amount | Violet | `#a855f7` |
| date | Slate | `#64748b` |
| place | Orange | `#f97316` |
| topic | Teal | `#14b8a6` |
| other / unknown | Gray | `#6b7280` |

### 3.4 Edge Styles

By predicate namespace:

| Namespace | Style | Dash |
|-----------|-------|------|
| `core/` | Solid, 2px | — |
| `legal/` | Solid, 3px, color accent | — |
| `prov/` | Dotted, 1px, low opacity | `2,4` |
| contradiction | Red dashed, 2px | `4,4` |

### 3.5 Services

**knowledge-tree.service.ts** — Update to use new triple API endpoints:
- `getSubgraph(tenantId, entityUri, maxHops)` → POST `/triples/neighbors`
- `getEntityDetails(tenantId, entityUri)` → POST `/triples/query` with subject_uri
- `getStats(tenantId)` → GET `/triples/stats`

**explainability.service.ts** — Same updates for 3D view

## 4. New UI Features

### 4.1 Entity Search

Text input that searches `TrustGraphEntities` Weaviate collection by similarity. User types a concept → sees matching entities → clicks one → graph centers on it and expands neighbors.

### 4.2 Contradiction Panel

When selecting an entity with contradictions:
- Shows pairs of conflicting values (value_a vs value_b) for same predicate
- Links to source documents for each value
- Helps users identify data quality issues

### 4.3 Provenance Tooltip

Hovering over an edge shows:
- Extraction method (llm_relationships, llm_definitions, system)
- Source document name
- Extraction timestamp

## 5. File Impact

| File | Change |
|------|--------|
| `frontend/src/app/knowledge-graph/components/ExplainabilityGraph3D.tsx` | **MODIFY** — new data model |
| `frontend/src/app/knowledge-graph/components/NodeDetailsDrawer.tsx` | **NEW or MODIFY** — triples + contradictions |
| `frontend/src/app/admin/knowledge-tree/components/ForceGraph.tsx` | **MODIFY** — new data model |
| `frontend/src/app/admin/knowledge-tree/components/graph-theme.ts` | **MODIFY** — type-based colors |
| `frontend/src/lib/services/knowledge-tree.service.ts` | **MODIFY** — new API endpoints |
| `frontend/src/lib/services/explainability.service.ts` | **MODIFY** — new API endpoints |

## 6. Dependencies

- Phase 2 Backend must be complete (entity embeddings populated, `/triples/neighbors` endpoint live)
- TrustGraph workbench-ui reference: `https://github.com/trustgraph-ai/workbench-ui/tree/master/src/components`
