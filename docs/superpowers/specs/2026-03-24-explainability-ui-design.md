# Explainability UI + Graph Visualization — Design Spec

**Date**: 2026-03-24
**Status**: Draft
**Scope**: Frontend (Next.js) + 2 backend endpoints
**Inspired by**: TrustGraph Workbench UI (react-force-graph 3D, reasoning traces, entity explorer)

## Problem

Users have no visibility into HOW Emma arrived at each answer. The current `ReasoningCollapsible` shows a collapsed timeline of tool steps, but doesn't surface claims, evidence chains, source provenance, or contradictions. Users in legal/compliance contexts need to verify and trust AI responses.

## Goal

Two complementary views that make Emma's reasoning transparent:

1. **Knowledge Graph Page** (`/knowledge-graph`) — Full 3D graph explorer for the tenant's knowledge graph (entities, documents, claims, laws, contradictions)
2. **Reasoning Modal** (from chat) — Per-response split view showing the reasoning timeline + contextual evidence graph

## Success Criteria

- 3D graph renders with ≤100ms initial load for graphs up to 500 nodes
- Reasoning modal opens from any Emma response with reasoning steps
- Click any node → see properties, relationships, source text
- Contradictions visually highlighted (red pulse)
- Works without backend endpoints (client-side fallback from existing message data)
- Zero regressions in existing chat functionality

## Architecture

```
┌──────────────────────────────────────────────────────┐
│  View 1: /knowledge-graph (full page)                │
│  ┌────────────────────────────────────────────────┐  │
│  │  ExplainabilityGraph3D (ForceGraph3D)          │  │
│  │  + SearchBar (top-left floating)               │  │
│  │  + Legend (bottom-left floating)               │  │
│  │  + StatsBar (header)                           │  │
│  │  + NodeDetailsDrawer (Sheet from right)        │  │
│  └────────────────────────────────────────────────┘  │
│  Data: GET /emma/explainability/graph                 │
└──────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────┐
│  View 2: Reasoning Modal (fullscreen overlay)        │
│  ┌───────────────┬────────────────────────────────┐  │
│  │ Timeline (40%)│  EvidenceGraph (60%)            │  │
│  │ ┌───────────┐ │  ForceGraph3D (contextual)     │  │
│  │ │BÚSQUEDA   │ │  Only nodes from THIS response │  │
│  │ │OBSERVACIÓN│ │  Click → ClaimDetail popup     │  │
│  │ │RAZONAMIEN │ │                                │  │
│  │ │RESPUESTA  │ │                                │  │
│  │ └───────────┘ │                                │  │
│  └───────────────┴────────────────────────────────┘  │
│  Trigger: "Ver Razonamiento" button in MessageBubble │
│  Data: Client-side from EmmaMessage OR               │
│        GET /emma/explainability/trace/{thread}/{idx}  │
└──────────────────────────────────────────────────────┘
```

## New Dependencies

```json
{
  "react-force-graph": ">=1.47.0",
  "three-spritetext": "^1.9.3"
}
```

Note: `three` is a peer dependency of `react-force-graph` (~2MB). D3 force libs already installed.

## Design

### Color System

```typescript
// Node types
const NODE_COLORS = {
  entity:        '#06b6d4',  // Cyan
  document:      '#f59e0b',  // Amber
  claim:         '#22c55e',  // Green
  law:           '#a855f7',  // Purple
  contradiction: '#ef4444',  // Red (pulsing glow)
}

// Edge types
const EDGE_COLORS = {
  MENTIONED_IN:    '#64748b',  // Slate
  EXTRACTED_FROM:  '#3b82f6',  // Blue
  CONTRADICTS:     '#ef4444',  // Red (dashed)
  SUPPORTS:        '#22c55e',  // Green
  RELATED_TO:      '#94a3b8',  // Light slate
  REFERENCES:      '#8b5cf6',  // Violet
  MODIFIES:        '#f97316',  // Orange
  DEROGATES:       '#dc2626',  // Dark red
}

// Timeline badges
const BADGE_COLORS = {
  RAZONAMIENTO: '#a855f7',  // thinking, analyzing
  BÚSQUEDA:     '#3b82f6',  // searching, querying
  OBSERVACIÓN:  '#f59e0b',  // reading, doc_read
  ACCIÓN:       '#06b6d4',  // tool_call, tool_result
  RESPUESTA:    '#22c55e',  // final answer
  ERROR:        '#ef4444',  // errors
  SWARM:        '#8b5cf6',  // swarm workers
}
```

### Data Structures

#### Graph Response (full tenant graph)

