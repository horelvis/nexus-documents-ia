# Explainability UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 3D knowledge graph page + per-response reasoning modal to surface HOW and WHY Emma arrived at each answer.

**Architecture:** Two views — full Knowledge Graph page at `/knowledge-graph` with ForceGraph3D (react-force-graph) and per-response Reasoning Modal with split timeline/graph. Both share the ExplainabilityGraph3D component. Client-side evidence graph fallback enables frontend before backend endpoints exist.

**Tech Stack:** Next.js 15, TypeScript, Tailwind CSS, react-force-graph, three-spritetext, Radix UI Sheet, Tabler Icons

**Spec:** `docs/superpowers/specs/2026-03-24-explainability-ui-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `frontend/src/lib/services/explainability.service.ts` | Create | API client + TypeScript types |
| `frontend/src/app/knowledge-graph/components/explainability-theme.ts` | Create | Colors, node/link types, sizing |
| `frontend/src/app/knowledge-graph/components/ExplainabilityGraph3D.tsx` | Create | ForceGraph3D wrapper (3D graph) |
| `frontend/src/app/knowledge-graph/components/NodeDetailsDrawer.tsx` | Create | Sheet with properties + relationships |
| `frontend/src/app/knowledge-graph/components/ExplainabilitySearchBar.tsx` | Create | Floating search/filter |
| `frontend/src/app/knowledge-graph/components/ExplainabilityLegend.tsx` | Create | Color legend |
| `frontend/src/app/knowledge-graph/components/ExplainabilityStatsBar.tsx` | Create | Node/edge counts |
| `frontend/src/app/knowledge-graph/page.tsx` | Create | Knowledge Graph page |
| `frontend/src/components/emma-chat/ReasoningTimeline.tsx` | Create | TrustGraph-style badge timeline |
| `frontend/src/components/emma-chat/ReasoningEvidenceGraph.tsx` | Create | Contextual 3D graph for response |
| `frontend/src/components/emma-chat/ReasoningClaimDetail.tsx` | Create | Floating claim detail popup |
| `frontend/src/components/emma-chat/ReasoningModal.tsx` | Create | Fullscreen overlay orchestrator |
| `frontend/src/lib/config.ts` | Modify | Add endpoint URLs |
| `frontend/src/components/layout/app-sidebar.tsx` | Modify | Add Knowledge Graph nav link |
| `frontend/src/components/emma-chat/messages/MessageBubble.tsx` | Modify | Add "Ver Razonamiento" button |
| `frontend/package.json` | Modify | Add react-force-graph + three-spritetext |

---

### Task 1: Install Dependencies + Foundation Types

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/src/lib/services/explainability.service.ts`
- Create: `frontend/src/app/knowledge-graph/components/explainability-theme.ts`
- Modify: `frontend/src/lib/config.ts`

- [ ] **Step 1: Install react-force-graph and three-spritetext**

```bash
cd frontend && npm install react-force-graph three-spritetext three
```

Note: `three` is a peer dependency of react-force-graph.

- [ ] **Step 2: Add endpoint URLs to config.ts**

In `frontend/src/lib/config.ts`, add to the `ENDPOINTS` object:

```typescript
// Explainability
EXPLAINABILITY_GRAPH: '/emma/explainability/graph',
EXPLAINABILITY_TRACE: (threadId: string, messageIndex: number) =>
  `/emma/explainability/trace/${threadId}/${messageIndex}`,
```

- [ ] **Step 3: Create explainability-theme.ts**

```typescript
// frontend/src/app/knowledge-graph/components/explainability-theme.ts

export type ExplainNodeType = 'entity' | 'document' | 'claim' | 'law' | 'contradiction'

export interface ExplainNode {
  id: string
  type: ExplainNodeType
  label: string
  properties: Record<string, unknown>
  // react-force-graph fields (populated at runtime)
  x?: number
  y?: number
  z?: number
  fx?: number
  fy?: number
  fz?: number
}

export interface ExplainLink {
  id: string
  source: string | ExplainNode
  target: string | ExplainNode
  type: string
  properties: Record<string, unknown>
}

export const NODE_COLORS: Record<ExplainNodeType, string> = {
  entity:        '#06b6d4',
  document:      '#f59e0b',
  claim:         '#22c55e',
  law:           '#a855f7',
  contradiction: '#ef4444',
}

export const NODE_GLOW: Record<ExplainNodeType, string> = {
  entity:        '#22d3ee',
  document:      '#fbbf24',
  claim:         '#4ade80',
  law:           '#c084fc',
  contradiction: '#f87171',
}

export const EDGE_COLORS: Record<string, string> = {
  MENTIONED_IN:    '#64748b',
  EXTRACTED_FROM:  '#3b82f6',
  CONTRADICTS:     '#ef4444',
  SUPPORTS:        '#22c55e',
  RELATED_TO:      '#94a3b8',
  REFERENCES:      '#8b5cf6',
  MODIFIES:        '#f97316',
  DEROGATES:       '#dc2626',
}

export const NODE_SIZE: Record<ExplainNodeType, number> = {
  entity:        6,
  document:      8,
  claim:         4,
  law:           10,
  contradiction: 5,
}

export function getNodeColor(node: ExplainNode): string {
  return NODE_COLORS[node.type] || '#94a3b8'
}

export function getEdgeColor(link: ExplainLink): string {
  return EDGE_COLORS[link.type] || '#64748b'
}

export function getNodeSize(node: ExplainNode): number {
  return NODE_SIZE[node.type] || 6
}
```

