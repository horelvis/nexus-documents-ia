/**
 * Knowledge Tree — Observatory Theme
 *
 * Color system, node sizing, and visual constants for the graph visualization.
 * Deep space aesthetic: void background, constellation-like nodes.
 */

import type { GraphNode, NodeKind } from "@/lib/services/knowledge-tree.service"
import { getNodeKind } from "@/lib/services/knowledge-tree.service"
import type { SimulationNodeDatum, SimulationLinkDatum } from "d3-force"

// ── D3 simulation types ──

export interface SimNode extends SimulationNodeDatum {
  id: string
  label: string
  name: string
  kind: NodeKind
  properties: Record<string, unknown>
}

export interface SimLink extends SimulationLinkDatum<SimNode> {
  id: string
  edgeLabel: string
  properties: Record<string, unknown>
}

// ── Color system ──

/** Node colors by kind — each type is a distinct "star class" */
const KIND_COLORS: Record<NodeKind, string> = {
  document: "#3b82f6",     // Blue — steady, reliable
  person: "#f59e0b",       // Amber — warm, human
  law: "#06b6d4",          // Cyan — sharp, authoritative
  entity_type: "#22c55e",  // Emerald — structural
  memory: "#a855f7",       // Violet — abstract
  folder: "#f97316",       // Orange — container
  unknown: "#64748b",      // Slate — neutral
}

/** Glow color (brighter variant) for hover/highlight */
const KIND_GLOW: Record<NodeKind, string> = {
  document: "#60a5fa",
  person: "#fbbf24",
  law: "#22d3ee",
  entity_type: "#4ade80",
  memory: "#c084fc",
  folder: "#fb923c",
  unknown: "#94a3b8",
}

/** Domain-specific colors for LegalLaw nodes */
const LAW_DOMAIN_COLORS: Record<string, string> = {
  labor: "#ef4444",
  fiscal: "#f59e0b",
  privacy: "#8b5cf6",
  mercantile: "#06b6d4",
  civil: "#3b82f6",
  administrative: "#64748b",
  compliance: "#f97316",
  ip: "#ec4899",
  commerce: "#22c55e",
  real_estate: "#14b8a6",
  education: "#a855f7",
  general: "#94a3b8",
}

export function getNodeColor(node: SimNode): string {
  if (node.kind === "law") {
    const domain = (node.properties.domain as string) || "general"
    return LAW_DOMAIN_COLORS[domain] || LAW_DOMAIN_COLORS.general
  }
  return KIND_COLORS[node.kind]
}

export function getNodeGlow(node: SimNode): string {
  return KIND_GLOW[node.kind]
}

export function getNodeRadius(node: SimNode): number {
  switch (node.kind) {
    case "law": return 12
    case "person": return 10
    case "folder": {
      const count = (node.properties.doc_count as number) || 0
      return Math.max(8, Math.min(20, 8 + Math.sqrt(count) * 2))
    }
    case "entity_type": return 8
    case "memory": return 5
    case "document": return 6
    default: return 5
  }
}

// ── TrustGraph entity type colors (same palette as 3D) ──

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

export function getTrustGraphNodeColor(type: string): string {
  return ENTITY_TYPE_COLORS[type] ?? ENTITY_TYPE_COLORS.other
}

export function getTrustGraphNodeRadius(connectionCount: number): number {
  return 6 + Math.log(connectionCount + 1) * 3
}

// ── Edge styling (legacy label-based) ──

const EDGE_STYLES: Record<string, { dash: string; opacity: number }> = {
  CONTAINED_IN: { dash: "none", opacity: 0.3 },
  CONTAINS: { dash: "none", opacity: 0.25 },
  MENTIONED_IN: { dash: "none", opacity: 0.4 },
  RELATED_TO: { dash: "2 2", opacity: 0.2 },
  BELONGS_TO: { dash: "4 2", opacity: 0.2 },
  REFERENCES_LAW: { dash: "4 2", opacity: 0.35 },
  ASOCIADO_A: { dash: "none", opacity: 0.35 },
  APLICA: { dash: "4 2", opacity: 0.3 },
  INSTANCE_OF: { dash: "2 2", opacity: 0.2 },
  HAS_MEMORY: { dash: "1 3", opacity: 0.15 },
  MODIFIES: { dash: "6 2", opacity: 0.4 },
  DEROGATES: { dash: "4 2", opacity: 0.4 },
  REFERENCES: { dash: "none", opacity: 0.25 },
}

export function getEdgeStyle(label: string) {
  return EDGE_STYLES[label] || { dash: "none", opacity: 0.2 }
}

// ── TrustGraph edge styles by namespace ──

