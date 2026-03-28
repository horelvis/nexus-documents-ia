// ── Legacy types (kept for backward compat) ──

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

// ── Backward compat — aliases for old consumers ──

export const NODE_COLORS = ENTITY_TYPE_COLORS

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
  return ENTITY_TYPE_COLORS[node.type] || '#94a3b8'
}

export function getEdgeColor(link: ExplainLink): string {
  return EDGE_COLORS[link.type] || '#64748b'
}

export function getNodeSize(node: ExplainNode): number {
  return NODE_SIZE[node.type] || 6
}
