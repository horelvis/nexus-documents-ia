'use client'

import { NODE_COLORS } from './explainability-theme'

interface ExplainabilityStats {
  total_entities: number
  total_documents: number
  total_claims: number
  total_laws: number
  total_contradictions: number
}

interface ExplainabilityStatsBarProps {
  stats: ExplainabilityStats
}

interface StatItemProps {
  color: string
  label: string
  count: number
}

function StatItem({ color, label, count }: StatItemProps) {
  return (
    <div className="flex items-center gap-1.5">
      <span
        className="h-2 w-2 rounded-full shrink-0"
        style={{ backgroundColor: color, boxShadow: `0 0 4px ${color}60` }}
      />
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-xs font-medium tabular-nums">{count}</span>
    </div>
  )
}

export function ExplainabilityStatsBar({ stats }: ExplainabilityStatsBarProps) {
  return (
    <div className="flex items-center gap-4 px-4 py-2 border-b bg-background/80 backdrop-blur-sm flex-wrap">
      <StatItem color={NODE_COLORS.entity} label="Entities" count={stats.total_entities} />
      <div className="h-3 w-px bg-border" />
      <StatItem color={NODE_COLORS.document} label="Documents" count={stats.total_documents} />
      <div className="h-3 w-px bg-border" />
      <StatItem color={NODE_COLORS.claim} label="Claims" count={stats.total_claims} />
      <div className="h-3 w-px bg-border" />
      <StatItem color={NODE_COLORS.law} label="Laws" count={stats.total_laws} />
      <div className="h-3 w-px bg-border" />
      <StatItem color={NODE_COLORS.contradiction} label="Contradictions" count={stats.total_contradictions} />
    </div>
  )
}
