"use client"

/**
 * Knowledge Tree Service
 *
 * Types and API client for the Knowledge Tree visualization.
 * Consumes endpoints from knowledge-tree-service (port 8011)
 * proxied through /api/v1/knowledge-tree → /tree/...
 */

// ── Graph Data Types (Phase 6 unified graph) ──

export interface GraphNodeProperties {
  semantic_type?: string
  domain?: string
  quality_score?: number
  associated_person?: string
  boe_id?: string
  status?: string
  [key: string]: unknown
}

export interface GraphNode {
  id: string
  /** Vertex label: structural_document | Persona | LegalLaw | EntityType | DocumentMemory */
  label: string
  /** Display name */
  name: string
  properties: GraphNodeProperties
}

export interface GraphEdgeProperties {
  confidence?: string
  source?: string
  article?: string
  [key: string]: unknown
}

export interface GraphEdge {
  source_id: string
  target_id: string
  /** Relationship: ASOCIADO_A | APLICA | INSTANCE_OF | HAS_MEMORY | MODIFIES | DEROGATES | REFERENCES */
  label: string
  properties: GraphEdgeProperties
}

export interface SubgraphResponse {
  nodes: GraphNode[]
  edges: GraphEdge[]
  root_entities: string[]
  pruned_count: number
}

export interface TreeStats {
  total_documents: number
  total_folders: number
  types_breakdown: Record<string, number>
  domains_breakdown: Record<string, number>
}

export interface LegalStats {
  total_laws: number
  total_edges: number
  domains: Record<string, number>
}

export interface LegalGraphStructure {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface EntitySearchResult {
  id: string
  label: string
  name: string
  properties: GraphNodeProperties
}

export interface OntologyType {
  name: string
  parent?: string
  count?: number
}

export interface OntologyHierarchy {
  types: OntologyType[]
}

export type GraphViewMode = "unified" | "legal"

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
  // ForceGraph3D adds these at runtime during simulation
  x?: number; y?: number; z?: number
  fx?: number; fy?: number; fz?: number
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

// ── Node type helpers ──

export type NodeKind = "document" | "person" | "law" | "entity_type" | "memory" | "folder" | "unknown"

export function getNodeKind(node: GraphNode): NodeKind {
  switch (node.label) {
    case "structural_document": return "document"
    case "Persona": return "person"
    case "LegalLaw": return "law"
    case "EntityType": return "entity_type"
    case "DocumentMemory": return "memory"
    default: return "unknown"
  }
}

// ── API Client ──

import { apiClient } from "@/lib/api-client"

const BASE = "/knowledge-tree"

export const knowledgeTreeApi = {
  /** GET /tree/stats — Graph statistics */
  async getStats() {
    return apiClient.get<TreeStats>(`${BASE}/tree/stats`)
  },

  /** GET /tree/graph/structure — Full graph structure (all nodes + edges) */
  async getGraphStructure() {
    return apiClient.get<SubgraphResponse>(`${BASE}/tree/graph/structure`)
  },

  /** POST /tree/graph/subgraph — Multi-hop subgraph for a specific entity */
  async getSubgraph(entity: string, maxHops = 2, maxNodes = 100) {
    return apiClient.post<SubgraphResponse>(`${BASE}/tree/graph/subgraph`, {
      entity,
      max_hops: maxHops,
      max_nodes: maxNodes,
    })
  },

  /** GET /tree/entities/search — Search entities in the graph */
  async searchEntities(query: string, limit = 20) {
    return apiClient.get<EntitySearchResult[]>(
      `${BASE}/tree/entities/search?q=${encodeURIComponent(query)}&limit=${limit}`
    )
  },

  /** GET /tree/graph/document-ids — Document IDs in the graph */
  async getDocumentIds() {
    return apiClient.get<string[]>(`${BASE}/tree/graph/document-ids`)
  },

  /** POST /tree/graph/query — Direct Cypher query */
  async cypherQuery(query: string) {
    return apiClient.post<unknown>(`${BASE}/tree/graph/query`, { query })
  },

  /** GET /legal/stats — Legal graph stats */
  async getLegalStats() {
    return apiClient.get<LegalStats>(`${BASE}/legal/stats`)
  },

  /** GET /legal/graph/structure — Full legal graph (nodes + edges for D3) */
  async getLegalGraphStructure() {
    return apiClient.get<LegalGraphStructure>(`${BASE}/legal/graph/structure`)
  },

  /** GET /ontology/types — Ontology types */
  async getOntologyTypes() {
    return apiClient.get<OntologyType[]>(`${BASE}/ontology/types`)
  },

  /** GET /ontology/hierarchy — Full type hierarchy */
  async getOntologyHierarchy() {
    return apiClient.get<OntologyHierarchy>(`${BASE}/ontology/hierarchy`)
  },

  /** GET /ontology/document-context/{id} — Ontological context for a document */
  async getDocumentContext(documentId: string) {
    return apiClient.get<unknown>(`${BASE}/ontology/document-context/${documentId}`)
  },

  // ── TrustGraph Phase 2 ──

  /** GET /triples/top-entities — Entities with highest degree centrality */
  async getTopEntities(
    tenantId: string,
    limit: number = 10,
  ): Promise<Array<{ uri: string; degree: number }>> {
    try {
      const response = await apiClient.get<Array<{ uri: string; degree: number }>>(
        `${BASE}/triples/top-entities?tenant_id=${encodeURIComponent(tenantId)}&limit=${limit}`,
      )
      return response.data ?? []
    } catch (error) {
      console.error('Top entities failed:', error)
      return []
    }
  },

  /** POST /triples/neighbors — BFS subgraph via triple store */
  async getTripleNeighbors(
    tenantId: string,
    seedUris: string[],
    maxHops: number = 2,
    maxEdges: number = 150,
  ): Promise<TripleNeighborsResponse> {
    try {
      const response = await apiClient.post<TripleNeighborsResponse>(
        `${BASE}/triples/neighbors`,
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
  },

  /** POST /triples/query — Get all triples for a specific entity */
  async getEntityTriples(
    tenantId: string,
    entityUri: string,
  ): Promise<Triple[]> {
    try {
      const response = await apiClient.post<{ triples: Triple[] }>(
        `${BASE}/triples/query`,
        { tenant_id: tenantId, subject_uri: entityUri, limit: 100 },
      )
      return response.data?.triples ?? []
    } catch (error) {
      console.error('Entity triples failed:', error)
      return []
    }
  },
}

// ── TrustGraph data transformation ──

/**
 * Transform raw triples into force graph data.
 * Node→Node edges go into the graph; Node→Literal become properties.
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

    // Skip prov/*
    if (namespace === 'prov') continue

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
