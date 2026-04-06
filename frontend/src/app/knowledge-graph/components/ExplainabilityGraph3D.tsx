'use client'

import { useEffect, useRef, useState, useCallback } from 'react'
import { IconLoader2 } from '@tabler/icons-react'
import dynamic from 'next/dynamic'
import SpriteText from 'three-spritetext'
import type {
  TrustGraphNode,
  TrustGraphEdge,
} from '@/lib/services/knowledge-tree.service'
import {
  getEntityColor,
  getEntityGlow,
  getEntityNodeSize,
  getEdgeStyle,
  ENTITY_TYPE_COLORS,
} from './explainability-theme'

const ForceGraph3D = dynamic(
  () => import('react-force-graph-3d'),
  {
    ssr: false,
    loading: () => (
      <div className="flex items-center justify-center h-full text-muted-foreground">
        Cargando grafo 3D...
      </div>
    ),
  }
)

interface ExplainabilityGraph3DProps {
  nodes: TrustGraphNode[]
  links: TrustGraphEdge[]
  highlightedIds?: Set<string> | null
  onNodeClick?: (node: TrustGraphNode) => void
  focusNodeId?: string | null
  className?: string
  width?: number
  height?: number
}

export default function ExplainabilityGraph3D({
  nodes,
  links,
  highlightedIds,
  onNodeClick,
  focusNodeId,
  className,
  width,
  height,
}: ExplainabilityGraph3DProps) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const graphRef = useRef<any>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [dimensions, setDimensions] = useState({ width: width ?? 0, height: height ?? 0 })
  const [isSimulating, setIsSimulating] = useState(true)

  // ResizeObserver for responsive sizing — updates state to trigger re-render
  useEffect(() => {
    if (!containerRef.current) return

    // Set initial dimensions from container (avoids 800x600 flash)
    const rect = containerRef.current.getBoundingClientRect()
    if (rect.width > 0 && rect.height > 0) {
      setDimensions({ width: rect.width, height: rect.height })
    }

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width: w, height: h } = entry.contentRect
        if (w > 0 && h > 0) {
          setDimensions({ width: w, height: h })
        }
      }
    })
    observer.observe(containerRef.current)
    return () => observer.disconnect()
  }, [])

  // Auto-focus camera when focusNodeId changes
  useEffect(() => {
    if (!focusNodeId || !graphRef.current) return
    const node = nodes.find((n) => n.id === focusNodeId)
    if (!node) return
    const distance = 120
    const distRatio = 1 + distance / Math.hypot(node.x ?? 0, node.y ?? 0, (node.z ?? 0) || 1)
    graphRef.current.cameraPosition(
      {
        x: (node.x ?? 0) * distRatio,
        y: (node.y ?? 0) * distRatio,
        z: (node.z ?? 0) * distRatio,
      },
      node,
      1000
    )
  }, [focusNodeId, nodes])

  const handleNodeClick = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (node: any) => {
      if (onNodeClick) onNodeClick(node as TrustGraphNode)
    },
    [onNodeClick]
  )

  const handleBackgroundClick = useCallback(() => {
    if (onNodeClick) onNodeClick(null as unknown as TrustGraphNode)
  }, [onNodeClick])

  // Pin node on drag end
  const handleNodeDragEnd = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (node: any) => {
      node.fx = node.x
      node.fy = node.y
      node.fz = node.z
    },
    []
  )

  // Node three-object: sphere + label (truncated for readability)
  const nodeThreeObject = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (node: any) => {
      const tgNode = node as TrustGraphNode
      // Truncate long labels for readability
      const displayLabel = tgNode.label.length > 28
        ? tgNode.label.slice(0, 26) + '…'
        : tgNode.label
      const sprite = new SpriteText(displayLabel)
      const baseColor = getEntityColor(tgNode.type)
      const dimmed =
        highlightedIds != null && !highlightedIds.has(tgNode.id)

      sprite.color = dimmed ? '#1e293b44' : baseColor
      sprite.textHeight = dimmed ? 2.5 : 4
      sprite.backgroundColor = 'transparent'
      sprite.padding = 1
      return sprite
    },
    [highlightedIds]
  )

  const nodeColor = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (node: any) => {
      const tgNode = node as TrustGraphNode
      const base = getEntityColor(tgNode.type)
      if (highlightedIds != null && !highlightedIds.has(tgNode.id)) {
        return '#0f172a' // slate-900: nearly invisible in void
      }
      return base
    },
    [highlightedIds]
  )

  const nodeVal = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (node: any) => getEntityNodeSize((node as TrustGraphNode).connectionCount),
    []
  )

  const linkColor = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (link: any) => {
      const tgLink = link as TrustGraphEdge
      if (highlightedIds != null) {
        const srcId =
          typeof tgLink.source === 'string'
            ? tgLink.source
            : (tgLink.source as any)?.id
        const tgtId =
          typeof tgLink.target === 'string'
            ? tgLink.target
            : (tgLink.target as any)?.id
        if (!highlightedIds.has(srcId) || !highlightedIds.has(tgtId)) {
          return '#1e293b'
        }
      }
      return getEdgeStyle(tgLink.namespace).color
    },
    [highlightedIds]
  )

  // Link label as SpriteText at midpoint
  const linkThreeObjectExtend = true

  const linkThreeObject = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (link: any) => {
      const tgLink = link as TrustGraphEdge
      const sprite = new SpriteText(tgLink.predicate.replace(/-/g, ' '))
      sprite.color = '#94a3b8'
      sprite.textHeight = 2.5
      sprite.backgroundColor = 'rgba(7,9,15,0.6)'
      sprite.padding = 1
      return sprite
    },
    []
  )

  const linkPositionUpdate = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (sprite: any, { start, end }: { start: any; end: any }) => {
      const mid = {
        x: start.x + (end.x - start.x) / 2,
        y: start.y + (end.y - start.y) / 2,
        z: start.z + (end.z - start.z) / 2,
      }
      Object.assign(sprite.position, mid)
    },
    []
  )

  // Hide loader after engine stabilizes or after timeout
  useEffect(() => {
    setIsSimulating(true)
    const timeout = setTimeout(() => setIsSimulating(false), 3000)
    return () => clearTimeout(timeout)
  }, [nodes, links])

  // Also hide when engine stabilizes
  const handleEngineStop = useCallback(() => setIsSimulating(false), [])

  const graphData = { nodes, links }

  return (
    <div
      ref={containerRef}
      className={className}
      style={{ width: '100%', height: '100%', background: '#07090f' }}
    >
      {/* Simulation loader */}
      {isSimulating && nodes.length > 0 && (
        <div className="absolute inset-0 flex items-center justify-center bg-[#07090f]/80 z-10">
          <div className="flex flex-col items-center gap-3">
            <IconLoader2 className="h-6 w-6 animate-spin text-cyan-500/60" />
            <span className="text-[11px] text-slate-600 tracking-widest uppercase">
              Calculando layout 3D ({nodes.length} nodos)
            </span>
          </div>
        </div>
      )}

      {dimensions.width > 0 && dimensions.height > 0 && (
      <ForceGraph3D
        ref={graphRef}
        graphData={graphData}
        width={dimensions.width}
        height={dimensions.height}
        backgroundColor="#07090f"
        nodeLabel={(node: any) =>
          `${(node as TrustGraphNode).label} (${(node as TrustGraphNode).type})${(node as TrustGraphNode).definition ? '\n' + (node as TrustGraphNode).definition : ''}`
        }
        nodeVal={nodeVal}
        nodeColor={nodeColor}
        nodeThreeObject={nodeThreeObject}
        nodeThreeObjectExtend={false}
        onNodeClick={handleNodeClick}
        onBackgroundClick={handleBackgroundClick}
        onNodeDragEnd={handleNodeDragEnd}
        linkColor={linkColor}
        linkDirectionalArrowLength={4}
        linkDirectionalArrowRelPos={1}
        linkDirectionalArrowColor={linkColor}
        linkThreeObject={linkThreeObject}
        linkThreeObjectExtend={linkThreeObjectExtend}
        linkPositionUpdate={linkPositionUpdate}
        linkOpacity={0.7}
        linkWidth={(link: any) => getEdgeStyle((link as TrustGraphEdge).namespace).width * 0.3}
        linkLabel={(link: any) => (link as TrustGraphEdge).predicate.replace(/-/g, ' ')}
        onEngineStop={handleEngineStop}
      />
      )}
    </div>
  )
}