export const NAMESPACE_EDGE_STYLES: Record<string, {
  stroke: string
  strokeWidth: number
  dashArray?: string
  opacity: number
}> = {
  core: { stroke: '#94a3b8', strokeWidth: 1.5, opacity: 0.6 },
  legal: { stroke: '#22d3ee', strokeWidth: 2.5, opacity: 0.8 },
  prov: { stroke: '#475569', strokeWidth: 1, dashArray: '2,4', opacity: 0.3 },
}

export function getNamespaceEdgeStyle(namespace: string) {
  return NAMESPACE_EDGE_STYLES[namespace] ?? NAMESPACE_EDGE_STYLES.core
}

// ── Converters: API response → D3 sim data ──

/**
 * Convert API nodes to D3 sim nodes.
 * Handles both formats:
 *  - /tree/graph/structure returns { id, label (display name), node_type, ... }
 *  - /tree/graph/subgraph returns { id, label (vertex type), name (display), properties }
 */
export function apiNodesToSim(nodes: Record<string, any>[]): SimNode[] {
  return nodes
    .filter((n) => n.id)
    .map((n) => {
      // Detect format: if node_type exists, it's the structure format
      const isStructureFormat = "node_type" in n

      const vertexLabel = isStructureFormat
        ? (n.node_type === "document" ? "structural_document" : n.node_type === "folder" ? "Folder" : n.node_type === "law" ? "LegalLaw" : n.node_type)
        : (n.label || "unknown")

      const displayName = isStructureFormat
        ? (n.label || n.id)
        : (n.name || n.label || n.id)

      // Merge flat fields into properties for structure format
      const properties = n.properties || {}
      if (isStructureFormat) {
        if (n.folder_type) properties.folder_type = n.folder_type
        if (n.semantic_type) properties.semantic_type = n.semantic_type
        if (n.doc_count) properties.doc_count = n.doc_count
        if (n.domain) properties.domain = n.domain
        if (n.status) properties.status = n.status
        if (n.path) properties.path = n.path
      }

      return {
        id: n.id,
        label: vertexLabel,
        name: displayName,
        kind: getNodeKindFromLabel(vertexLabel),
        properties,
      } as SimNode
    })
}

function getNodeKindFromLabel(label: string): NodeKind {
  switch (label) {
    case "structural_document":
    case "document":
      return "document"
    case "Persona":
    case "person":
      return "person"
    case "LegalLaw":
    case "law":
      return "law"
    case "EntityType":
    case "Entity":
    case "entity_type":
      return "entity_type"
    case "DocumentMemory": return "memory"
    case "Folder":
    case "folder":
      return "folder"
    default: return "unknown"
  }
}

/**
 * Convert API edges to D3 sim links.
 * Handles both formats:
 *  - /tree/graph/structure returns { source, target }
 *  - /tree/graph/subgraph returns { source_id, target_id }
 */
export function apiEdgesToSim(
  edges: Record<string, any>[],
  nodeIds?: Set<string>,
): SimLink[] {
  return edges
    .map((e, i) => {
      const src = e.source_id ?? e.source
      const tgt = e.target_id ?? e.target
      if (!src || !tgt) return null
      if (nodeIds && (!nodeIds.has(src) || !nodeIds.has(tgt))) return null
      return {
        id: e.id || `edge-${i}`,
        source: src,
        target: tgt,
        edgeLabel: e.label || "",
        properties: e.properties || {},
      } as SimLink
    })
    .filter((e): e is SimLink => e !== null)
}

// ── Kind labels for UI ──

export const KIND_LABELS: Record<NodeKind, string> = {
  document: "Documento",
  person: "Persona",
  law: "Ley",
  entity_type: "Tipo",
  memory: "Memoria",
  folder: "Carpeta",
  unknown: "Otro",
}

// ── TrustGraph → SimNode/SimLink converters ──

import type { TrustGraphNode, TrustGraphEdge } from "@/lib/services/knowledge-tree.service"

export function trustGraphNodesToSim(nodes: TrustGraphNode[]): SimNode[] {
  return nodes.map((n) => ({
    id: n.id,
    label: n.type,
    name: n.label,
    kind: (n.type === "person" ? "person" : n.type === "law" ? "law" : n.type === "document" ? "document" : "entity_type") as NodeKind,
    properties: {
      definition: n.definition,
      connectionCount: n.connectionCount,
      entityType: n.type,
    },
  }))
}

export function trustGraphEdgesToSim(edges: TrustGraphEdge[]): SimLink[] {
  return edges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    edgeLabel: e.predicate,
    properties: { namespace: e.namespace, weight: e.weight },
  }))
}

export { KIND_COLORS, LAW_DOMAIN_COLORS }