- [ ] **Step 4: Create explainability.service.ts**

```typescript
// frontend/src/lib/services/explainability.service.ts

import { API_CONFIG } from '@/lib/config'
import { apiClient } from '@/lib/api-client'

// --- Types ---

export interface ExplainabilityNode {
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

export interface ExplainabilityEdge {
  id: string
  source: string
  target: string
  type: string
  properties: {
    confidence?: number
    [key: string]: unknown
  }
}

export interface ExplainabilityGraphResponse {
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

export interface ReasoningTimelineStep {
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

export interface ReasoningTraceResponse {
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

// --- API Client ---

export const explainabilityService = {
  async getGraph(tenantId: string): Promise<ExplainabilityGraphResponse> {
    const response = await apiClient.get(
      `${API_CONFIG.ENDPOINTS.EXPLAINABILITY_GRAPH}?tenant_id=${tenantId}`
    )
    return response.data
  },

  async getTrace(threadId: string, messageIndex: number): Promise<ReasoningTraceResponse> {
    const url = typeof API_CONFIG.ENDPOINTS.EXPLAINABILITY_TRACE === 'function'
      ? API_CONFIG.ENDPOINTS.EXPLAINABILITY_TRACE(threadId, messageIndex)
      : `${API_CONFIG.ENDPOINTS.EXPLAINABILITY_TRACE}/${threadId}/${messageIndex}`
    const response = await apiClient.get(url)
    return response.data
  },
}
```

- [ ] **Step 5: Verify build**

```bash
cd frontend && npm run build 2>&1 | tail -10
```

Expected: Build succeeds (no type errors from new files).

- [ ] **Step 6: Commit**

```bash
cd frontend
git add package.json package-lock.json src/lib/config.ts \
  src/lib/services/explainability.service.ts \
  src/app/knowledge-graph/components/explainability-theme.ts
git commit -m "feat(frontend): add explainability types, service, and theme

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: ExplainabilityGraph3D Component

**Files:**
- Create: `frontend/src/app/knowledge-graph/components/ExplainabilityGraph3D.tsx`

- [ ] **Step 1: Create the 3D graph component**

This is the core visualization. Follow TrustGraph's `Graph.tsx` pattern adapted to our stack.

```typescript
// frontend/src/app/knowledge-graph/components/ExplainabilityGraph3D.tsx
'use client'

import { useRef, useState, useEffect, useCallback } from 'react'
import dynamic from 'next/dynamic'
import SpriteText from 'three-spritetext'
import { ExplainNode, ExplainLink, getNodeColor, getEdgeColor, getNodeSize } from './explainability-theme'

// ForceGraph3D cannot SSR (Three.js needs DOM)
const ForceGraph3D = dynamic(() => import('react-force-graph').then(m => m.ForceGraph3D), {
  ssr: false,
  loading: () => <div className="flex items-center justify-center h-full text-muted-foreground">Cargando grafo 3D...</div>,
})

interface ExplainabilityGraph3DProps {
  nodes: ExplainNode[]
  links: ExplainLink[]
  highlightedIds?: Set<string> | null
  onNodeClick?: (node: ExplainNode) => void
  focusNodeId?: string | null
  className?: string
  width?: number
  height?: number
}

