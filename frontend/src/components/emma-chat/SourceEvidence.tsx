'use client'

import { useState } from 'react'
import { IconChevronDown, IconChevronRight, IconFileText, IconQuote } from '@tabler/icons-react'
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

function ChunkPreview({ text }: { text: string }) {
  return (
    <div className="mt-1.5 rounded border border-border/40 bg-background/60 px-2.5 py-2">
      <div className="flex items-start gap-1.5">
        <IconQuote className="h-3 w-3 mt-0.5 text-muted-foreground/60 shrink-0" />
        <p className="text-[11px] leading-relaxed text-muted-foreground italic">
          {text}
        </p>
      </div>
    </div>
  )
}

interface SourceEvidenceProps {
  sources: SourceEvidenceItem[]
  onDocumentClick?: (documentId: string) => void
}

export function SourceEvidence({ sources, onDocumentClick }: SourceEvidenceProps) {
  const [isExpanded, setIsExpanded] = useState(false)
  const [expandedChunks, setExpandedChunks] = useState<Set<number>>(new Set())

  if (!sources || sources.length === 0) return null

  const toggleChunk = (idx: number) => {
    setExpandedChunks(prev => {
      const next = new Set(prev)
      if (next.has(idx)) {
        next.delete(idx)
      } else {
        next.add(idx)
      }
      return next
    })
  }

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
            <div key={idx} className="text-xs">
              <div className="flex items-center gap-2">
                <button
                  onClick={() => onDocumentClick?.(src.document_id)}
                  className="font-medium text-primary hover:underline truncate"
                >
                  {src.document_title}
                </button>
                <button
                  onClick={() => src.chunk_text && toggleChunk(idx)}
                  className={cn(
                    'text-muted-foreground shrink-0',
                    src.chunk_text && 'hover:text-foreground cursor-pointer underline decoration-dotted'
                  )}
                >
                  {src.page_start && src.page_start > 0
                    ? src.page_end && src.page_end !== src.page_start
                      ? `pág. ${src.page_start}–${src.page_end}`
                      : `pág. ${src.page_start}`
                    : `sección ${src.chunk_offset}`}
                </button>
                <ConfidenceBadge confidence={src.confidence} />
              </div>
              <p className="text-muted-foreground mt-0.5 line-clamp-1">
                {src.relationship}
              </p>
              {src.chunk_text && expandedChunks.has(idx) && (
                <ChunkPreview text={src.chunk_text} />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
