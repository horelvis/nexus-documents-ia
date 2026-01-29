"use client"

/**
 * Knowledge Tree Service
 *
 * Types and service for the Knowledge Tree visualization page.
 * Fetches graph structure from the backend proxy to knowledge-tree-service.
 */

export interface GraphNode {
  id: string
  label: string
  node_type: "folder" | "document"
  // folder-specific
  folder_type?: string
  doc_count?: number
  path?: string
  // document-specific
  semantic_type?: string
  file_path?: string
}

export interface GraphEdge {
  id: string
  source: string
  target: string
}

export interface GraphStructure {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface TreeStats {
  total_documents: number
  total_folders: number
  types_breakdown: Record<string, number>
  domains_breakdown: Record<string, number>
}
