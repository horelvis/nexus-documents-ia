# TrustGraph Phase 2 Frontend — Graph Visualization & Chat Integration

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adapt Knowledge Graph 3D, Knowledge Tree 2D, and Emma Chat to the TrustGraph `:Node`/`:Rel` model with entity-first navigation, message type badges, and clickable entity tags.

**Architecture:** Service layer fetches from new KTS `/triples/neighbors` + `/weaviate/entities/search` endpoints. Both graph views transform triples into Node→Node force graph (literals become properties in drawer). Chat integration maps SSE events to visual badges and extracts entity tags from Graph RAG responses.

**Tech Stack:** Next.js 15 App Router, TypeScript, react-force-graph-3d, D3, shadcn/ui (Sheet, Command, Badge, Tabs, Table), Tailwind CSS.

**Spec:** `docs/superpowers/specs/2026-03-28-trustgraph-phase2-frontend-graph-viz-design.md`
**Depends on:** Phase 2 Backend complete (Task 1-11 from backend plan)

---

## File Structure

| File | Responsibility |
|------|---------------|
| `lib/services/knowledge-tree.service.ts` | **MODIFY** — Add `getSubgraphByTriples()`, `getEntityTriples()` methods |
| `lib/services/entity-search.service.ts` | **NEW** — Weaviate TrustGraphEntities similarity search |
| `lib/services/explainability.service.ts` | **MODIFY** — Add triple-based data fetching |
| `app/knowledge-graph/components/explainability-theme.ts` | **MODIFY** — Type-based colors + namespace edge styles |
| `app/knowledge-graph/components/ExplainabilityGraph3D.tsx` | **MODIFY** — TrustGraph data model, triple transform |
| `app/knowledge-graph/components/NodeDetailsDrawer.tsx` | **MODIFY** — Triple-based tabs: relationships, properties, contradictions |
| `app/admin/knowledge-tree/components/graph-theme.ts` | **MODIFY** — Type-based colors matching 3D theme |
| `app/admin/knowledge-tree/components/ForceGraph.tsx` | **MODIFY** — TrustGraph data model |
| `components/graph/EntitySearchBar.tsx` | **NEW** — Similarity search combobox (shared) |
| `components/emma-chat/EmmaMarkdown.tsx` | **MODIFY** — Message type badges |
| `components/emma-chat/hooks/useMessageConverter.ts` | **MODIFY** — Entity tag extraction from tool results |
| `components/emma-chat/EntityTags.tsx` | **NEW** — Clickable entity tags below responses |

**Path prefix:** all paths relative to `frontend/src/`

---

## Task 1: Entity Search Service

New service for searching TrustGraph entities via Weaviate similarity.

**Files:**
- Create: `frontend/src/lib/services/entity-search.service.ts`

- [ ] **Step 1: Create entity-search.service.ts**

```typescript
// frontend/src/lib/services/entity-search.service.ts
"use client"

/**
 * Entity Search Service
 *
 * Search TrustGraph entities by text similarity via Weaviate TrustGraphEntities.
 * Proxied through /api/v1/weaviate → weaviate-service.
 */

import { apiClient } from '@/lib/api-client'

export interface EntityMatch {
  entity_uri: string
  label: string
  definition: string
  entity_type: string
  score: number
}

export interface EntitySearchResponse {
  entities: EntityMatch[]
  count: number
}

class EntitySearchService {
  async search(
    tenantId: string,
    query: string,
    limit: number = 10,
  ): Promise<EntityMatch[]> {
    try {
      const response = await apiClient.post<EntitySearchResponse>(
        '/api/v1/weaviate/entities/search',
        { query, tenant_id: tenantId, limit },
      )
      return response.data?.entities ?? []
    } catch (error) {
      console.error('Entity search failed:', error)
      return []
    }
  }
}

export const entitySearchService = new EntitySearchService()
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/lib/services/entity-search.service.ts
git commit -m "feat(trustgraph-ui): entity search service for Weaviate TrustGraphEntities"
```

---

## Task 2: Knowledge Tree Service Updates

Add methods for the new TrustGraph triple-based data fetching.

**Files:**
- Modify: `frontend/src/lib/services/knowledge-tree.service.ts`

- [ ] **Step 1: Add triple-based interfaces and methods**

Add these interfaces after the existing ones in `knowledge-tree.service.ts`:

```typescript
// ── TrustGraph Phase 2 Types ──

export interface Triple {
  subject: string
  predicate: string
  object: string
  object_type: 'node' | 'literal'
  extraction_method?: string
  source_chunk?: string
}

export interface TripleNeighborsResponse {
  edges: Triple[]
  entities_visited: number
  hops_used: number
}

export interface TrustGraphNode {
  id: string              // entity URI
  label: string           // from core/label triple
  type: string            // from core/type: "law", "person", "organization"
  definition?: string     // from core/definition
  connectionCount: number // degree centrality
}

export interface TrustGraphEdge {
  id: string              // hash: s@@p@@o
  source: string          // subject URI
  target: string          // object URI
  predicate: string       // last segment: "regulado-por"
  namespace: string       // "core", "legal"
  weight: number          // 1.0 default or edge score
}

export interface EntityProperty {
  predicate: string
  namespace: string
  value: string
  extractionMethod?: string
  sourceDocument?: string
}

export interface Contradiction {
  subject: string
  predicate: string
  valueA: string
  valueB: string
  sourceA?: string
  sourceB?: string
}
```

