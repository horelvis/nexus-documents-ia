'use client'

import { useState } from 'react'
import { IconChevronDown, IconChevronRight, IconFileText } from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import type { SourceEvidenceItem } from '@/lib/types/emma'

function ConfidenceBadge({ confidence }: { confidence?: number }) {
  if (confidence == null) return null
  const color = confidence >= 0.8
    ? 'bg-green-500/20 text-green-400 border-green-500/30'
    : confidence >= 0.5
      ? 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30'
      : 'bg-red-500/20 text-red-400 border-red-500/30'
  return (
    <span className={cn('text-[10px] px-1.5 py-0.5 rounded border font-mono', color)}>
      {(confidence * 100).toFixed(0)}%
    </span>
  )
}

interface SourceEvidenceProps {
  sources: SourceEvidenceItem[]
  onDocumentClick?: (documentId: string) => void
}

export function SourceEvidence({ sources, onDocumentClick }: SourceEvidenceProps) {
  const [isExpanded, setIsExpanded] = useState(false)

  if (!sources || sources.length === 0) return null

  return (
    <div className="mt-2 rounded-lg border border-border/50 bg-muted/30">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex w-full items-center gap-2 px-3 py-2 text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        {isExpanded ? (
          <IconChevronDown className="h-3.5 w-3.5" />
        ) : (
          <IconChevronRight className="h-3.5 w-3.5" />
        )}
        <IconFileText className="h-3.5 w-3.5" />
        <span className="font-medium">Fuentes consultadas ({sources.length})</span>
      </button>

      {isExpanded && (
        <div className="px-3 pb-3 space-y-2">
          {sources.map((src, idx) => (
            <div key={idx} className="flex items-start gap-2 text-xs">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => onDocumentClick?.(src.document_id)}
                    className="font-medium text-primary hover:underline truncate"
                  >
                    {src.document_title}
                  </button>
                  <span className="text-muted-foreground shrink-0">chunk {src.chunk_offset}</span>
                  <ConfidenceBadge confidence={src.confidence} />
                </div>
                <p className="text-muted-foreground mt-0.5 line-clamp-1">
                  {src.relationship}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
