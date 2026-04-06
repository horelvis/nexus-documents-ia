# TrustGraph Phase 2 Frontend — Graph Visualization & Chat Integration

**Date**: 2026-03-28 (v2)
**Status**: Approved
**Scope**: Adapt graph visualizations + chat message types to TrustGraph model
**Depends on**: Phase 2 Backend (Graph RAG pipeline, `/triples/neighbors` endpoint)
**Reference**: TrustGraph workbench-ui `/tmp/trustgraph-ui/src/components/`

## 1. Objective

Adapt the existing Knowledge Graph 3D, Knowledge Tree 2D, and Emma Chat to the TrustGraph `:Node`/`:Rel` model. Validated against TrustGraph workbench-ui patterns — adopt their proven approaches while keeping our stronger UI foundation (shadcn/ui, Next.js App Router, existing dark theme).

### What changes

| Before | After |
|---|---|
| Node types from typed labels (`:Entity`, `:Document`) | Node types derived from `core/type` triple value |
| Edge labels from relationship label names | Edge labels from `Rel.uri` last segment (predicate name) |
| Static color scheme per label | Dynamic color by entity type with dark/light mode |
| No contradiction display | Contradiction panel in node details drawer |
| No provenance display | Source document + extraction method in edge tooltips |
| Chat shows flat text responses | Chat distinguishes thinking/observation/answer message types |
| No entity↔graph navigation from chat | Entity tags in chat responses → click to explore in graph |

## 2. TrustGraph Workbench-UI Patterns Adopted

| Pattern | TrustGraph Implementation | Our Adaptation |
|---------|--------------------------|----------------|
| 3D Force Graph | `react-force-graph` + Three.js sprites | Keep existing `react-force-graph-3d` (already using it) |
| Node details drawer | Chakra Drawer, right-side, shows relationships + properties | shadcn Sheet, right-side, same content |
| Message type badges | thinking (Brain) / observation (Eye) / answer (Check) | Same 3 types, mapped to our SSE event types |
| Entity-first navigation | Entity tags in chat → click → graph/entity view | Entity tags below Emma responses → click → graph panel |
| Theme-aware colors | Custom hooks with `useColorModeValue` | CSS variables in `graph-theme.ts` (already have dark mode) |
| Subgraph building | Filter literals from graph, show as properties in drawer | Same — only Node→Node edges in force graph |
| Relationship navigation | Click relationship → follow edge → expand subgraph | Same — click edge → query neighbors → expand |
| Lazy loading | React.lazy() for heavy graph pages | Next.js dynamic imports (already doing this) |

### Patterns NOT adopted (we have better)

| TrustGraph | Why we skip | Our approach |
|---|---|---|
| Chakra UI | We use shadcn/ui + Tailwind (richer, more customizable) | Keep shadcn |
| Zustand state | We use React Context + service layer | Keep existing pattern |
| react-markdown-it | We use custom EmmaMarkdown with SSE streaming | Keep EmmaMarkdown |
| No citation panels | They don't show provenance in chat | We ADD provenance (new feature) |

## 3. Data Model

### API Endpoints (from Phase 2 Backend)

| Endpoint | Method | Returns | Used by |
|----------|--------|---------|---------|
| `/triples/neighbors` | POST | BFS subgraph from seed entities | Graph 3D/2D |
| `/triples/query` | POST | Triples matching SPO pattern | Node details drawer |
| `/triples/stats` | GET | Node/literal/rel counts + type breakdown | Graph stats panel |
| `/weaviate/entities/search` | POST | Entity similarity search | Entity search bar |

### TypeScript Interfaces

```typescript
// Graph node for visualization (Node→Node edges only)
interface GraphNode {
  id: string              // entity URI
  label: string           // from core/label triple
  type: string            // from core/type triple: "law", "person", "organization"
  definition?: string     // from core/definition triple
  connectionCount: number // degree centrality
}

// Graph edge for visualization
interface GraphEdge {
  id: string              // hash of s+p+o (TrustGraph pattern)
  source: string          // subject entity URI
  target: string          // object entity URI
  predicate: string       // last segment of Rel.uri: "regulado-por"
  namespace: string       // "core", "legal"
  weight: number          // 1.0 default, or edge score from Graph RAG
}

// Property (Node→Literal edges, shown in drawer not graph)
interface EntityProperty {
  predicate: string       // "salario-bruto", "vigente-desde"
  namespace: string       // "legal", "core"
  value: string           // literal value
  extractionMethod: string
  sourceDocument?: string
}

// Contradiction (same subject+predicate, different values)
interface Contradiction {
  subject: string
  predicate: string
  valueA: string
  valueB: string
  sourceA?: string        // source document for value A
  sourceB?: string        // source document for value B
}
```

## 4. Components

### 4.1 Knowledge Graph 3D (`app/knowledge-graph/`)

**ExplainabilityGraph3D.tsx** — Modify