Add these methods to the `KnowledgeTreeService` class:

```typescript
  /** BFS subgraph via /triples/neighbors */
  async getTripleNeighbors(
    tenantId: string,
    seedUris: string[],
    maxHops: number = 2,
    maxEdges: number = 150,
  ): Promise<TripleNeighborsResponse> {
    try {
      const response = await apiClient.post<TripleNeighborsResponse>(
        '/api/v1/knowledge-tree/triples/neighbors',
        {
          tenant_id: tenantId,
          seed_uris: seedUris,
          max_hops: maxHops,
          max_edges: maxEdges,
          exclude_predicates: ['prov/.*'],
        },
      )
      return response.data ?? { edges: [], entities_visited: 0, hops_used: 0 }
    } catch (error) {
      console.error('Triple neighbors failed:', error)
      return { edges: [], entities_visited: 0, hops_used: 0 }
    }
  }

  /** Get all triples for a specific entity */
  async getEntityTriples(
    tenantId: string,
    entityUri: string,
  ): Promise<Triple[]> {
    try {
      const response = await apiClient.post<{ triples: Triple[] }>(
        '/api/v1/knowledge-tree/triples/query',
        { tenant_id: tenantId, subject_uri: entityUri, limit: 100 },
      )
      return response.data?.triples ?? []
    } catch (error) {
      console.error('Entity triples failed:', error)
      return []
    }
  }
```

- [ ] **Step 2: Add graph data transformation function**

Add this standalone function below the service class:

```typescript
/**
 * Transform raw triples into force graph data.
 * Node→Node edges go into the graph; Node→Literal become properties.
 *
 * Adopted from TrustGraph workbench-ui knowledge-graph-viz.ts.
 */
export function buildTrustGraphData(triples: Triple[]): {
  nodes: TrustGraphNode[]
  edges: TrustGraphEdge[]
  properties: Map<string, EntityProperty[]>
  contradictions: Contradiction[]
} {
  const nodeMap = new Map<string, TrustGraphNode>()
  const edges: TrustGraphEdge[] = []
  const properties = new Map<string, EntityProperty[]>()

  for (const triple of triples) {
    const predicateSegments = triple.predicate.split('/')
    const predicateName = predicateSegments.pop() ?? triple.predicate
    const namespace = predicateSegments.pop() ?? 'core'

    // Skip prov/* and core/label (labels resolved via node map)
    if (namespace === 'prov') continue
    if (predicateName === 'label') continue

    if (triple.object_type === 'literal') {
      // Node→Literal: store as property
      const props = properties.get(triple.subject) ?? []
      props.push({
        predicate: predicateName,
        namespace,
        value: triple.object,
        extractionMethod: triple.extraction_method,
        sourceDocument: triple.source_chunk,
      })
      properties.set(triple.subject, props)

      // Ensure subject node exists
      if (!nodeMap.has(triple.subject)) {
        nodeMap.set(triple.subject, {
          id: triple.subject,
          label: '',
          type: 'other',
          connectionCount: 0,
        })
      }
      continue
    }

    // Node→Node: force graph edge
    if (!nodeMap.has(triple.subject)) {
      nodeMap.set(triple.subject, {
        id: triple.subject,
        label: '',
        type: 'other',
        connectionCount: 0,
      })
    }
    if (!nodeMap.has(triple.object)) {
      nodeMap.set(triple.object, {
        id: triple.object,
        label: '',
        type: 'other',
        connectionCount: 0,
      })
    }

    nodeMap.get(triple.subject)!.connectionCount++
    nodeMap.get(triple.object)!.connectionCount++

    const edgeId = `${triple.subject}@@${triple.predicate}@@${triple.object}`
    edges.push({
      id: edgeId,
      source: triple.subject,
      target: triple.object,
      predicate: predicateName,
      namespace,
      weight: 1.0,
    })
  }

  // Resolve labels and types from properties
  for (const [uri, node] of nodeMap) {
    const props = properties.get(uri) ?? []
    const labelProp = props.find(p => p.predicate === 'label')
    const typeProp = props.find(p => p.predicate === 'type')
    const defProp = props.find(p => p.predicate === 'definition')

    if (labelProp) node.label = labelProp.value
    if (typeProp) node.type = typeProp.value
    if (defProp) node.definition = defProp.value

    // Fallback: humanize URI
    if (!node.label) {
      node.label = uri.split('/').pop()?.replace(/-/g, ' ') ?? uri
      // Title case
      node.label = node.label.replace(/\b\w/g, c => c.toUpperCase())
    }
  }

  // Detect contradictions: same subject+predicate with different literal values
  const contradictions: Contradiction[] = []
  for (const [uri, props] of properties) {
    const grouped = new Map<string, EntityProperty[]>()
    for (const prop of props) {
      const key = prop.predicate
      const group = grouped.get(key) ?? []
      group.push(prop)
      grouped.set(key, group)
    }
    for (const [predicate, group] of grouped) {
      if (group.length >= 2) {
        const uniqueValues = [...new Set(group.map(p => p.value))]
        if (uniqueValues.length >= 2) {
          contradictions.push({
            subject: uri,
            predicate,
            valueA: uniqueValues[0],
            valueB: uniqueValues[1],
            sourceA: group[0].sourceDocument,
            sourceB: group[1].sourceDocument,
          })
        }
      }
    }
  }

  return {
    nodes: Array.from(nodeMap.values()),
    edges,
    properties,
    contradictions,
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/services/knowledge-tree.service.ts
git commit -m "feat(trustgraph-ui): triple-based data fetching + graph transformation"
```