```typescript
// GET /emma/explainability/graph?tenant_id=X
interface ExplainabilityGraphResponse {
  nodes: ExplainabilityNode[]
  edges: ExplainabilityEdge[]
  stats: {
    total_entities: number
    total_documents: number
    total_claims: number
    total_laws: number
    total_contradictions: number
  }
}

interface ExplainabilityNode {
  id: string
  type: 'entity' | 'document' | 'claim' | 'law' | 'contradiction'
  label: string
  properties: {
    domain?: string
    semantic_type?: string
    confidence?: number
    excerpt?: string
    boe_id?: string
    source_document_id?: string
    [key: string]: unknown
  }
}

interface ExplainabilityEdge {
  id: string
  source: string
  target: string
  type: string  // MENTIONED_IN, EXTRACTED_FROM, CONTRADICTS, etc.
  properties: {
    confidence?: number
    [key: string]: unknown
  }
}
```

#### Reasoning Trace (per-response)

```typescript
// GET /emma/explainability/trace/{thread_id}/{message_index}
interface ReasoningTraceResponse {
  message_id: string
  thread_id: string
  timeline: ReasoningTimelineStep[]
  evidence_graph: {
    nodes: ExplainabilityNode[]
    edges: ExplainabilityEdge[]
  }
  total_execution_ms: number
  tools_used: string[]
  sources_cited: number
}

interface ReasoningTimelineStep {
  index: number
  type: 'thinking' | 'search' | 'observation' | 'tool_call' | 'tool_result' | 'reflection' | 'answer' | 'error'
  content: string
  detail?: string
  source?: string
  timestamp_ms: number
  duration_ms?: number
  confidence?: number
  related_node_ids?: string[]
}
```

### Components

#### View 1: Knowledge Graph Page

| Component | Path | Props | Purpose |
|-----------|------|-------|---------|
| `page.tsx` | `app/knowledge-graph/page.tsx` | — | Page with SidebarProvider, data fetching, state |
| `ExplainabilityGraph3D` | `app/knowledge-graph/components/ExplainabilityGraph3D.tsx` | `nodes, links, highlightedIds, onNodeClick, focusNodeId` | ForceGraph3D with SpriteText labels, node colors, edge arrows |
| `NodeDetailsDrawer` | `app/knowledge-graph/components/NodeDetailsDrawer.tsx` | `node, edges, allNodes, onClose, onNavigate` | Sheet from right with properties + relationships tables |
| `ExplainabilitySearchBar` | `app/knowledge-graph/components/ExplainabilitySearchBar.tsx` | `nodes, onFilter` | Floating search panel, client-side filter |
| `ExplainabilityLegend` | `app/knowledge-graph/components/ExplainabilityLegend.tsx` | — | Color legend for 5 node types |
| `ExplainabilityStatsBar` | `app/knowledge-graph/components/ExplainabilityStatsBar.tsx` | `stats` | Node/edge counts |
| `explainability-theme.ts` | `app/knowledge-graph/components/explainability-theme.ts` | — | Types, colors, sizing functions |

#### View 2: Reasoning Modal

| Component | Path | Props | Purpose |
|-----------|------|-------|---------|
| `ReasoningModal` | `components/emma-chat/ReasoningModal.tsx` | `message, onClose` | Fullscreen overlay, split layout (40% timeline / 60% graph) |
| `ReasoningTimeline` | `components/emma-chat/ReasoningTimeline.tsx` | `steps, onStepHover, activeStepIndex` | Vertical timeline with TrustGraph-style badges |
| `ReasoningEvidenceGraph` | `components/emma-chat/ReasoningEvidenceGraph.tsx` | `nodes, links, highlightedNodeIds, onNodeClick` | Contextual ForceGraph3D (smaller, response-specific) |
| `ReasoningClaimDetail` | `components/emma-chat/ReasoningClaimDetail.tsx` | `node, onClose` | Floating popup: claim text, confidence bar, source doc |

#### Service Layer

| File | Path | Purpose |
|------|------|---------|
| `explainability.service.ts` | `lib/services/explainability.service.ts` | API client for 2 endpoints |

### Integration Points

1. **MessageBubble.tsx**: Add "Ver Razonamiento" button (IconRoute) to ActionBar. Visible when `rawReasoningSteps.length > 0`. Opens `ReasoningModal`.

2. **AppSidebar**: Add "Knowledge Graph" link (IconNetwork) next to existing "Knowledge Tree".

3. **next.config.ts**: Add proxy rewrite for `/api/emma/explainability/*` → emma-agent-service.

