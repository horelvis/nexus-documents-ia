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
  node_type: "folder" | "document" | "law"
  // folder-specific
  folder_type?: string
  doc_count?: number
  path?: string
  // document-specific
  semantic_type?: string
  file_path?: string
  // law-specific (legal graph)
  domain?: string
  status?: string
  title?: string
}

export interface GraphEdge {
  id: string
  source: string
  target: string
  label?: string
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

export type GraphViewMode = "structural" | "legal"