---

## Task 3: Graph Theme — Type-Based Colors

Update both theme files to use dynamic entity-type colors matching the TrustGraph model.

**Files:**
- Modify: `frontend/src/app/knowledge-graph/components/explainability-theme.ts`
- Modify: `frontend/src/app/admin/knowledge-tree/components/graph-theme.ts`

- [ ] **Step 1: Update explainability-theme.ts**

Replace the existing `NODE_COLORS` with type-based colors. Keep the existing interface exports but update them:

```typescript
// ── TrustGraph entity type colors ──

export const ENTITY_TYPE_COLORS: Record<string, string> = {
  document: '#3b82f6',    // blue-500
  person: '#f59e0b',      // amber-500
  law: '#06b6d4',         // cyan-500
  organization: '#22c55e', // green-500
  contract: '#f43f5e',    // rose-500
  amount: '#a855f7',      // purple-500
  date: '#64748b',        // slate-500
  place: '#f97316',       // orange-500
  topic: '#14b8a6',       // teal-500
  other: '#6b7280',       // gray-500
}

export const ENTITY_TYPE_GLOW: Record<string, string> = {
  document: 'rgba(59, 130, 246, 0.4)',
  person: 'rgba(245, 158, 11, 0.4)',
  law: 'rgba(6, 182, 212, 0.4)',
  organization: 'rgba(34, 197, 94, 0.4)',
  contract: 'rgba(244, 63, 94, 0.4)',
  amount: 'rgba(168, 85, 247, 0.4)',
  date: 'rgba(100, 116, 139, 0.3)',
  place: 'rgba(249, 115, 22, 0.4)',
  topic: 'rgba(20, 184, 166, 0.4)',
  other: 'rgba(107, 114, 128, 0.3)',
}

export function getEntityColor(type: string): string {
  return ENTITY_TYPE_COLORS[type] ?? ENTITY_TYPE_COLORS.other
}

export function getEntityGlow(type: string): string {
  return ENTITY_TYPE_GLOW[type] ?? ENTITY_TYPE_GLOW.other
}

export function getEntityNodeSize(connectionCount: number): number {
  return 8 + Math.log(connectionCount + 1) * 4
}

// ── Edge styles by namespace ──

export const EDGE_NAMESPACE_STYLES: Record<string, {
  color: string
  width: number
  dash?: string
  opacity: number
}> = {
  core: { color: '#94a3b8', width: 1.5, opacity: 0.6 },
  legal: { color: '#22d3ee', width: 2.5, opacity: 0.8 },
  prov: { color: '#475569', width: 1, dash: '2,4', opacity: 0.3 },
  contradiction: { color: '#f43f5e', width: 2, dash: '4,4', opacity: 0.9 },
}

export function getEdgeStyle(namespace: string) {
  return EDGE_NAMESPACE_STYLES[namespace] ?? EDGE_NAMESPACE_STYLES.core
}
```

Keep backward compatibility by re-exporting as `NODE_COLORS`:

```typescript
// Backward compat — alias for old consumers
export const NODE_COLORS = ENTITY_TYPE_COLORS
```

- [ ] **Step 2: Update graph-theme.ts (2D)**

Apply the same color scheme to `graph-theme.ts`. Replace the `NodeKind`-based color map:

```typescript
// ── TrustGraph entity type colors (same as 3D) ──

export const ENTITY_TYPE_COLORS: Record<string, string> = {
  document: '#3b82f6',
  person: '#f59e0b',
  law: '#06b6d4',
  organization: '#22c55e',
  contract: '#f43f5e',
  amount: '#a855f7',
  date: '#64748b',
  place: '#f97316',
  topic: '#14b8a6',
  other: '#6b7280',
}

export function getNodeColor(type: string): string {
  return ENTITY_TYPE_COLORS[type] ?? ENTITY_TYPE_COLORS.other
}

export function getNodeRadius(connectionCount: number): number {
  return 6 + Math.log(connectionCount + 1) * 3
}

// ── Edge styles by namespace ──

export const EDGE_STYLES: Record<string, {
  stroke: string
  strokeWidth: number
  dashArray?: string
  opacity: number
}> = {
  core: { stroke: '#94a3b8', strokeWidth: 1.5, opacity: 0.6 },
  legal: { stroke: '#22d3ee', strokeWidth: 2.5, opacity: 0.8 },
  prov: { stroke: '#475569', strokeWidth: 1, dashArray: '2,4', opacity: 0.3 },
}

export function getEdgeStyle(namespace: string) {
  return EDGE_STYLES[namespace] ?? EDGE_STYLES.core
}
```