Changes:
- Data fetch: POST `/triples/neighbors` with `{seed_uris, max_hops: 2, max_edges: 150}`
- Transform response: split Node→Node edges (graph) from Node→Literal edges (properties)
- Node color: by `type` field (see color scheme §5)
- Node size: `8 + Math.log(connectionCount + 1) * 4`
- Edge labels: predicate name as 3D sprite text (already using `three-spritetext`)
- Node tooltip: `"{label} ({type})"` — definition on hover
- Click node: open NodeDetailsDrawer + set as selected entity
- Click edge: emit particles (TrustGraph pattern — visual flow animation)
- Background click: deselect

**Subgraph building** (adopted from TrustGraph `knowledge-graph-viz.ts`):
```typescript
function buildGraphData(triples: Triple[]): { nodes: GraphNode[], edges: GraphEdge[] } {
  const nodeMap = new Map<string, GraphNode>()
  const edges: GraphEdge[] = []

  for (const triple of triples) {
    // Only Node→Node edges go into the force graph
    if (triple.object_type === "literal") continue

    // Deduplicate nodes
    if (!nodeMap.has(triple.subject)) {
      nodeMap.set(triple.subject, { id: triple.subject, label: "...", type: "other", connectionCount: 0 })
    }
    if (!nodeMap.has(triple.object)) {
      nodeMap.set(triple.object, { id: triple.object, label: "...", type: "other", connectionCount: 0 })
    }

    // Count connections
    nodeMap.get(triple.subject)!.connectionCount++
    nodeMap.get(triple.object)!.connectionCount++

    // Edge with dedup key (TrustGraph pattern)
    const edgeId = `${triple.subject}@@${triple.predicate}@@${triple.object}`
    edges.push({
      id: edgeId,
      source: triple.subject,
      target: triple.object,
      predicate: triple.predicate.split("/").pop() ?? triple.predicate,
      namespace: triple.predicate.split("/").slice(-2, -1)[0] ?? "core",
      weight: 1.0,
    })
  }

  return { nodes: Array.from(nodeMap.values()), edges }
}
```

**NodeDetailsDrawer.tsx** — New component (shadcn Sheet)

Right-side drawer opened on node selection. Three tabs:

| Tab | Content |
|-----|---------|
| **Relationships** | Table of outgoing + incoming Node→Node edges. Each row clickable → navigates to that entity (expands subgraph). Columns: direction (→/←), predicate, target entity, extraction method |
| **Properties** | Table of Node→Literal edges. Columns: predicate, value, extraction method, source document |
| **Contradictions** | Pairs of conflicting values for same predicate. Columns: predicate, value A, value B, source A, source B. Highlighted in red/amber |

### 4.2 Knowledge Tree 2D (`app/admin/knowledge-tree/`)

**ForceGraph.tsx** — Modify

Same data model changes as 3D. D3 force simulation tuning:
- `forceLink.distance`: 80 → 60 (denser graph with more entities)
- `forceManyBody.strength`: -300 → -200 (less repulsion, more compact)
- `forceCollide.radius`: 30 (prevent overlap)

**graph-theme.ts** — Modify

Replace `NodeKind` enum with dynamic type-based colors (§5). Keep existing edge style definitions, map to predicate namespace instead of relationship label.

### 4.3 Emma Chat Integration (`components/emma-chat/`)

**Message type badges** (adopted from TrustGraph ChatMessage pattern):

Map our existing SSE event types to visual badges:

| SSE Event | Badge | Icon | Color | When |
|-----------|-------|------|-------|------|
| `agent_reasoning` | Pensando | Brain | `blue-500` | ReAct agent reasoning steps |
| `tool_call` / `tool_result` | Observando | Eye | `amber-500` | Tool execution (smart_search, graph_rag) |
| `final_answer` | Respuesta | CheckCircle | `emerald-500` | Final synthesized answer |
| `claim_*` | Verificando | Shield | `violet-500` | Verified Generation claims |

Implementation: in `useMessageConverter.ts`, map SSE events to message parts with `type` metadata. In `EmmaMarkdown.tsx`, render badge + icon before content.

**Entity tags in responses** (adopted from TrustGraph EntityList):

After Graph RAG responses, show extracted entities as clickable tags below the message:

```tsx
<div className="flex flex-wrap gap-1.5 mt-2">
  {entities.map(entity => (
    <button
      key={entity.uri}
      onClick={() => navigateToGraph(entity.uri)}
      className="px-2 py-0.5 rounded-full text-xs bg-cyan-500/10 text-cyan-400
                 hover:bg-cyan-500/20 border border-cyan-500/20"
    >
      {entity.label}
    </button>
  ))}
</div>
```

Clicking an entity tag navigates to the Knowledge Graph view centered on that entity.

### 4.4 Entity Search Bar (NEW)

**Location**: Shared component used in both graph views

