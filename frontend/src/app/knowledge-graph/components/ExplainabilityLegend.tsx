'use client'

import { NODE_COLORS, type ExplainNodeType } from './explainability-theme'

const NODE_TYPE_LABELS: Record<ExplainNodeType, string> = {
  entity: 'Entity',
  document: 'Document',
  claim: 'Claim',
  law: 'Law',
  contradiction: 'Contradiction',
}

const NODE_TYPES: ExplainNodeType[] = ['entity', 'document', 'claim', 'law', 'contradiction']

export function ExplainabilityLegend() {
  return (
    <div className="absolute bottom-4 left-4 z-10 rounded-lg border bg-background/80 backdrop-blur-sm px-3 py-2.5 shadow-md">
      <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider mb-2">
        Node Types
      </p>
      <div className="space-y-1.5">
        {NODE_TYPES.map((type) => (
          <div key={type} className="flex items-center gap-2">
            <span
              className={`h-2.5 w-2.5 rounded-full shrink-0${type === 'contradiction' ? ' animate-pulse' : ''}`}
              style={{
                backgroundColor: NODE_COLORS[type],
                boxShadow: `0 0 6px ${NODE_COLORS[type]}80`,
              }}
            />
            <span className="text-xs text-foreground/80">{NODE_TYPE_LABELS[type]}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
