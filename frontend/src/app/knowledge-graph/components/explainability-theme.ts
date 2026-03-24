export type ExplainNodeType = 'entity' | 'document' | 'claim' | 'law' | 'contradiction'

export interface ExplainNode {
  id: string
  type: ExplainNodeType
  label: string
  properties: Record<string, unknown>
  x?: number; y?: number; z?: number
  fx?: number; fy?: number; fz?: number
}

export interface ExplainLink {
  id: string
  source: string | ExplainNode
  target: string | ExplainNode
  type: string
  properties: Record<string, unknown>
}

export const NODE_COLORS: Record<ExplainNodeType, string> = {
  entity: '#06b6d4', document: '#f59e0b', claim: '#22c55e',
  law: '#a855f7', contradiction: '#ef4444',
}

export const NODE_GLOW: Record<ExplainNodeType, string> = {
  entity: '#22d3ee', document: '#fbbf24', claim: '#4ade80',
  law: '#c084fc', contradiction: '#f87171',
}

export const EDGE_COLORS: Record<string, string> = {
  MENTIONED_IN: '#64748b', EXTRACTED_FROM: '#3b82f6',
  CONTRADICTS: '#ef4444', SUPPORTS: '#22c55e',
  RELATED_TO: '#94a3b8', REFERENCES: '#8b5cf6',
  MODIFIES: '#f97316', DEROGATES: '#dc2626',
}

export const NODE_SIZE: Record<ExplainNodeType, number> = {
  entity: 6, document: 8, claim: 4, law: 10, contradiction: 5,
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
