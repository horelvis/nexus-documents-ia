"use client"

import { KIND_COLORS, KIND_LABELS, LAW_DOMAIN_COLORS } from "./graph-theme"
import type { GraphViewMode } from "@/lib/services/knowledge-tree.service"

export function GraphLegend({ viewMode }: { viewMode: GraphViewMode }) {
  const entries = viewMode === "legal"
    ? Object.entries(LAW_DOMAIN_COLORS).map(([key, color]) => ({ label: key, color }))
    : Object.entries(KIND_COLORS)
        .filter(([k]) => k !== "unknown")
        .map(([key, color]) => ({ label: KIND_LABELS[key as keyof typeof KIND_LABELS], color }))

  return (
    <div className="kt-legend">
      {entries.map(({ label, color }) => (
        <div key={label} className="flex items-center gap-1.5">
          <span
            className="h-2 w-2 rounded-full shrink-0"
            style={{ backgroundColor: color, boxShadow: `0 0 4px ${color}40` }}
          />
          <span className="text-[10px] text-slate-500 capitalize">{label}</span>
        </div>
      ))}
    </div>
  )
}
