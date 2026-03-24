'use client'

import { useEffect, useRef, useCallback } from 'react'
import dynamic from 'next/dynamic'
import SpriteText from 'three-spritetext'
import {
  ExplainNode,
  ExplainLink,
  getNodeColor,
  getEdgeColor,
  getNodeSize,
} from './explainability-theme'

const ForceGraph3D = dynamic(
  () => import('react-force-graph').then((m) => m.ForceGraph3D),
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
  nodes: ExplainNode[]
  links: ExplainLink[]
  highlightedIds?: Set<string> | null
  onNodeClick?: (node: ExplainNode) => void
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
  const dimensionsRef = useRef({ width: width ?? 800, height: height ?? 600 })

  // ResizeObserver for responsive sizing
  useEffect(() => {
    if (!containerRef.current) return
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width: w, height: h } = entry.contentRect
        dimensionsRef.current = { width: w, height: h }
        if (graphRef.current) {
          graphRef.current.width(w)
          graphRef.current.height(h)
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
    const distRatio = 1 + distance / Math.hypot(node.x ?? 0, node.y ?? 0, node.z ?? 0 || 1)
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
      if (onNodeClick) onNodeClick(node as ExplainNode)
    },
    [onNodeClick]
  )

  const handleBackgroundClick = useCallback(() => {
    if (onNodeClick) onNodeClick(null as unknown as ExplainNode)
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

  // Node three-object: sphere + label
  const nodeThreeObject = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (node: any) => {
      const explainNode = node as ExplainNode
      const sprite = new SpriteText(explainNode.label)
      const baseColor = getNodeColor(explainNode)
      const dimmed =
        highlightedIds != null && !highlightedIds.has(explainNode.id)

      sprite.color = dimmed ? '#334155' : baseColor
      sprite.textHeight = dimmed ? 3 : 4
      sprite.backgroundColor = 'transparent'
      sprite.padding = 1
      return sprite
    },
    [highlightedIds]
  )

  const nodeColor = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (node: any) => {
      const explainNode = node as ExplainNode
      const base = getNodeColor(explainNode)
      if (highlightedIds != null && !highlightedIds.has(explainNode.id)) {
        return '#1e293b'
      }
      return base
    },
    [highlightedIds]
  )

  const nodeVal = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (node: any) => getNodeSize(node as ExplainNode),
    []
  )

  const linkColor = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (link: any) => {
      const explainLink = link as ExplainLink
      if (highlightedIds != null) {
        const srcId =
          typeof explainLink.source === 'string'
            ? explainLink.source
            : (explainLink.source as ExplainNode).id
        const tgtId =
          typeof explainLink.target === 'string'
            ? explainLink.target
            : (explainLink.target as ExplainNode).id
        if (!highlightedIds.has(srcId) || !highlightedIds.has(tgtId)) {
          return '#1e293b'
        }
      }
      return getEdgeColor(explainLink)
    },
    [highlightedIds]
  )

  // Link label as SpriteText at midpoint
  const linkThreeObjectExtend = true

  const linkThreeObject = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (link: any) => {
      const explainLink = link as ExplainLink
      const sprite = new SpriteText(explainLink.type)
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

  const graphData = { nodes, links }

  return (
    <div
      ref={containerRef}
      className={className}
      style={{ width: '100%', height: '100%', background: '#07090f' }}
    >
      <ForceGraph3D
        ref={graphRef}
        graphData={graphData}
        width={dimensionsRef.current.width}
        height={dimensionsRef.current.height}
        backgroundColor="#07090f"
        nodeLabel="label"
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
        linkWidth={1}
      />
    </div>
  )
}