export default function ExplainabilityGraph3D({
  nodes,
  links,
  highlightedIds,
  onNodeClick,
  focusNodeId,
  className = '',
  width,
  height,
}: ExplainabilityGraph3DProps) {
  const fgRef = useRef<any>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [dimensions, setDimensions] = useState({ w: width || 800, h: height || 600 })

  // Resize observer
  useEffect(() => {
    if (width && height) {
      setDimensions({ w: width, h: height })
      return
    }
    if (!containerRef.current) return
    const ro = new ResizeObserver(entries => {
      const { width: w, height: h } = entries[0].contentRect
      if (w > 0 && h > 0) setDimensions({ w, h })
    })
    ro.observe(containerRef.current)
    return () => ro.disconnect()
  }, [width, height])

  // Auto-focus on node
  useEffect(() => {
    if (focusNodeId && fgRef.current) {
      const node = nodes.find(n => n.id === focusNodeId)
      if (node && node.x !== undefined) {
        fgRef.current.cameraPosition(
          { x: node.x, y: node.y, z: (node.z || 0) + 120 },
          { x: node.x, y: node.y, z: node.z || 0 },
          1000
        )
      }
    }
  }, [focusNodeId, nodes])

  const handleNodeClick = useCallback((node: any) => {
    setSelectedId(node.id)
    onNodeClick?.(node as ExplainNode)
  }, [onNodeClick])

  const handleBgClick = useCallback(() => {
    setSelectedId(null)
  }, [])

  const wrap = (s: string, w: number) =>
    s.replace(new RegExp(`(?![^\\n]{1,${w}}$)([^\\n]{1,${w}})\\s`, 'g'), '$1\n')

  const graphData = { nodes, links }

  return (
    <div ref={containerRef} className={`relative w-full h-full ${className}`}>
      <ForceGraph3D
        ref={fgRef}
        width={dimensions.w}
        height={dimensions.h}
        graphData={graphData}
        nodeOpacity={0.85}
        nodeLabel="label"
        enableNodeDrag={true}
        nodeColor={(node: any) => {
          if (highlightedIds && !highlightedIds.has(node.id)) return '#1e293b'
          return getNodeColor(node as ExplainNode)
        }}
        nodeVal={(node: any) => getNodeSize(node as ExplainNode)}
        backgroundColor="#07090f"
        nodeThreeObject={(node: any) => {
          const sprite = new SpriteText(wrap(node.label || '', 25))
          sprite.color = selectedId === node.id ? '#f97316' : '#e2e8f0'
          sprite.textHeight = 3.5
          return sprite
        }}
        onNodeClick={handleNodeClick}
        onBackgroundClick={handleBgClick}
        onNodeDragEnd={(node: any) => {
          node.fx = node.x
          node.fy = node.y
          node.fz = node.z
        }}
        linkDirectionalArrowLength={2.5}
        linkDirectionalArrowRelPos={0.75}
        linkOpacity={0.5}
        linkColor={(link: any) => getEdgeColor(link as ExplainLink)}
        linkWidth={1.5}
        linkThreeObjectExtend={true}
        linkThreeObject={(link: any) => {
          const sprite = new SpriteText(wrap(link.type || '', 20))
          sprite.color = '#94a3b8'
          sprite.textHeight = 1.8
          return sprite
        }}
        linkPositionUpdate={(sprite: any, { start, end }: any) => {
          Object.assign(sprite.position, {
            x: start.x + (end.x - start.x) / 2,
            y: start.y + (end.y - start.y) / 2,
            z: start.z + (end.z - start.z) / 2,
          })
        }}
        linkDirectionalParticleColor={() => '#a855f7'}
        linkDirectionalParticleWidth={1.2}
        linkHoverPrecision={2}
        onLinkClick={(link: any) => {
          if (fgRef.current) fgRef.current.emitParticle(link)
        }}
      />
    </div>
  )
}
```

- [ ] **Step 2: Verify it compiles**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: No type errors (or only pre-existing ones).

- [ ] **Step 3: Commit**

```bash
git add src/app/knowledge-graph/components/ExplainabilityGraph3D.tsx
git commit -m "feat(frontend): add ExplainabilityGraph3D component (ForceGraph3D)

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: NodeDetailsDrawer + Supporting Components

**Files:**
- Create: `frontend/src/app/knowledge-graph/components/NodeDetailsDrawer.tsx`
- Create: `frontend/src/app/knowledge-graph/components/ExplainabilityLegend.tsx`
- Create: `frontend/src/app/knowledge-graph/components/ExplainabilityStatsBar.tsx`
- Create: `frontend/src/app/knowledge-graph/components/ExplainabilitySearchBar.tsx`

- [ ] **Step 1: Create NodeDetailsDrawer**

Uses the existing `Sheet` component from `@/components/ui/sheet`.

```typescript
// frontend/src/app/knowledge-graph/components/NodeDetailsDrawer.tsx
'use client'

import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { IconExternalLink } from '@tabler/icons-react'
import { ExplainNode, ExplainLink, NODE_COLORS, EDGE_COLORS } from './explainability-theme'

interface NodeDetailsDrawerProps {
  node: ExplainNode | null
  edges: ExplainLink[]
  allNodes: ExplainNode[]
  onClose: () => void
  onNavigate?: (nodeId: string) => void
}

export default function NodeDetailsDrawer({ node, edges, allNodes, onClose, onNavigate }: NodeDetailsDrawerProps) {
  if (!node) return null

  const connectedEdges = edges.filter(e => {
    const src = typeof e.source === 'string' ? e.source : e.source?.id
    const tgt = typeof e.target === 'string' ? e.target : e.target?.id
    return src === node.id || tgt === node.id
  })

  const resolveLabel = (id: string) => allNodes.find(n => n.id === id)?.label || id

  return (
    <Sheet open={!!node} onOpenChange={(open) => { if (!open) onClose() }}>
      <SheetContent className="w-[400px] bg-background/95 backdrop-blur-sm overflow-y-auto">
        <SheetHeader>
          <div className="flex items-center gap-2">
            <div
              className="w-3 h-3 rounded-full"
              style={{ backgroundColor: NODE_COLORS[node.type] }}
            />
            <Badge variant="outline" className="text-xs uppercase">
              {node.type}
            </Badge>
          </div>
          <SheetTitle className="text-lg">{node.label}</SheetTitle>
        </SheetHeader>

        {/* Properties */}
        <div className="mt-6">
          <h4 className="text-sm font-medium text-muted-foreground mb-2">Propiedades</h4>
          <div className="space-y-1">
            {Object.entries(node.properties).filter(([_, v]) => v != null).map(([key, value]) => (
              <div key={key} className="flex justify-between text-sm py-1 border-b border-border/50">
                <span className="text-muted-foreground font-mono text-xs">{key}</span>
                <span className="text-right max-w-[200px] truncate">{String(value)}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Relationships */}
        {connectedEdges.length > 0 && (
          <div className="mt-6">
            <h4 className="text-sm font-medium text-muted-foreground mb-2">
              Relaciones ({connectedEdges.length})
            </h4>
            <div className="space-y-2">
              {connectedEdges.map((edge, i) => {
                const src = typeof edge.source === 'string' ? edge.source : edge.source?.id
                const tgt = typeof edge.target === 'string' ? edge.target : edge.target?.id
                const otherId = src === node.id ? tgt : src
                const direction = src === node.id ? '→' : '←'
                return (
                  <button
                    key={i}
                    className="w-full flex items-center gap-2 text-sm p-2 rounded hover:bg-accent/50 transition-colors text-left"
                    onClick={() => otherId && onNavigate?.(otherId)}
                  >
                    <span className="text-muted-foreground">{direction}</span>
                    <Badge
                      variant="outline"
                      className="text-xs"
                      style={{ borderColor: EDGE_COLORS[edge.type] || '#64748b' }}
                    >
                      {edge.type}
                    </Badge>
                    <span className="truncate">{resolveLabel(otherId || '')}</span>
                  </button>
                )
              })}
            </div>
          </div>
        )}

        {/* Claim excerpt */}
        {node.type === 'claim' && node.properties.excerpt && (
          <div className="mt-6 p-3 bg-muted/50 rounded-md border-l-2 border-green-500">
            <h4 className="text-xs font-medium text-muted-foreground mb-1">Extracto</h4>
            <p className="text-sm">{String(node.properties.excerpt)}</p>
            {node.properties.confidence != null && (
              <div className="mt-2 flex items-center gap-2">
                <span className="text-xs text-muted-foreground">Confianza:</span>
                <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${(node.properties.confidence as number) * 100}%`,
                      backgroundColor: (node.properties.confidence as number) >= 0.8 ? '#22c55e' : (node.properties.confidence as number) >= 0.5 ? '#f59e0b' : '#ef4444',
                    }}
                  />
                </div>
                <span className="text-xs font-mono">{((node.properties.confidence as number) * 100).toFixed(0)}%</span>
              </div>
            )}
          </div>
        )}
      </SheetContent>
    </Sheet>
  )
}
```

- [ ] **Step 2: Create ExplainabilityLegend**

```typescript
// frontend/src/app/knowledge-graph/components/ExplainabilityLegend.tsx
'use client'