4. **Client-side fallback**: Evidence graph in ReasoningModal can be built from `EmmaMessage.metadata` (documents, sources, rawReasoningSteps) without the backend trace endpoint.

### 3D Graph Behavior

Following TrustGraph's `Graph.tsx` pattern:
- `ForceGraph3D` with `SpriteText` node labels
- `useResizeDetector` for responsive sizing
- Node click → `setSelectedNode` → opens NodeDetailsDrawer
- Background click → deselects
- Node drag → pin position (`node.fx/fy/fz`)
- Directional arrows on links (`linkDirectionalArrowLength={2.5}`)
- Link labels as SpriteText at midpoint
- Contradiction nodes: CSS `@keyframes pulse` on the glow filter
- Hover highlights connected subgraph (dim unconnected)
- Loaded via `next/dynamic` with `ssr: false` (Three.js cannot SSR)

### Timeline Badge Mapping

| Existing ReasoningStep type | New Badge | Color |
|---|---|---|
| `thinking`, `analyzing` | RAZONAMIENTO | Purple |
| `searching`, `querying`, `browsing`, `search_result` | BÚSQUEDA | Blue |
| `reading`, `doc_read`, `listing` | OBSERVACIÓN | Amber |
| `connecting`, `preparing`, tool_call, tool_result | ACCIÓN | Cyan |
| final answer / synthesis | RESPUESTA | Green |
| `error` | ERROR | Red |
| `swarm_*` | SWARM | Violet |

## Implementation Phases

| Phase | Components | Dependency |
|-------|-----------|------------|
| 1. Foundation | `explainability.service.ts`, `explainability-theme.ts` | None |
| 2. Knowledge Graph Page | `ExplainabilityGraph3D`, `NodeDetailsDrawer`, `SearchBar`, `Legend`, `StatsBar`, `page.tsx`, sidebar link | `npm install react-force-graph three-spritetext` |
| 3. Reasoning Modal | `ReasoningTimeline`, `ReasoningEvidenceGraph`, `ReasoningClaimDetail`, `ReasoningModal`, MessageBubble integration | Phase 2 (shares Graph3D) |
| 4. Backend Endpoints | `/emma/explainability/graph`, `/emma/explainability/trace` in emma-agent-service | FalkorDB data already exists |

Phase 3 works without Phase 4 (client-side fallback). Phase 4 enriches the data.

## Files Modified (existing)

| File | Change |
|------|--------|
| `components/emma-chat/messages/MessageBubble.tsx` | Add "Ver Razonamiento" button + ReasoningModal render |
| `components/layout/AppSidebar.tsx` | Add Knowledge Graph nav link |
| `next.config.ts` | Add proxy rewrite for explainability endpoints |
| `lib/config.ts` | Add API endpoint URLs |
| `package.json` | Add react-force-graph + three-spritetext |

## Files NOT Modified

| File | Reason |
|------|--------|
| `ReasoningCollapsible.tsx` | Kept as-is for inline chat view. Modal provides deep dive. |
| `FullscreenDocumentViewer.tsx` | Separate concern (document viewing, not reasoning) |
| `ForceGraph.tsx` (knowledge-tree) | Different graph, different purpose. Not refactored. |

## Backend Endpoints (Phase 4)

### GET /emma/explainability/graph

Source: FalkorDB via knowledge-tree-service.

```cypher
MATCH (n)
WHERE n.tenant_id = $tid
OPTIONAL MATCH (n)-[r]-(m)
WHERE m.tenant_id = $tid OR m.shared = true
RETURN n, r, m
LIMIT 500
```

Transform to `ExplainabilityGraphResponse` format. Classify nodes by labels (Entity, Document, Claim → type).

### GET /emma/explainability/trace/{thread_id}/{message_index}

Source: ReActState from checkpointer (AsyncPostgresSaver) + reasoning_steps from graph execution.

Reads the checkpointed state for the given thread/message, extracts `reasoning_steps`, `sources`, `tool_calls_history`, and constructs the timeline + evidence graph.

## Risks

1. **Three.js bundle size** (~2MB) — mitigated by dynamic import with `ssr: false`
2. **Large graphs** (>500 nodes) — LIMIT on API, client-side filtering
3. **Checkpointer data availability** — trace endpoint requires checkpointer enabled (default: true)
4. **SSE reasoning steps format** — may need normalization for timeline display

## Out of Scope

- Chunk nodes / provenance DAG (separate sub-project)
- Reasoning persistence to FalkorDB (separate sub-project, currently in-memory only)
- Graph editing / annotation
- Export / share reasoning traces