Keep the existing `SimNode` / `SimLink` interfaces but update them to use `type` instead of `kind`:

```typescript
export interface SimNode extends SimulationNodeDatum {
  id: string
  label: string
  name: string
  type: string            // entity type from core/type
  properties: Record<string, unknown>
  connectionCount: number
}

export interface SimLink extends SimulationLinkDatum<SimNode> {
  id: string
  predicate: string       // predicate name
  namespace: string       // "core", "legal"
  properties: Record<string, unknown>
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/knowledge-graph/components/explainability-theme.ts \
       frontend/src/app/admin/knowledge-tree/components/graph-theme.ts
git commit -m "feat(trustgraph-ui): type-based entity colors + namespace edge styles"
```

---

## Task 4: Entity Search Bar (Shared Component)

Debounced similarity search combobox for both graph views.

**Files:**
- Create: `frontend/src/components/graph/EntitySearchBar.tsx`

- [ ] **Step 1: Create EntitySearchBar component**

```tsx
// frontend/src/components/graph/EntitySearchBar.tsx
'use client'

import { useState, useEffect, useRef } from 'react'
import {
  Command,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
} from '@/components/ui/command'
import { Badge } from '@/components/ui/badge'
import { entitySearchService, type EntityMatch } from '@/lib/services/entity-search.service'
import { ENTITY_TYPE_COLORS } from '@/app/knowledge-graph/components/explainability-theme'

interface EntitySearchBarProps {
  tenantId: string
  onSelect: (entity: EntityMatch) => void
  placeholder?: string
  className?: string
}

export function EntitySearchBar({
  tenantId,
  onSelect,
  placeholder = 'Buscar entidades...',
  className = '',
}: EntitySearchBarProps) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<EntityMatch[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [isOpen, setIsOpen] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current)

    if (query.length < 2) {
      setResults([])
      return
    }

    timerRef.current = setTimeout(async () => {
      setIsLoading(true)
      try {
        const entities = await entitySearchService.search(tenantId, query, 10)
        setResults(entities)
        setIsOpen(true)
      } catch {
        setResults([])
      } finally {
        setIsLoading(false)
      }
    }, 300)

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [query, tenantId])

  function handleSelect(entity: EntityMatch) {
    setIsOpen(false)
    setQuery('')
    setResults([])
    onSelect(entity)
  }

  return (
    <div className={`relative ${className}`}>
      <Command shouldFilter={false} className="rounded-lg border border-white/10 bg-slate-900/90 backdrop-blur">
        <CommandInput
          placeholder={placeholder}
          value={query}
          onValueChange={setQuery}
          onFocus={() => results.length > 0 && setIsOpen(true)}
          className="text-sm"
        />
        {isOpen && (
          <CommandList className="max-h-60">
            {isLoading && <CommandEmpty>Buscando...</CommandEmpty>}
            {!isLoading && results.length === 0 && query.length >= 2 && (
              <CommandEmpty>No se encontraron entidades</CommandEmpty>
            )}
            {results.length > 0 && (
              <CommandGroup heading="Entidades">
                {results.map((entity) => (
                  <CommandItem
                    key={entity.entity_uri}
                    value={entity.entity_uri}
                    onSelect={() => handleSelect(entity)}
                    className="flex items-center gap-2"
                  >
                    <span
                      className="h-2 w-2 rounded-full flex-shrink-0"
                      style={{ backgroundColor: ENTITY_TYPE_COLORS[entity.entity_type] ?? '#6b7280' }}
                    />
                    <span className="flex-1 truncate">{entity.label}</span>
                    <Badge variant="outline" className="text-[10px] px-1.5">
                      {entity.entity_type}
                    </Badge>
                    <span className="text-xs text-muted-foreground">
                      {Math.round(entity.score * 100)}%
                    </span>
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
          </CommandList>
        )}
      </Command>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/graph/EntitySearchBar.tsx
git commit -m "feat(trustgraph-ui): EntitySearchBar — similarity search combobox"
```

---

## Task 5: ExplainabilityGraph3D — TrustGraph Data Model

Update the 3D graph to fetch and render TrustGraph triples.

**Files:**
- Modify: `frontend/src/app/knowledge-graph/components/ExplainabilityGraph3D.tsx`

- [ ] **Step 1: Update data fetching and transformation**

Replace the existing data fetching logic to use `getTripleNeighbors` + `buildTrustGraphData`:

```typescript
import {
  type TrustGraphNode,
  type TrustGraphEdge,
  type Triple,
  buildTrustGraphData,
} from '@/lib/services/knowledge-tree.service'
import {
  getEntityColor,
  getEntityGlow,
  getEntityNodeSize,
  getEdgeStyle,
} from './explainability-theme'
```

In the component, update the data loading:

```typescript
  // Replace the old data fetch with triple-based loading
  const [graphNodes, setGraphNodes] = useState<TrustGraphNode[]>([])
  const [graphEdges, setGraphEdges] = useState<TrustGraphEdge[]>([])
  const [properties, setProperties] = useState<Map<string, EntityProperty[]>>(new Map())
  const [contradictions, setContradictions] = useState<Contradiction[]>([])

  async function loadGraph(seedUris?: string[]) {
    setIsLoading(true)
    setError(null)
    try {
      const seeds = seedUris ?? []  // Empty = load full graph stats first
      const response = await knowledgeTreeApi.getTripleNeighbors(
        tenantId, seeds, 2, 150,
      )
      const { nodes, edges, properties: props, contradictions: contras } = buildTrustGraphData(response.edges)
      setGraphNodes(nodes)
      setGraphEdges(edges)
      setProperties(props)
      setContradictions(contras)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load graph')
    } finally {
      setIsLoading(false)
    }
  }
```

- [ ] **Step 2: Update node and edge rendering**

Update the ForceGraph3D component configuration:

```typescript
  // Node color by entity type
  nodeColor={(node: any) => getEntityColor(node.type)}

  // Node size by connection count
  nodeVal={(node: any) => getEntityNodeSize(node.connectionCount)}

  // Node tooltip
  nodeLabel={(node: any) =>
    `${node.label} (${node.type})${node.definition ? '\n' + node.definition : ''}`
  }

  // Edge color by namespace
  linkColor={(link: any) => getEdgeStyle(link.namespace).color}

  // Edge width by namespace
  linkWidth={(link: any) => getEdgeStyle(link.namespace).width}

  // Edge label (predicate name)
  linkLabel={(link: any) => link.predicate.replace(/-/g, ' ')}

  // Edge opacity
  linkOpacity={0.7}

  // Click node → open drawer + center camera
  onNodeClick={(node: any) => {
    setSelectedNode(node)
    // Camera animation to node
    if (fgRef.current) {
      const distance = 120
      const distRatio = 1 + distance / Math.hypot(node.x, node.y, node.z)
      fgRef.current.cameraPosition(
        { x: node.x * distRatio, y: node.y * distRatio, z: node.z * distRatio },
        node,
        1000,
      )
    }
  }}

  // Click edge → emit particles (TrustGraph pattern)
  onLinkClick={(link: any) => {
    if (fgRef.current) {
      fgRef.current.emitParticle(link)
    }
  }}
```

- [ ] **Step 3: Wire up EntitySearchBar**

Add to the component's JSX:

```tsx
  <EntitySearchBar
    tenantId={tenantId}
    onSelect={(entity) => {
      // Load subgraph centered on selected entity
      loadGraph([entity.entity_uri])
    }}
    className="absolute top-4 left-4 w-72 z-10"
  />
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/knowledge-graph/components/ExplainabilityGraph3D.tsx
git commit -m "feat(trustgraph-ui): 3D graph uses TrustGraph triples + entity search"
```

---

## Task 6: NodeDetailsDrawer — Triple-Based Tabs

Rewrite the drawer to show TrustGraph relationships, properties, and contradictions.

**Files:**
- Modify: `frontend/src/app/knowledge-graph/components/NodeDetailsDrawer.tsx`

- [ ] **Step 1: Rewrite NodeDetailsDrawer**

Replace the existing content with a three-tab layout. The component already uses `Sheet` from shadcn and receives node/edges/allNodes props. Update to accept TrustGraph types:

