'use client'

import dynamic from 'next/dynamic'
import { ExplainNode, ExplainLink } from '@/app/knowledge-graph/components/explainability-theme'

const ExplainabilityGraph3D = dynamic(
  () => import('@/app/knowledge-graph/components/ExplainabilityGraph3D'),
  {
    ssr: false,
    loading: () => (
      <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
        Cargando grafo de evidencia...
      </div>
    ),
  }
)

interface ReasoningEvidenceGraphProps {
  nodes: ExplainNode[]
  links: ExplainLink[]
  highlightedNodeIds?: string[]
  onNodeClick?: (node: ExplainNode) => void
  className?: string
}

export default function ReasoningEvidenceGraph({
  nodes,
  links,
  highlightedNodeIds,
  onNodeClick,
  className,
}: ReasoningEvidenceGraphProps) {
  const highlightedSet = highlightedNodeIds && highlightedNodeIds.length > 0
    ? new Set(highlightedNodeIds)
    : null

  return (
    <div className={className} style={{ width: '100%', height: '100%' }}>
      <ExplainabilityGraph3D
        nodes={nodes}
        links={links}
        highlightedIds={highlightedSet}
        onNodeClick={onNodeClick}
      />
    </div>
  )
}