Text input with debounced search (300ms) against Weaviate `TrustGraphEntities` collection:

```
POST /weaviate/entities/search
{
  "query": "ley general tributaria",
  "tenant_id": "...",
  "limit": 10
}
```

Returns matching entities with similarity scores. User selects one → graph centers on it, loads neighbors via BFS.

Rendered as a combobox (shadcn Command) above the graph canvas.

## 5. Color Scheme

Derived from existing `graph-theme.ts`, mapped to `core/type` triple values. Both light and dark mode via CSS variables.

| Entity Type | Dark Mode | Light Mode | Tailwind |
|-------------|-----------|------------|----------|
| document | `#3b82f6` | `#2563eb` | `blue-500`/`blue-600` |
| person | `#f59e0b` | `#d97706` | `amber-500`/`amber-600` |
| law | `#06b6d4` | `#0891b2` | `cyan-500`/`cyan-600` |
| organization | `#22c55e` | `#16a34a` | `green-500`/`green-600` |
| contract | `#f43f5e` | `#e11d48` | `rose-500`/`rose-600` |
| amount | `#a855f7` | `#9333ea` | `purple-500`/`purple-600` |
| date | `#64748b` | `#475569` | `slate-500`/`slate-600` |
| place | `#f97316` | `#ea580c` | `orange-500`/`orange-600` |
| topic | `#14b8a6` | `#0d9488` | `teal-500`/`teal-600` |
| other | `#6b7280` | `#4b5563` | `gray-500`/`gray-600` |

Dynamic lookup function:
```typescript
const TYPE_COLORS: Record<string, string> = {
  document: "blue", person: "amber", law: "cyan", organization: "green",
  contract: "rose", amount: "purple", date: "slate", place: "orange",
  topic: "teal",
}

function getNodeColor(type: string): string {
  return TYPE_COLORS[type] ?? "gray"
}
```

## 6. Edge Styles

| Namespace | Stroke | Width | Dash | Opacity |
|-----------|--------|-------|------|---------|
| `core/` | `slate-400` | 1.5px | solid | 0.6 |
| `legal/` | `cyan-400` | 2.5px | solid | 0.8 |
| `prov/` | `slate-600` | 1px | `2,4` | 0.3 |
| contradiction | `rose-500` | 2px | `4,4` | 0.9 |

## 7. Services Layer

### knowledge-tree.service.ts — Modify

```typescript
// NEW: BFS subgraph for graph visualization
async getSubgraph(tenantId: string, seedUris: string[], maxHops?: number): Promise<SubgraphResponse>

// NEW: Entity details (all triples for a node)
async getEntityTriples(tenantId: string, entityUri: string): Promise<TripleQueryResponse>

// EXISTING (update): Stats with type breakdown
async getStats(tenantId: string): Promise<StatsResponse>
```

### entity-search.service.ts — New

```typescript
// Search entities by similarity via Weaviate TrustGraphEntities
async searchEntities(tenantId: string, query: string, limit?: number): Promise<EntityMatch[]>
```

### explainability.service.ts — Modify

Same updates as knowledge-tree.service.ts for the 3D view.

## 8. File Impact

| File | Change | Est. Lines |
|------|--------|-----------|
| `app/knowledge-graph/components/ExplainabilityGraph3D.tsx` | **MODIFY** — new data model, node/edge rendering | ~80 |
| `app/knowledge-graph/components/NodeDetailsDrawer.tsx` | **NEW** — triples table, contradictions, provenance | ~200 |
| `app/admin/knowledge-tree/components/ForceGraph.tsx` | **MODIFY** — new data model | ~60 |
| `app/admin/knowledge-tree/components/graph-theme.ts` | **MODIFY** — type-based colors, namespace edge styles | ~40 |
| `components/emma-chat/EmmaMarkdown.tsx` | **MODIFY** — message type badges | ~30 |
| `components/emma-chat/hooks/useMessageConverter.ts` | **MODIFY** — entity tag extraction | ~20 |
| `components/emma-chat/EntityTags.tsx` | **NEW** — clickable entity tags below responses | ~40 |
| `components/graph/EntitySearchBar.tsx` | **NEW** — similarity search combobox | ~60 |
| `lib/services/knowledge-tree.service.ts` | **MODIFY** — new triple API endpoints | ~30 |
| `lib/services/entity-search.service.ts` | **NEW** — Weaviate entity search | ~25 |
| `lib/services/explainability.service.ts` | **MODIFY** — new endpoints | ~20 |
| **Total** | | **~605 lines** |

## 9. Dependencies

- Phase 2 Backend complete: `/triples/neighbors`, `/weaviate/entities/search` endpoints live
- Entity embeddings populated in Weaviate `TrustGraphEntities` collection
- Graph populated with Phase 1 extraction data (955+ entities)
- No new npm packages needed (`react-force-graph-3d`, `three-spritetext`, `d3` already installed)
