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
}