```tsx
'use client'

import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import {
  ENTITY_TYPE_COLORS,
} from './explainability-theme'
import type {
  TrustGraphNode,
  TrustGraphEdge,
  EntityProperty,
  Contradiction,
} from '@/lib/services/knowledge-tree.service'

interface NodeDetailsDrawerProps {
  node: TrustGraphNode | null
  edges: TrustGraphEdge[]
  allNodes: TrustGraphNode[]
  properties: EntityProperty[]
  contradictions: Contradiction[]
  onClose: () => void
  onNavigate?: (nodeUri: string) => void
}

export function NodeDetailsDrawer({
  node,
  edges,
  allNodes,
  properties,
  contradictions,
  onClose,
  onNavigate,
}: NodeDetailsDrawerProps) {
  if (!node) return null

  const nodeColor = ENTITY_TYPE_COLORS[node.type] ?? '#6b7280'
  const nodeMap = new Map(allNodes.map((n) => [n.id, n]))

  // Edges connected to this node
  const relatedEdges = edges.filter(
    (e) => {
      const sourceId = typeof e.source === 'string' ? e.source : (e.source as any)?.id
      const targetId = typeof e.target === 'string' ? e.target : (e.target as any)?.id
      return sourceId === node.id || targetId === node.id
    },
  )

  // Node contradictions
  const nodeContradictions = contradictions.filter((c) => c.subject === node.id)

  return (
    <Sheet open={!!node} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" className="w-[400px] sm:w-[480px] overflow-y-auto">
        <SheetHeader className="pb-4">
          <div className="flex items-center gap-2">
            <span
              className="h-3 w-3 rounded-full"
              style={{ backgroundColor: nodeColor }}
            />
            <SheetTitle className="text-lg">{node.label}</SheetTitle>
            <Badge variant="outline" className="text-xs">
              {node.type}
            </Badge>
          </div>
          {node.definition && (
            <p className="text-sm text-muted-foreground mt-1">{node.definition}</p>
          )}
        </SheetHeader>

        <Tabs defaultValue="relationships" className="mt-2">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="relationships">
              Relaciones ({relatedEdges.length})
            </TabsTrigger>
            <TabsTrigger value="properties">
              Propiedades ({properties.length})
            </TabsTrigger>
            <TabsTrigger value="contradictions">
              Conflictos ({nodeContradictions.length})
            </TabsTrigger>
          </TabsList>

          {/* Relationships Tab */}
          <TabsContent value="relationships" className="mt-3 space-y-1">
            {relatedEdges.length === 0 && (
              <p className="text-sm text-muted-foreground">Sin relaciones</p>
            )}
            {relatedEdges.map((edge) => {
              const sourceId = typeof edge.source === 'string' ? edge.source : (edge.source as any)?.id
              const targetId = typeof edge.target === 'string' ? edge.target : (edge.target as any)?.id
              const isOutgoing = sourceId === node.id
              const otherUri = isOutgoing ? targetId : sourceId
              const otherNode = nodeMap.get(otherUri)
              const otherLabel = otherNode?.label ?? otherUri?.split('/').pop()?.replace(/-/g, ' ') ?? '?'

              return (
                <div
                  key={edge.id}
                  className="flex items-center gap-2 py-1.5 px-2 rounded hover:bg-white/5 cursor-pointer"
                  onClick={() => onNavigate?.(otherUri)}
                >
                  <span className="text-xs text-muted-foreground w-4">
                    {isOutgoing ? '→' : '←'}
                  </span>
                  <Badge variant="outline" className="text-[10px] font-mono">
                    {edge.predicate}
                  </Badge>
                  <span className="flex-1 text-sm truncate">{otherLabel}</span>
                  {otherNode && (
                    <span
                      className="h-2 w-2 rounded-full"
                      style={{ backgroundColor: ENTITY_TYPE_COLORS[otherNode.type] ?? '#6b7280' }}
                    />
                  )}
                </div>
              )
            })}
          </TabsContent>

          {/* Properties Tab */}
          <TabsContent value="properties" className="mt-3 space-y-1">
            {properties.length === 0 && (
              <p className="text-sm text-muted-foreground">Sin propiedades</p>
            )}
            {properties.map((prop, i) => (
              <div key={`${prop.predicate}-${i}`} className="flex items-start gap-2 py-1.5 px-2">
                <Badge variant="outline" className="text-[10px] font-mono flex-shrink-0 mt-0.5">
                  {prop.namespace}/{prop.predicate}
                </Badge>
                <span className="text-sm flex-1 break-words">{prop.value}</span>
              </div>
            ))}
          </TabsContent>

          {/* Contradictions Tab */}
          <TabsContent value="contradictions" className="mt-3 space-y-2">
            {nodeContradictions.length === 0 && (
              <p className="text-sm text-muted-foreground">Sin conflictos detectados</p>
            )}
            {nodeContradictions.map((c, i) => (
              <div key={`contradiction-${i}`} className="border border-rose-500/30 rounded-md p-3 bg-rose-500/5">
                <div className="text-xs font-mono text-rose-400 mb-2">{c.predicate}</div>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div>
                    <div className="text-muted-foreground text-xs mb-1">Valor A</div>
                    <div>{c.valueA}</div>
                    {c.sourceA && <div className="text-xs text-muted-foreground mt-1">{c.sourceA}</div>}
                  </div>
                  <div>
                    <div className="text-muted-foreground text-xs mb-1">Valor B</div>
                    <div>{c.valueB}</div>
                    {c.sourceB && <div className="text-xs text-muted-foreground mt-1">{c.sourceB}</div>}
                  </div>
                </div>
              </div>
            ))}
          </TabsContent>
        </Tabs>
      </SheetContent>
    </Sheet>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/app/knowledge-graph/components/NodeDetailsDrawer.tsx
git commit -m "feat(trustgraph-ui): NodeDetailsDrawer with relationships/properties/contradictions tabs"
```

---

## Task 7: ForceGraph 2D — TrustGraph Data Model

Update the 2D D3 force graph to use TrustGraph triples.

**Files:**
- Modify: `frontend/src/app/admin/knowledge-tree/components/ForceGraph.tsx`