import { NODE_COLORS, ExplainNodeType } from './explainability-theme'

const LABELS: Record<ExplainNodeType, string> = {
  entity: 'Entidad',
  document: 'Documento',
  claim: 'Claim',
  law: 'Legislación',
  contradiction: 'Contradicción',
}

export default function ExplainabilityLegend() {
  return (
    <div className="absolute bottom-4 left-4 bg-background/80 backdrop-blur-sm border border-border/50 rounded-lg p-3 z-10">
      <h4 className="text-xs font-medium text-muted-foreground mb-2">Tipos de Nodo</h4>
      <div className="space-y-1.5">
        {(Object.entries(LABELS) as [ExplainNodeType, string][]).map(([type, label]) => (
          <div key={type} className="flex items-center gap-2">
            <div
              className={`w-2.5 h-2.5 rounded-full ${type === 'contradiction' ? 'animate-pulse' : ''}`}
              style={{ backgroundColor: NODE_COLORS[type] }}
            />
            <span className="text-xs">{label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Create ExplainabilityStatsBar**

```typescript
// frontend/src/app/knowledge-graph/components/ExplainabilityStatsBar.tsx
'use client'

import { NODE_COLORS } from './explainability-theme'

interface Stats {
  total_entities: number
  total_documents: number
  total_claims: number
  total_laws: number
  total_contradictions: number
}

export default function ExplainabilityStatsBar({ stats }: { stats: Stats }) {
  const items = [
    { label: 'Entidades', value: stats.total_entities, color: NODE_COLORS.entity },
    { label: 'Documentos', value: stats.total_documents, color: NODE_COLORS.document },
    { label: 'Claims', value: stats.total_claims, color: NODE_COLORS.claim },
    { label: 'Leyes', value: stats.total_laws, color: NODE_COLORS.law },
    { label: 'Contradicciones', value: stats.total_contradictions, color: NODE_COLORS.contradiction },
  ]

  return (
    <div className="flex items-center gap-4 px-4 py-2 border-b border-border/50">
      {items.map(({ label, value, color }) => (
        <div key={label} className="flex items-center gap-1.5">
          <div className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
          <span className="text-xs text-muted-foreground">{label}:</span>
          <span className="text-xs font-mono font-medium">{value}</span>
        </div>
      ))}
    </div>
  )
}
```

- [ ] **Step 4: Create ExplainabilitySearchBar**

```typescript
// frontend/src/app/knowledge-graph/components/ExplainabilitySearchBar.tsx
'use client'

import { useState } from 'react'
import { Input } from '@/components/ui/input'
import { IconSearch } from '@tabler/icons-react'
import { ExplainNode } from './explainability-theme'

interface ExplainabilitySearchBarProps {
  nodes: ExplainNode[]
  onFilter: (nodeIds: Set<string> | null) => void
  onFocus: (nodeId: string) => void
}

export default function ExplainabilitySearchBar({ nodes, onFilter, onFocus }: ExplainabilitySearchBarProps) {
  const [query, setQuery] = useState('')

  const handleSearch = (value: string) => {
    setQuery(value)
    if (!value.trim()) {
      onFilter(null)
      return
    }
    const lower = value.toLowerCase()
    const matched = nodes.filter(n => n.label.toLowerCase().includes(lower))
    onFilter(new Set(matched.map(n => n.id)))
    if (matched.length === 1) onFocus(matched[0].id)
  }

  return (
    <div className="absolute top-4 left-4 z-10 w-72">
      <div className="relative">
        <IconSearch className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          value={query}
          onChange={(e) => handleSearch(e.target.value)}
          placeholder="Buscar entidad, documento, claim..."
          className="pl-9 bg-background/80 backdrop-blur-sm border-border/50"
        />
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Commit**

```bash
git add src/app/knowledge-graph/components/NodeDetailsDrawer.tsx \
  src/app/knowledge-graph/components/ExplainabilityLegend.tsx \
  src/app/knowledge-graph/components/ExplainabilityStatsBar.tsx \
  src/app/knowledge-graph/components/ExplainabilitySearchBar.tsx
git commit -m "feat(frontend): add NodeDetailsDrawer, Legend, StatsBar, SearchBar

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Knowledge Graph Page

**Files:**
- Create: `frontend/src/app/knowledge-graph/page.tsx`
- Modify: `frontend/src/components/layout/app-sidebar.tsx`

- [ ] **Step 1: Create page.tsx**

Follow the pattern from `/admin/knowledge-tree/page.tsx` — SidebarProvider, data fetching, state management.

```typescript
// frontend/src/app/knowledge-graph/page.tsx
'use client'

import { useState, useEffect } from 'react'
import dynamic from 'next/dynamic'
import { SidebarProvider, SidebarInset } from '@/components/ui/sidebar'
import { AppSidebar } from '@/components/layout/app-sidebar'
import { explainabilityService, ExplainabilityNode, ExplainabilityEdge } from '@/lib/services/explainability.service'
import { ExplainNode, ExplainLink } from './components/explainability-theme'
import NodeDetailsDrawer from './components/NodeDetailsDrawer'
import ExplainabilityLegend from './components/ExplainabilityLegend'
import ExplainabilityStatsBar from './components/ExplainabilityStatsBar'
import ExplainabilitySearchBar from './components/ExplainabilitySearchBar'
import { useAuth } from '@/contexts/auth-context'

const ExplainabilityGraph3D = dynamic(
  () => import('./components/ExplainabilityGraph3D'),
  { ssr: false, loading: () => <div className="flex items-center justify-center h-full text-muted-foreground">Cargando grafo 3D...</div> }
)

function toExplainNodes(apiNodes: ExplainabilityNode[]): ExplainNode[] {
  return apiNodes.map(n => ({ ...n }))
}

function toExplainLinks(apiEdges: ExplainabilityEdge[]): ExplainLink[] {
  return apiEdges.map(e => ({ ...e }))
}

export default function KnowledgeGraphPage() {
  const { tenantId } = useAuth()
  const [nodes, setNodes] = useState<ExplainNode[]>([])
  const [links, setLinks] = useState<ExplainLink[]>([])
  const [stats, setStats] = useState({ total_entities: 0, total_documents: 0, total_claims: 0, total_laws: 0, total_contradictions: 0 })
  const [selectedNode, setSelectedNode] = useState<ExplainNode | null>(null)
  const [highlightedIds, setHighlightedIds] = useState<Set<string> | null>(null)
  const [focusNodeId, setFocusNodeId] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!tenantId) return
    setIsLoading(true)
    setError(null)

    explainabilityService.getGraph(tenantId)
      .then(data => {
        setNodes(toExplainNodes(data.nodes))
        setLinks(toExplainLinks(data.edges))
        setStats(data.stats)
      })
      .catch(err => setError(err.message || 'Error cargando grafo'))
      .finally(() => setIsLoading(false))
  }, [tenantId])

  return (
    <SidebarProvider>
      <AppSidebar variant="inset" />
      <SidebarInset>
        <div className="flex flex-col h-screen">
          <ExplainabilityStatsBar stats={stats} />
          <div className="relative flex-1 bg-[#07090f]">
            {isLoading && (
              <div className="absolute inset-0 flex items-center justify-center text-muted-foreground z-20">
                Cargando grafo de conocimiento...
              </div>
            )}
            {error && (
              <div className="absolute inset-0 flex items-center justify-center text-destructive z-20">
                {error}
              </div>
            )}
            {!isLoading && !error && nodes.length > 0 && (
              <>
                <ExplainabilityGraph3D
                  nodes={nodes}
                  links={links}
                  highlightedIds={highlightedIds}
                  onNodeClick={setSelectedNode}
                  focusNodeId={focusNodeId}
                />
                <ExplainabilitySearchBar
                  nodes={nodes}
                  onFilter={setHighlightedIds}
                  onFocus={setFocusNodeId}
                />
                <ExplainabilityLegend />
              </>
            )}
            {!isLoading && !error && nodes.length === 0 && (
              <div className="absolute inset-0 flex items-center justify-center text-muted-foreground">
                Sin datos. Indexa documentos para construir el grafo.
              </div>
            )}
          </div>
        </div>

        <NodeDetailsDrawer
          node={selectedNode}
          edges={links}
          allNodes={nodes}
          onClose={() => setSelectedNode(null)}
          onNavigate={(id) => {
            setFocusNodeId(id)
            const target = nodes.find(n => n.id === id)
            if (target) setSelectedNode(target)
          }}
        />
      </SidebarInset>
    </SidebarProvider>
  )
}
```

- [ ] **Step 2: Add sidebar navigation link**

In `frontend/src/components/layout/app-sidebar.tsx`, find where Knowledge Tree link is defined and add Knowledge Graph next to it:

```typescript
{
  title: 'Knowledge Graph',
  url: '/knowledge-graph',
  icon: IconNetwork, // from @tabler/icons-react
},
```

- [ ] **Step 3: Verify page loads**

```bash
cd frontend && npm run dev
# Navigate to http://localhost:3001/knowledge-graph
```

Expected: Page loads with empty state message or loading spinner (backend endpoint doesn't exist yet, so it will show error — that's fine).

- [ ] **Step 4: Commit**

```bash
git add src/app/knowledge-graph/page.tsx src/components/layout/app-sidebar.tsx
git commit -m "feat(frontend): add Knowledge Graph page with 3D ForceGraph

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Reasoning Modal Components

**Files:**
- Create: `frontend/src/components/emma-chat/ReasoningTimeline.tsx`
- Create: `frontend/src/components/emma-chat/ReasoningClaimDetail.tsx`
- Create: `frontend/src/components/emma-chat/ReasoningEvidenceGraph.tsx`
- Create: `frontend/src/components/emma-chat/ReasoningModal.tsx`

- [ ] **Step 1: Create ReasoningTimeline**

TrustGraph-style vertical timeline with colored badges.

```typescript
// frontend/src/components/emma-chat/ReasoningTimeline.tsx
'use client'

import { IconBrain, IconSearch, IconEye, IconTool, IconCheck, IconAlertTriangle, IconUsers } from '@tabler/icons-react'
import { Badge } from '@/components/ui/badge'
import type { ReasoningTimelineStep } from '@/lib/services/explainability.service'

const BADGE_MAP: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  thinking:    { label: 'RAZONAMIENTO', color: '#a855f7', icon: <IconBrain size={12} /> },
  reflection:  { label: 'RAZONAMIENTO', color: '#a855f7', icon: <IconBrain size={12} /> },
  search:      { label: 'BÚSQUEDA',    color: '#3b82f6', icon: <IconSearch size={12} /> },
  observation: { label: 'OBSERVACIÓN', color: '#f59e0b', icon: <IconEye size={12} /> },
  tool_call:   { label: 'ACCIÓN',      color: '#06b6d4', icon: <IconTool size={12} /> },
  tool_result: { label: 'ACCIÓN',      color: '#06b6d4', icon: <IconTool size={12} /> },
  answer:      { label: 'RESPUESTA',   color: '#22c55e', icon: <IconCheck size={12} /> },
  error:       { label: 'ERROR',       color: '#ef4444', icon: <IconAlertTriangle size={12} /> },
}

interface ReasoningTimelineProps {
  steps: ReasoningTimelineStep[]
  onStepHover?: (step: ReasoningTimelineStep | null) => void
  className?: string
}

export default function ReasoningTimeline({ steps, onStepHover, className = '' }: ReasoningTimelineProps) {
  return (
    <div className={`overflow-y-auto space-y-0 ${className}`}>
      {steps.map((step, i) => {
        const badge = BADGE_MAP[step.type] || BADGE_MAP.thinking
        return (
          <div
            key={i}
            className="relative pl-8 pb-4 group"
            onMouseEnter={() => onStepHover?.(step)}
            onMouseLeave={() => onStepHover?.(null)}
          >
            {/* Timeline line */}
            {i < steps.length - 1 && (
              <div className="absolute left-[11px] top-6 bottom-0 w-px bg-border/50" />
            )}
            {/* Timeline dot */}
            <div
              className="absolute left-1 top-1.5 w-[14px] h-[14px] rounded-full border-2 border-background"
              style={{ backgroundColor: badge.color }}
            />
            {/* Content */}
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <Badge
                  variant="outline"
                  className="text-[10px] px-1.5 py-0 h-5 font-medium"
                  style={{ borderColor: badge.color, color: badge.color }}
                >
                  {badge.icon}
                  <span className="ml-1">{badge.label}</span>
                </Badge>
                {step.source && (
                  <span className="text-[10px] text-muted-foreground font-mono">{step.source}</span>
                )}
                <span className="text-[10px] text-muted-foreground ml-auto">
                  {step.timestamp_ms > 0 ? `${(step.timestamp_ms / 1000).toFixed(1)}s` : ''}
                </span>
              </div>
              <p className="text-sm text-foreground/80 leading-relaxed">{step.content}</p>
              {step.confidence != null && (
                <div className="flex items-center gap-2">
                  <div className="w-16 h-1 bg-muted rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${step.confidence * 100}%`,
                        backgroundColor: step.confidence >= 0.8 ? '#22c55e' : step.confidence >= 0.5 ? '#f59e0b' : '#ef4444',
                      }}
                    />
                  </div>
                  <span className="text-[10px] font-mono text-muted-foreground">
                    {(step.confidence * 100).toFixed(0)}%
                  </span>
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 2: Create ReasoningClaimDetail**

```typescript
// frontend/src/components/emma-chat/ReasoningClaimDetail.tsx
'use client'

import { Button } from '@/components/ui/button'
import { IconX } from '@tabler/icons-react'
import type { ExplainNode } from '@/app/knowledge-graph/components/explainability-theme'
import { NODE_COLORS } from '@/app/knowledge-graph/components/explainability-theme'

interface ReasoningClaimDetailProps {
  node: ExplainNode
  onClose: () => void
}

export default function ReasoningClaimDetail({ node, onClose }: ReasoningClaimDetailProps) {
  const confidence = node.properties.confidence as number | undefined

  return (
    <div className="absolute bottom-4 right-4 w-80 bg-background/95 backdrop-blur-sm border border-border/50 rounded-lg p-4 z-20 shadow-xl">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: NODE_COLORS[node.type] }} />
          <span className="text-xs font-medium uppercase text-muted-foreground">{node.type}</span>
        </div>
        <Button variant="ghost" size="icon" className="h-6 w-6" onClick={onClose}>
          <IconX size={14} />
        </Button>
      </div>
      <h4 className="text-sm font-medium mb-2">{node.label}</h4>
      {node.properties.excerpt && (
        <p className="text-xs text-muted-foreground border-l-2 border-border pl-2 mb-2">
          {String(node.properties.excerpt)}
        </p>
      )}
      {confidence != null && (
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Confianza:</span>
          <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all"
              style={{
                width: `${confidence * 100}%`,
                backgroundColor: confidence >= 0.8 ? '#22c55e' : confidence >= 0.5 ? '#f59e0b' : '#ef4444',
              }}
            />
          </div>
          <span className="text-xs font-mono">{(confidence * 100).toFixed(0)}%</span>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Create ReasoningEvidenceGraph**

Small wrapper around ExplainabilityGraph3D for the modal context.

```typescript
// frontend/src/components/emma-chat/ReasoningEvidenceGraph.tsx
'use client'

import dynamic from 'next/dynamic'
import type { ExplainNode, ExplainLink } from '@/app/knowledge-graph/components/explainability-theme'

const ExplainabilityGraph3D = dynamic(
  () => import('@/app/knowledge-graph/components/ExplainabilityGraph3D'),
  { ssr: false, loading: () => <div className="flex items-center justify-center h-full text-muted-foreground text-sm">Cargando evidencia...</div> }
)

interface ReasoningEvidenceGraphProps {
  nodes: ExplainNode[]
  links: ExplainLink[]
  highlightedNodeIds?: string[]
  onNodeClick?: (node: ExplainNode) => void
  className?: string
}

export default function ReasoningEvidenceGraph({ nodes, links, highlightedNodeIds, onNodeClick, className }: ReasoningEvidenceGraphProps) {
  const highlighted = highlightedNodeIds ? new Set(highlightedNodeIds) : null

  return (
    <div className={`relative w-full h-full ${className || ''}`}>
      <ExplainabilityGraph3D
        nodes={nodes}
        links={links}
        highlightedIds={highlighted}
        onNodeClick={onNodeClick}
      />
    </div>
  )
}
```

- [ ] **Step 4: Create ReasoningModal**

Fullscreen overlay orchestrator with split layout.

```typescript
// frontend/src/components/emma-chat/ReasoningModal.tsx
'use client'

import { useState, useEffect, useMemo } from 'react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { IconX, IconClock } from '@tabler/icons-react'
import ReasoningTimeline from './ReasoningTimeline'
import ReasoningEvidenceGraph from './ReasoningEvidenceGraph'
import ReasoningClaimDetail from './ReasoningClaimDetail'
import type { ExplainNode } from '@/app/knowledge-graph/components/explainability-theme'
import type { ReasoningTimelineStep } from '@/lib/services/explainability.service'

interface ReasoningModalProps {
  reasoningSteps: any[]  // rawReasoningSteps from EmmaMessage
  sources?: any[]
  executionTimeMs?: number
  onClose: () => void
}

function transformSteps(rawSteps: any[]): ReasoningTimelineStep[] {
  return rawSteps.map((step, i) => ({
    index: i,
    type: mapStepType(step.type || step.step_type || 'thinking'),
    content: step.content || step.summary || step.text || '',
    source: step.source || step.tool_name || undefined,
    timestamp_ms: step.timestamp_ms || step.timestamp || 0,
    duration_ms: step.duration_ms || undefined,
    confidence: step.confidence || undefined,
    related_node_ids: step.related_node_ids || undefined,
  }))
}

function mapStepType(type: string): ReasoningTimelineStep['type'] {
  if (['thinking', 'analyzing'].includes(type)) return 'thinking'
  if (['searching', 'querying', 'browsing', 'search_result'].includes(type)) return 'search'
  if (['reading', 'doc_read', 'listing'].includes(type)) return 'observation'
  if (['connecting', 'preparing'].includes(type)) return 'tool_call'
  if (type === 'error') return 'error'
  if (type.startsWith('tool_')) return type as any
  return 'thinking'
}

function buildEvidenceGraph(sources: any[]) {
  const nodes: ExplainNode[] = []
  const links: any[] = []
  const seen = new Set<string>()

  for (const src of sources || []) {
    const id = src.document_id || src.id || `src-${nodes.length}`
    if (seen.has(id)) continue
    seen.add(id)
    nodes.push({
      id,
      type: src.source_type === 'public_knowledge' ? 'law' : 'document',
      label: src.title || src.name || id,
      properties: { excerpt: src.excerpt, confidence: src.relevanceScore },
    })
  }

  return { nodes, links }
}

export default function ReasoningModal({ reasoningSteps, sources, executionTimeMs, onClose }: ReasoningModalProps) {
  const [selectedClaim, setSelectedClaim] = useState<ExplainNode | null>(null)
  const [highlightedIds, setHighlightedIds] = useState<string[]>([])

  const timeline = useMemo(() => transformSteps(reasoningSteps), [reasoningSteps])
  const evidenceGraph = useMemo(() => buildEvidenceGraph(sources || []), [sources])

  // Escape to close
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  // Lock body scroll
  useEffect(() => {
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = '' }
  }, [])

  const handleStepHover = (step: ReasoningTimelineStep | null) => {
    setHighlightedIds(step?.related_node_ids || [])
  }

  return (
    <div className="fixed inset-0 z-50 bg-background/95 backdrop-blur-sm flex flex-col">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-border/50">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-medium">Razonamiento de Emma</h2>
          {executionTimeMs && (
            <Badge variant="outline" className="text-xs gap-1">
              <IconClock size={12} />
              {(executionTimeMs / 1000).toFixed(1)}s
            </Badge>
          )}
          <Badge variant="outline" className="text-xs">
            {timeline.length} pasos
          </Badge>
          {evidenceGraph.nodes.length > 0 && (
            <Badge variant="outline" className="text-xs">
              {evidenceGraph.nodes.length} fuentes
            </Badge>
          )}
        </div>
        <Button variant="ghost" size="icon" onClick={onClose}>
          <IconX size={18} />
        </Button>
      </div>

      {/* Split layout */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: Timeline */}
        <div className="w-[40%] border-r border-border/50 p-4 overflow-y-auto">
          <ReasoningTimeline
            steps={timeline}
            onStepHover={handleStepHover}
          />
        </div>

        {/* Right: Evidence Graph */}
        <div className="w-[60%] relative bg-[#07090f]">
          {evidenceGraph.nodes.length > 0 ? (
            <>
              <ReasoningEvidenceGraph
                nodes={evidenceGraph.nodes}
                links={evidenceGraph.links}
                highlightedNodeIds={highlightedIds}
                onNodeClick={setSelectedClaim}
              />
              {selectedClaim && (
                <ReasoningClaimDetail
                  node={selectedClaim}
                  onClose={() => setSelectedClaim(null)}
                />
              )}
            </>
          ) : (
            <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
              Sin evidencia gráfica para esta respuesta
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Commit**

```bash
git add src/components/emma-chat/ReasoningTimeline.tsx \
  src/components/emma-chat/ReasoningClaimDetail.tsx \
  src/components/emma-chat/ReasoningEvidenceGraph.tsx \
  src/components/emma-chat/ReasoningModal.tsx
git commit -m "feat(frontend): add Reasoning Modal with timeline + evidence graph

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Integrate into Chat (MessageBubble)

**Files:**
- Modify: `frontend/src/components/emma-chat/messages/MessageBubble.tsx`

- [ ] **Step 1: Read MessageBubble.tsx to understand ActionBar**

Read the file first to find where action buttons are rendered and where to add "Ver Razonamiento".

- [ ] **Step 2: Add "Ver Razonamiento" button**

In MessageBubble.tsx, add state and the button:

```typescript
import { IconRoute } from '@tabler/icons-react'
import ReasoningModal from '../ReasoningModal'

// In the component:
const [showReasoning, setShowReasoning] = useState(false)

// In the action bar area (near copy/feedback buttons):
{message.metadata?.rawReasoningSteps?.length > 0 && (
  <Button
    variant="ghost"
    size="sm"
    className="h-7 text-xs gap-1 text-muted-foreground hover:text-foreground"
    onClick={() => setShowReasoning(true)}
  >
    <IconRoute size={14} />
    Ver Razonamiento
  </Button>
)}

// At the end of the component return (before closing fragment):
{showReasoning && (
  <ReasoningModal
    reasoningSteps={message.metadata?.rawReasoningSteps || []}
    sources={message.metadata?.sources || message.metadata?.documents || []}
    executionTimeMs={message.metadata?.execution_time_ms}
    onClose={() => setShowReasoning(false)}
  />
)}
```

- [ ] **Step 3: Verify build**

```bash
cd frontend && npm run build 2>&1 | tail -10
```

- [ ] **Step 4: Commit**

```bash
git add src/components/emma-chat/messages/MessageBubble.tsx
git commit -m "feat(frontend): add 'Ver Razonamiento' button to chat messages

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Visual Polish + Verify

**Files:**
- All new files (CSS adjustments if needed)

- [ ] **Step 1: Start dev server**

```bash
cd frontend && npm run dev
```

- [ ] **Step 2: Verify Knowledge Graph page**

Navigate to `http://localhost:3001/knowledge-graph`. Expected:
- Page loads with sidebar
- Shows empty state or error (backend endpoint not implemented yet)
- StatsBar renders with zeros
- Legend renders with 5 colored dots
- No console errors from ForceGraph3D

- [ ] **Step 3: Verify Reasoning Modal**

In the chat, send a query to Emma. When response arrives with reasoning steps:
- Hover the response → "Ver Razonamiento" button should appear
- Click → fullscreen modal with split layout
- Left: timeline with colored badges
- Right: evidence graph (may be empty if no sources)
- Escape closes

- [ ] **Step 4: Fix any visual issues**

Adjust spacing, colors, or layout if needed.

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "fix(frontend): visual polish for explainability UI

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```
