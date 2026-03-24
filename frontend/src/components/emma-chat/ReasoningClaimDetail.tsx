'use client'

import { IconX } from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ExplainNode, NODE_COLORS } from '@/app/knowledge-graph/components/explainability-theme'

interface ReasoningClaimDetailProps {
  node: ExplainNode
  onClose: () => void
}

const TYPE_LABELS: Record<ExplainNode['type'], string> = {
  entity: 'Entidad',
  document: 'Documento',
  claim: 'Afirmación',
  law: 'Ley',
  contradiction: 'Contradicción',
}

export default function ReasoningClaimDetail({ node, onClose }: ReasoningClaimDetailProps) {
  const color = NODE_COLORS[node.type] ?? '#94a3b8'
  const typeLabel = TYPE_LABELS[node.type] ?? node.type
  const excerpt = node.properties?.excerpt as string | undefined
  const confidence = node.properties?.confidence as number | undefined
  const domain = node.properties?.domain as string | undefined
  const boeId = node.properties?.boe_id as string | undefined

  return (
    <div
      className={cn(
        'absolute bottom-4 right-4 z-20 w-80 rounded-xl border border-slate-700/60',
        'bg-slate-900/90 backdrop-blur-md shadow-2xl'
      )}
    >
      {/* Header */}
      <div className="flex items-start gap-2 p-3 border-b border-slate-700/50">
        <Badge
          className="shrink-0 text-[10px] font-bold tracking-wider border"
          style={{
            color,
            backgroundColor: `${color}1a`,
            borderColor: `${color}40`,
          }}
        >
          {typeLabel.toUpperCase()}
        </Badge>
        <span className="flex-1 text-sm font-medium text-slate-100 leading-snug line-clamp-2">{node.label}</span>
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6 shrink-0 text-slate-400 hover:text-slate-100"
          onClick={onClose}
        >
          <IconX size={14} />
        </Button>
      </div>

      {/* Body */}
      <div className="p-3 space-y-2">
        {/* Excerpt */}
        {excerpt && (
          <p className="text-xs text-slate-300 leading-relaxed line-clamp-4">{excerpt}</p>
        )}

        {/* Meta */}
        <div className="flex flex-wrap gap-1.5">
          {domain && (
            <Badge variant="secondary" className="text-[10px]">
              {domain}
            </Badge>
          )}
          {boeId && (
            <Badge variant="outline" className="text-[10px] font-mono">
              {boeId}
            </Badge>
          )}
        </div>

        {/* Confidence bar */}
        {confidence != null && (
          <div className="flex items-center gap-2 pt-1">
            <span className="text-[10px] text-slate-500 shrink-0">Confianza</span>
            <div className="flex-1 h-1.5 rounded-full bg-slate-700 overflow-hidden">
              <div
                className="h-full rounded-full transition-all"
                style={{
                  width: `${Math.round(confidence * 100)}%`,
                  backgroundColor: color,
                }}
              />
            </div>
            <span className="text-[10px] text-slate-400 shrink-0">{Math.round(confidence * 100)}%</span>
          </div>
        )}
      </div>
    </div>
  )
}
