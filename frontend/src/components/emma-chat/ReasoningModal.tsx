'use client'

import { useEffect, useState, useCallback } from 'react'
import { IconX, IconClock, IconListNumbers } from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  ReasoningTimelineStep,
  explainabilityApi,
} from '@/lib/services/explainability.service'
import { ExplainNode, ExplainLink } from '@/app/knowledge-graph/components/explainability-theme'
import ReasoningTimeline from './ReasoningTimeline'
import ReasoningClaimDetail from './ReasoningClaimDetail'
import ReasoningEvidenceGraph from './ReasoningEvidenceGraph'

// --- Step type mapping ---

function mapStepType(rawType: string): ReasoningTimelineStep['type'] {
  switch (rawType) {
    case 'thinking':
    case 'analyzing':
      return 'thinking'
    case 'searching':
    case 'querying':
    case 'browsing':
    case 'search_result':
      return 'search'
    case 'reading':
    case 'doc_read':
    case 'listing':
      return 'observation'
    case 'connecting':
    case 'preparing':
      return 'tool_call'
    case 'error':
      return 'error'
    default:
      return 'thinking'
  }
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function transformSteps(rawSteps: any[]): ReasoningTimelineStep[] {
  return rawSteps.map((raw, i) => ({
    index: i,
    type: mapStepType(raw.type ?? raw.step_type ?? ''),
    content: raw.content ?? raw.text ?? raw.message ?? String(raw),
    detail: raw.detail ?? raw.tool_name ?? undefined,
    source: raw.source ?? raw.tool ?? undefined,
    timestamp_ms: raw.timestamp_ms ?? raw.elapsed_ms ?? i * 100,
    duration_ms: raw.duration_ms ?? undefined,
    confidence: raw.confidence ?? undefined,
    related_node_ids: raw.related_node_ids ?? undefined,
  }))
}

// --- Evidence graph builder ---

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function buildEvidenceGraph(sources: any[]): { nodes: ExplainNode[]; links: ExplainLink[] } {
  const seen = new Set<string>()
  const nodes: ExplainNode[] = []

  for (const src of sources) {
    const id = src.id ?? src.document_id ?? src.title ?? String(Math.random())
    if (seen.has(id)) continue
    seen.add(id)

    const type: ExplainNode['type'] =
      src.source_type === 'legislation' ? 'law' : 'document'

    nodes.push({
      id,
      type,
      label: src.title ?? src.document ?? id,
      properties: {
        excerpt: src.excerpt ?? undefined,
        confidence: src.relevance ?? src.confidence ?? undefined,
        domain: src.domain ?? undefined,
        boe_id: src.boe_id ?? undefined,
        source_document_id: src.document_id ?? undefined,
      },
    })
  }

  return { nodes, links: [] }
}

// --- Props ---

interface ReasoningModalProps {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  reasoningSteps: any[]
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  sources?: any[]
  executionTimeMs?: number
  onClose: () => void
  threadId?: string
  messageIndex?: number
}

export default function ReasoningModal({
  reasoningSteps,
  sources = [],
  executionTimeMs,
  onClose,
  threadId,
  messageIndex,
}: ReasoningModalProps) {
  const [steps] = useState<ReasoningTimelineStep[]>(() => transformSteps(reasoningSteps))
  // Initial graph from cited sources (fallback). Replaced once the
  // backend's evidence_graph (entities + edges + chunks) arrives.
  const [graphData, setGraphData] = useState<{ nodes: ExplainNode[]; links: ExplainLink[] }>(
    () => buildEvidenceGraph(sources)
  )
  const [traceStatus, setTraceStatus] = useState<{
    state: 'idle' | 'loading' | 'ok' | 'empty' | 'error' | 'no-thread'
    detail?: string
  }>({ state: threadId ? 'loading' : 'no-thread' })

  // Fetch the rich evidence_graph from /emma/explainability/trace.
  // Backend already builds it from graph_rag's source_evidence, but the
  // SSE stream collapses everything into the timeline — only the trace
  // endpoint exposes the full {nodes, edges} typed graph.
  useEffect(() => {
    if (!threadId) {
      setTraceStatus({ state: 'no-thread' })
      return
    }
    let cancelled = false
    const idx = messageIndex ?? 0
    setTraceStatus({ state: 'loading', detail: `${threadId.slice(0, 8)}…/${idx}` })
    explainabilityApi
      .getReasoningTrace(threadId, idx)
      .then((res) => {
        if (cancelled) return
        if (res.error) {
          setTraceStatus({ state: 'error', detail: `HTTP ${res.status}: ${res.error}` })
          return
        }
        const data = res.data
        const eg = data?.evidence_graph
        if (!eg || !Array.isArray(eg.nodes) || eg.nodes.length === 0) {
          setTraceStatus({ state: 'empty', detail: `${threadId.slice(0, 8)}…/${idx}` })
          return
        }
        const nodes: ExplainNode[] = eg.nodes.map((n) => ({
          id: n.id,
          type: n.type,
          label: n.label,
          properties: n.properties || {},
        }))
        const links: ExplainLink[] = (eg.edges || []).map((e) => ({
          id: e.id,
          source: e.source,
          target: e.target,
          type: e.type,
          properties: e.properties || {},
        }))
        setGraphData({ nodes, links })
        setTraceStatus({ state: 'ok', detail: `${nodes.length} nodes / ${links.length} edges` })
      })
      .catch((err) => {
        if (cancelled) return
        setTraceStatus({ state: 'error', detail: String(err).slice(0, 120) })
      })
    return () => {
      cancelled = true
    }
  }, [threadId, messageIndex])
  const [highlightedNodeIds, setHighlightedNodeIds] = useState<string[]>([])
  const [selectedNode, setSelectedNode] = useState<ExplainNode | null>(null)

  // Body scroll lock
  useEffect(() => {
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = prev }
  }, [])

  // Escape key
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const handleStepHover = useCallback((step: ReasoningTimelineStep | null) => {
    if (step?.related_node_ids?.length) {
      setHighlightedNodeIds(step.related_node_ids)
    } else {
      setHighlightedNodeIds([])
    }
  }, [])

  const handleNodeClick = useCallback((node: ExplainNode) => {
    setSelectedNode(node ?? null)
  }, [])

  const execSec = executionTimeMs != null ? (executionTimeMs / 1000).toFixed(1) : null

  return (
    <div className="fixed inset-0 z-50 bg-background/95 backdrop-blur-sm flex flex-col">
      {/* Top toolbar */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-slate-700/50 bg-slate-900/80 shrink-0">
        <h2 className="text-sm font-semibold text-slate-100">Razonamiento de Emma</h2>

        {execSec && (
          <Badge variant="secondary" className="gap-1 text-xs">
            <IconClock size={12} />
            {execSec}s
          </Badge>
        )}

        <Badge variant="secondary" className="gap-1 text-xs">
          <IconListNumbers size={12} />
          {steps.length} pasos
        </Badge>

        <Badge
          variant={traceStatus.state === 'ok' ? 'secondary' : 'outline'}
          className="gap-1 text-xs font-mono"
          title={traceStatus.detail || ''}
        >
          trace: {traceStatus.state}
          {traceStatus.detail ? ` (${traceStatus.detail})` : ''}
        </Badge>

        <Button
          variant="ghost"
          size="icon"
          className="ml-auto h-7 w-7 text-slate-400 hover:text-slate-100"
          onClick={onClose}
        >
          <IconX size={16} />
        </Button>
      </div>

      {/* Split layout */}
      <div className="flex flex-1 min-h-0">
        {/* Left: Timeline (40%) */}
        <div
          className={cn(
            'flex flex-col border-r border-slate-700/50 bg-slate-950/60',
            'overflow-hidden'
          )}
          style={{ width: '40%' }}
        >
          <div className="px-1 py-2 text-[11px] font-medium text-slate-500 uppercase tracking-wider border-b border-slate-700/30 shrink-0 px-4">
            Pasos de razonamiento
          </div>
          <div className="flex-1 overflow-y-auto p-4">
            <ReasoningTimeline
              steps={steps}
              onStepHover={handleStepHover}
            />
          </div>
        </div>

        {/* Right: Evidence Graph (60%) */}
        <div
          className="relative flex flex-col"
          style={{ width: '60%', background: '#07090f' }}
        >
          {graphData.nodes.length === 0 ? (
            <div className="flex-1 flex items-center justify-center text-slate-500 text-sm">
              No hay fuentes de evidencia disponibles.
            </div>
          ) : (
            <ReasoningEvidenceGraph
              nodes={graphData.nodes}
              links={graphData.links}
              highlightedNodeIds={highlightedNodeIds}
              onNodeClick={handleNodeClick}
              className="flex-1"
            />
          )}

          {/* Claim detail popup */}
          {selectedNode && (
            <ReasoningClaimDetail
              node={selectedNode}
              onClose={() => setSelectedNode(null)}
            />
          )}
        </div>
      </div>
    </div>
  )
}
