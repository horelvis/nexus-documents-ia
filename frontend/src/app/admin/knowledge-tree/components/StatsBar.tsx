"use client"

import { IconFileText, IconUser, IconScale, IconCategory } from "@tabler/icons-react"
import type { TreeStats, LegalStats } from "@/lib/services/knowledge-tree.service"

interface StatsBarProps {
  treeStats?: TreeStats | null
  legalStats?: LegalStats | null
  nodeCount: number
  edgeCount: number
}

export function StatsBar({ treeStats, legalStats, nodeCount, edgeCount }: StatsBarProps) {
  return (
    <div className="flex items-center gap-3">
      {treeStats && (
        <>
          <StatPill icon={IconFileText} value={treeStats.total_documents} label="docs" color="blue" />
          <StatPill icon={IconUser} value={treeStats.total_folders} label="carpetas" color="amber" />
          <StatPill icon={IconCategory} value={Object.keys(treeStats.types_breakdown).length} label="tipos" color="emerald" />
        </>
      )}
      {legalStats && (
        <>
          <StatPill icon={IconScale} value={legalStats.total_laws} label="leyes" color="cyan" />
          <StatPill icon={IconCategory} value={Object.keys(legalStats.domains || {}).length} label="dominios" color="amber" />
        </>
      )}
      <div className="h-3 w-px bg-slate-700/50" />
      <span className="text-[10px] text-slate-600 tabular-nums">
        {nodeCount} nodos · {edgeCount} aristas
      </span>
    </div>
  )
}

function StatPill({
  icon: Icon,
  value,
  label,
  color,
}: {
  icon: typeof IconFileText
  value: number
  label: string
  color: "blue" | "amber" | "emerald" | "cyan"
}) {
  const colorMap = {
    blue: "text-blue-400 bg-blue-500/10",
    amber: "text-amber-400 bg-amber-500/10",
    emerald: "text-emerald-400 bg-emerald-500/10",
    cyan: "text-cyan-400 bg-cyan-500/10",
  }

  return (
    <span className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] tabular-nums ${colorMap[color]}`}>
      <Icon className="h-3 w-3" />
      {value} <span className="text-slate-500">{label}</span>
    </span>
  )
}