- [ ] **Step 1: Update ForceGraph props and data handling**

Update the component's props interface to accept TrustGraph types:

```typescript
import type { TrustGraphNode, TrustGraphEdge } from '@/lib/services/knowledge-tree.service'
import { getNodeColor, getNodeRadius, getEdgeStyle } from './graph-theme'

interface ForceGraphProps {
  nodes: TrustGraphNode[]
  links: TrustGraphEdge[]
  highlightedIds?: Set<string>
  onNodeClick?: (node: TrustGraphNode) => void
}
```

Update the D3 force simulation configuration:

```typescript
  // Denser layout for TrustGraph
  const simulation = d3.forceSimulation(simNodes)
    .force('link', d3.forceLink(simLinks).id((d: any) => d.id).distance(60))
    .force('charge', d3.forceManyBody().strength(-200))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collide', d3.forceCollide().radius(30))
```

Update node rendering:

```typescript
  // Node circles — color by entity type
  nodeGroup.append('circle')
    .attr('r', (d: any) => getNodeRadius(d.connectionCount ?? 0))
    .attr('fill', (d: any) => getNodeColor(d.type))
    .attr('stroke', (d: any) => highlighted.has(d.id) ? '#fff' : 'none')
    .attr('stroke-width', 2)

  // Node labels
  nodeGroup.append('text')
    .text((d: any) => d.label)
    .attr('text-anchor', 'middle')
    .attr('dy', (d: any) => getNodeRadius(d.connectionCount ?? 0) + 12)
    .attr('fill', '#94a3b8')
    .attr('font-size', '10px')
```

Update edge rendering:

```typescript
  // Edge lines — style by namespace
  linkGroup.append('line')
    .attr('stroke', (d: any) => getEdgeStyle(d.namespace).stroke)
    .attr('stroke-width', (d: any) => getEdgeStyle(d.namespace).strokeWidth)
    .attr('stroke-dasharray', (d: any) => getEdgeStyle(d.namespace).dashArray ?? '')
    .attr('opacity', (d: any) => getEdgeStyle(d.namespace).opacity)
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/app/admin/knowledge-tree/components/ForceGraph.tsx
git commit -m "feat(trustgraph-ui): 2D ForceGraph uses TrustGraph type-based rendering"
```

---

## Task 8: Emma Chat — Message Type Badges

Add visual badges for different SSE event types in chat messages.

**Files:**
- Modify: `frontend/src/components/emma-chat/EmmaMarkdown.tsx`

- [ ] **Step 1: Add message type badge rendering**

At the top of `EmmaMarkdown.tsx`, add the badge config:

```typescript
import { Badge } from '@/components/ui/badge'
import {
  IconBrain,
  IconEye,
  IconCircleCheck,
  IconShield,
} from '@tabler/icons-react'

const MESSAGE_TYPE_BADGES: Record<string, {
  label: string
  icon: typeof IconBrain
  color: string
  bgColor: string
}> = {
  agent_reasoning: {
    label: 'Pensando',
    icon: IconBrain,
    color: 'text-blue-400',
    bgColor: 'bg-blue-500/10 border-blue-500/20',
  },
  tool_call: {
    label: 'Observando',
    icon: IconEye,
    color: 'text-amber-400',
    bgColor: 'bg-amber-500/10 border-amber-500/20',
  },
  tool_result: {
    label: 'Observando',
    icon: IconEye,
    color: 'text-amber-400',
    bgColor: 'bg-amber-500/10 border-amber-500/20',
  },
  final_answer: {
    label: 'Respuesta',
    icon: IconCircleCheck,
    color: 'text-emerald-400',
    bgColor: 'bg-emerald-500/10 border-emerald-500/20',
  },
  claim_verification: {
    label: 'Verificando',
    icon: IconShield,
    color: 'text-violet-400',
    bgColor: 'bg-violet-500/10 border-violet-500/20',
  },
}
```

Add a `MessageTypeBadge` component:

```tsx
function MessageTypeBadge({ type }: { type?: string }) {
  if (!type) return null
  const config = MESSAGE_TYPE_BADGES[type]
  if (!config) return null

  const Icon = config.icon
  return (
    <div className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs border ${config.bgColor} ${config.color} mb-2`}>
      <Icon size={12} />
      <span>{config.label}</span>
    </div>
  )
}
```

Then in the main `EmmaMarkdown` component, render it conditionally:

```tsx
export function EmmaMarkdown({ content, className, forceLight, messageType }: EmmaMarkdownProps & { messageType?: string }) {
  return (
    <div>
      <MessageTypeBadge type={messageType} />
      {/* existing ReactMarkdown rendering */}
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/emma-chat/EmmaMarkdown.tsx
git commit -m "feat(trustgraph-ui): message type badges — thinking/observing/answer/verifying"
```

---

## Task 9: Emma Chat — Entity Tags

Clickable entity tags below Graph RAG responses that navigate to the knowledge graph.

**Files:**
- Create: `frontend/src/components/emma-chat/EntityTags.tsx`
- Modify: `frontend/src/components/emma-chat/hooks/useMessageConverter.ts`

- [ ] **Step 1: Create EntityTags component**

```tsx
// frontend/src/components/emma-chat/EntityTags.tsx
'use client'

import { useRouter } from 'next/navigation'
import { ENTITY_TYPE_COLORS } from '@/app/knowledge-graph/components/explainability-theme'

export interface EntityTag {
  uri: string
  label: string
  type: string
}

interface EntityTagsProps {
  entities: EntityTag[]
}

export function EntityTags({ entities }: EntityTagsProps) {
  const router = useRouter()

  if (!entities.length) return null

  function navigateToGraph(uri: string) {
    // Navigate to knowledge graph with entity as seed
    const encoded = encodeURIComponent(uri)
    router.push(`/knowledge-graph?entity=${encoded}`)
  }

  return (
    <div className="flex flex-wrap gap-1.5 mt-2">
      {entities.map((entity) => (
        <button
          key={entity.uri}
          onClick={() => navigateToGraph(entity.uri)}
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs
                     bg-cyan-500/10 text-cyan-400 hover:bg-cyan-500/20
                     border border-cyan-500/20 transition-colors"
        >
          <span
            className="h-1.5 w-1.5 rounded-full"
            style={{ backgroundColor: ENTITY_TYPE_COLORS[entity.type] ?? '#6b7280' }}
          />
          {entity.label}
        </button>
      ))}
    </div>
  )
}
```

- [ ] **Step 2: Extract entities from tool results in useMessageConverter**

In `frontend/src/components/emma-chat/hooks/useMessageConverter.ts`, add entity extraction logic. After the existing message conversion, look for `graph_rag` tool results in the SSE data:

```typescript
// Extract entities from graph_rag tool results
function extractEntityTags(message: any): EntityTag[] {
  const entities: EntityTag[] = []

  // Look for graph_rag data in the message metadata/tool results
  const toolResults = message.tool_results ?? message.data?.tool_results ?? []
  for (const result of toolResults) {
    if (result.tool_name === 'graph_rag' && result.data?.entities) {
      for (const entity of result.data.entities.slice(0, 8)) {
        entities.push({
          uri: entity.entity_uri ?? '',
          label: entity.label ?? '',
          type: entity.entity_type ?? 'other',
        })
      }
    }
  }

  return entities
}
```

Add `entityTags` to the converted message type and populate it during conversion.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/emma-chat/EntityTags.tsx \
       frontend/src/components/emma-chat/hooks/useMessageConverter.ts
git commit -m "feat(trustgraph-ui): clickable entity tags in chat → graph navigation"
```

---

## Task 10: Page-Level Integration

Wire everything together in the page components.

**Files:**
- Modify: `frontend/src/app/knowledge-graph/page.tsx`
- Modify: `frontend/src/app/admin/knowledge-tree/page.tsx`

- [ ] **Step 1: Update Knowledge Graph page**

Update the page to:
1. Read `?entity=` query param for deep-linking from chat
2. Pass `properties` and `contradictions` to `NodeDetailsDrawer`
3. Wire up `EntitySearchBar` → `loadGraph()`

```typescript
  // Read entity query param for deep-linking
  const searchParams = useSearchParams()
  const initialEntity = searchParams.get('entity')

  useEffect(() => {
    if (initialEntity) {
      loadGraph([decodeURIComponent(initialEntity)])
    } else {
      // Load full graph overview via stats
      loadGraph()
    }
  }, [initialEntity])
```

- [ ] **Step 2: Update Knowledge Tree page**

Apply the same data model transformation — call `getTripleNeighbors` instead of the old `getGraphStructure`, and pass TrustGraph-typed data to `ForceGraph`.

- [ ] **Step 3: Verify both pages render**

Run: `cd frontend && npm run build`
Expected: Build succeeds with no TypeScript errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/knowledge-graph/page.tsx \
       frontend/src/app/admin/knowledge-tree/page.tsx
git commit -m "feat(trustgraph-ui): page integration — deep-linking + TrustGraph data model"
```

---

## Summary — Execution Order

| Task | Depends on | Est. Time |
|------|-----------|-----------|
| 1. Entity search service | Backend Task 2 | 5 min |
| 2. KT service updates | Backend Task 1 | 15 min |
| 3. Theme colors | — | 10 min |
| 4. Entity search bar | Tasks 1, 3 | 10 min |
| 5. 3D graph update | Tasks 2, 3, 4 | 20 min |
| 6. NodeDetailsDrawer | Tasks 2, 3 | 15 min |
| 7. 2D graph update | Tasks 2, 3 | 15 min |
| 8. Chat badges | — | 10 min |
| 9. Chat entity tags | Task 3 | 10 min |
| 10. Page integration | Tasks 4-9 | 15 min |

**Parallelizable**: Tasks 1-3 and 8 are independent. Tasks 4-7 and 9 can proceed once their dependencies complete.
