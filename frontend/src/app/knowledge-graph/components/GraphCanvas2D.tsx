'use client'

/**
 * GraphCanvas2D — SVG knowledge graph visualization
 *
 * Inspired by TrustGraph context-graph-demo (GraphCanvasSVG.tsx).
 * Radial layout grouped by entity type, Bézier gradient edges,
 * breathing animation, grid background, glow on hover.
 */

import { useEffect, useRef, useState, useCallback, useMemo, useReducer } from 'react'
import {
  IconZoomIn,
  IconZoomOut,
  IconFocusCentered,
  IconLoader2,
} from '@tabler/icons-react'
import type { TrustGraphNode, TrustGraphEdge } from '@/lib/services/knowledge-tree.service'
import { getEntityColor } from './explainability-theme'

// ── Internal types ──

interface GraphNode extends TrustGraphNode {
  cx: number
  cy: number
  r: number
  color: string
}

interface Props {
  nodes: TrustGraphNode[]
  links: TrustGraphEdge[]
  highlightedIds?: Set<string> | null
  onNodeClick?: (node: TrustGraphNode) => void
  focusNodeId?: string | null
  className?: string
}

// ── Constants ──

const GRID_SPACING = 30
const GRID_COLOR = 'rgba(255,255,255,0.015)'
const BG_COLOR = '#0A0A0F'
const SETTLE_TIME = 8000
const NODE_RADIUS = 9
const FONT_FAMILY_MONO = "'JetBrains Mono', 'IBM Plex Mono', monospace"
const FONT_FAMILY_SANS = "'IBM Plex Sans', 'Inter', sans-serif"

// ── Component ──

export function GraphCanvas2D({
  nodes,
  links,
  highlightedIds,
  onNodeClick,
  focusNodeId,
  className,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  const [size, setSize] = useState({ width: 0, height: 0 })
  const [hovered, setHovered] = useState<string | null>(null)

  // Animation state kept entirely in refs — no React state updates during animation
  const timeRef = useRef(0)
  const settledRef = useRef(false)
  const animRef = useRef<number>(0)
  const startTimeRef = useRef<number>(0)
  const lastFrameRef = useRef<number>(0)
  // Force re-render without state deps: useReducer tick
  const [, forceRender] = useReducer((x: number) => x + 1, 0)

  // Zoom + pan
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const isPanningRef = useRef(false)
  const lastPanRef = useRef({ x: 0, y: 0 })

  // ── ResizeObserver ──
  const prevSizeRef = useRef({ width: 0, height: 0 })
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const obs = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect
      const w = Math.round(width)
      const h = Math.round(height)
      if (w > 0 && h > 0 && (w !== prevSizeRef.current.width || h !== prevSizeRef.current.height)) {
        prevSizeRef.current = { width: w, height: h }
        setSize({ width: w, height: h })
      }
    })
    obs.observe(el)
    return () => obs.disconnect()
  }, [])

  // ── Build graph nodes with radial layout by entity type ──
  const graphNodes = useMemo(() => {
    if (size.width === 0 || nodes.length === 0) return []

    const cx = size.width / 2
    const cy = size.height / 2

    const groups = new Map<string, TrustGraphNode[]>()
    for (const n of nodes) {
      const type = n.type || 'other'
      const group = groups.get(type) ?? []
      group.push(n)
      groups.set(type, group)
    }

    const typeKeys = Array.from(groups.keys())
    const typePositions = new Map<string, { x: number; y: number }>()

    typeKeys.forEach((type, i) => {
      const angle = (Math.PI * 2 * i) / typeKeys.length - Math.PI / 2
      const radius = Math.min(cx, cy) * 0.4
      typePositions.set(type, {
        x: cx + Math.cos(angle) * radius,
        y: cy + Math.sin(angle) * radius,
      })
    })

    const result: GraphNode[] = []
    for (const [type, typeNodes] of groups) {
      const center = typePositions.get(type)!
      const color = getEntityColor(type)
      const count = typeNodes.length

      typeNodes.forEach((n, idx) => {
        const angle = (Math.PI * 2 * idx) / count - Math.PI / 2
        const spread = Math.min(size.width, size.height) * 0.08 + Math.sqrt(count) * 8
        result.push({
          ...n,
          cx: center.x + Math.cos(angle) * spread,
          cy: center.y + Math.sin(angle) * spread,
          r: NODE_RADIUS + Math.log(n.connectionCount + 1) * 2,
          color,
        })
      })
    }

    return result
  }, [nodes, size])

  const nodeMap = useMemo(
    () => new Map(graphNodes.map((n) => [n.id, n])),
    [graphNodes],
  )

  const activeHighlights = highlightedIds && highlightedIds.size > 0 ? highlightedIds : null

  // ── Animation loop — uses refs only, triggers forceRender ──
  useEffect(() => {
    if (size.width === 0 || graphNodes.length === 0) return

    startTimeRef.current = performance.now()
    settledRef.current = false
    timeRef.current = 0

    let cancelled = false

    function animate(now: number) {
      if (cancelled) return

      if (now - lastFrameRef.current < 50) {
        animRef.current = requestAnimationFrame(animate)
        return
      }
      lastFrameRef.current = now

      if (!settledRef.current && now - startTimeRef.current > SETTLE_TIME) {
        settledRef.current = true
        forceRender() // one final render to show settled state
        return
      }

      timeRef.current += 0.015
      forceRender()
      animRef.current = requestAnimationFrame(animate)
    }

    animRef.current = requestAnimationFrame(animate)
    return () => {
      cancelled = true
      cancelAnimationFrame(animRef.current)
    }
    // Only re-run when data or container actually changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [size.width, size.height, graphNodes.length])

  // Read animation values from refs (no state deps)
  const time = timeRef.current
  const settled = settledRef.current

  // ── Position helpers ──
  const getPos = useCallback((node: GraphNode, t: number, isSettled: boolean) => {
    if (isSettled) return { x: node.cx, y: node.cy }
    const dx = Math.sin(t + node.cx * 0.01) * 0.5
    const dy = Math.cos(t + node.cy * 0.01) * 0.5
    return { x: node.cx + dx, y: node.cy + dy }
  }, [])

  const getEdgePath = useCallback(
    (from: GraphNode, to: GraphNode, t: number, isSettled: boolean) => {
      const p1 = getPos(from, t, isSettled)
      const p2 = getPos(to, t, isSettled)
      const mx = (p1.x + p2.x) / 2 + (p1.y - p2.y) * 0.1
      const my = (p1.y + p2.y) / 2 + (p2.x - p1.x) * 0.1
      return { path: `M ${p1.x} ${p1.y} Q ${mx} ${my} ${p2.x} ${p2.y}`, mx, my, ...p1, x2: p2.x, y2: p2.y }
    },
    [getPos],
  )

  // ── Grid ──
  const gridLines = useMemo(() => {
    const lines: React.ReactElement[] = []
    for (let x = 0; x < size.width; x += GRID_SPACING) {
      lines.push(<line key={`v${x}`} x1={x} y1={0} x2={x} y2={size.height} stroke={GRID_COLOR} strokeWidth={0.5} />)
    }
    for (let y = 0; y < size.height; y += GRID_SPACING) {
      lines.push(<line key={`h${y}`} x1={0} y1={y} x2={size.width} y2={y} stroke={GRID_COLOR} strokeWidth={0.5} />)
    }
    return lines
  }, [size])

  // ── Zoom (native listener for passive:false) ──
  const zoomRef = useRef(zoom)
  const panRef = useRef(pan)
  zoomRef.current = zoom
  panRef.current = pan

  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return
    function onWheel(e: WheelEvent) {
      e.preventDefault()
      const delta = e.deltaY > 0 ? 0.9 : 1.1
      const z = zoomRef.current
      const p = panRef.current
      const newZoom = Math.min(4, Math.max(0.25, z * delta))
      const rect = svg!.getBoundingClientRect()
      const cx = e.clientX - rect.left
      const cy = e.clientY - rect.top
      const ratio = newZoom / z
      setPan({ x: cx - (cx - p.x) * ratio, y: cy - (cy - p.y) * ratio })
      setZoom(newZoom)
    }
    svg.addEventListener('wheel', onWheel, { passive: false })
    return () => svg.removeEventListener('wheel', onWheel)
  }, [])

  // ── Pan ──
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button === 1 || (e.button === 0 && e.shiftKey)) {
      e.preventDefault()
      isPanningRef.current = true
      lastPanRef.current = { x: e.clientX, y: e.clientY }
    }
  }, [])

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!isPanningRef.current) return
    setPan((p) => ({
      x: p.x + e.clientX - lastPanRef.current.x,
      y: p.y + e.clientY - lastPanRef.current.y,
    }))
    lastPanRef.current = { x: e.clientX, y: e.clientY }
  }, [])

  const handleMouseUp = useCallback(() => { isPanningRef.current = false }, [])
  const handleReset = useCallback(() => { setZoom(1); setPan({ x: 0, y: 0 }) }, [])

  const handleNodeClick = useCallback(
    (node: GraphNode) => onNodeClick?.(node),
    [onNodeClick],
  )

  // ── Early returns ──
  if (size.width === 0) {
    return <div ref={containerRef} className={`w-full h-full ${className ?? ''}`} />
  }

  if (graphNodes.length === 0) {
    return (
      <div ref={containerRef} className={`w-full h-full flex items-center justify-center ${className ?? ''}`} style={{ background: BG_COLOR }}>
        <IconLoader2 className="h-6 w-6 animate-spin text-cyan-500/40" />
      </div>
    )
  }

  // Type cluster labels (computed inline — cheap)
  const typeGroups = new Map<string, { x: number; y: number }>()
  for (const n of graphNodes) {
    if (!typeGroups.has(n.type)) {
      const sameType = graphNodes.filter((g) => g.type === n.type)
      const avgX = sameType.reduce((s, g) => s + g.cx, 0) / sameType.length
      const avgY = sameType.reduce((s, g) => s + g.cy, 0) / sameType.length
      typeGroups.set(n.type, { x: avgX, y: avgY - Math.min(size.width, size.height) * 0.1 })
    }
  }

  return (
    <div
      ref={containerRef}
      className={`relative w-full h-full overflow-hidden ${className ?? ''}`}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
    >
      <svg
        ref={svgRef}
        width={size.width}
        height={size.height}
        style={{ display: 'block', background: BG_COLOR, cursor: isPanningRef.current ? 'grabbing' : 'default' }}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
      >
        <g>{gridLines}</g>

        <g transform={`translate(${pan.x},${pan.y}) scale(${zoom})`}>
          {/* Type labels */}
          {Array.from(typeGroups.entries()).map(([type, pos]) => (
            <text
              key={`label-${type}`}
              x={pos.x}
              y={pos.y}
              fill={`${getEntityColor(type)}44`}
              fontSize={11}
              fontWeight="bold"
              fontFamily={FONT_FAMILY_MONO}
              textAnchor="middle"
            >
              {type.toUpperCase()}
            </text>
          ))}

          {/* Edges */}
          {links.map((link, i) => {
            const srcId = typeof link.source === 'string' ? link.source : (link.source as any)?.id
            const tgtId = typeof link.target === 'string' ? link.target : (link.target as any)?.id
            const from = nodeMap.get(srcId)
            const to = nodeMap.get(tgtId)
            if (!from || !to) return null

            const isHighlighted = activeHighlights
              ? activeHighlights.has(srcId) && activeHighlights.has(tgtId)
              : false

            const { path, mx, my, x: x1, y: y1, x2, y2 } = getEdgePath(from, to, time, settled)
            const baseAlpha = isHighlighted ? 0.7 : 0.12
            const pulse = isHighlighted ? Math.sin(time * 4) * 0.15 + 0.15 : 0
            const alpha = Math.min(1, baseAlpha + pulse)

            const t = (time * 2) % 1
            const px = (1 - t) * (1 - t) * x1 + 2 * (1 - t) * t * mx + t * t * x2
            const py = (1 - t) * (1 - t) * y1 + 2 * (1 - t) * t * my + t * t * y2

            return (
              <g key={`edge-${i}`}>
                <defs>
                  <linearGradient id={`grad-${i}`} x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" stopColor={from.color} stopOpacity={alpha} />
                    <stop offset="100%" stopColor={to.color} stopOpacity={alpha} />
                  </linearGradient>
                </defs>
                <path d={path} stroke={`url(#grad-${i})`} strokeWidth={isHighlighted ? 1.5 : 0.75} fill="none" />
                {isHighlighted && <circle cx={px} cy={py} r={1.5} fill="#fff" />}
              </g>
            )
          })}

          {/* Nodes */}
          {graphNodes.map((node) => {
            const isHighlighted = activeHighlights ? activeHighlights.has(node.id) : false
            const isHovered = hovered === node.id
            const isDimmed = activeHighlights && activeHighlights.size > 0 && !isHighlighted
            const alpha = isDimmed ? 0.2 : 1
            const r = isHighlighted || isHovered ? node.r * 1.4 : node.r
            const pulseR = isHighlighted && !settled ? Math.sin(time * 3) * 1.5 : 0
            const { x, y } = getPos(node, time, settled)
            const label = node.label.length > 24 ? node.label.slice(0, 22) + '…' : node.label

            return (
              <g
                key={node.id}
                style={{ cursor: 'pointer' }}
                onClick={() => handleNodeClick(node)}
                onMouseEnter={() => setHovered(node.id)}
                onMouseLeave={() => setHovered(null)}
              >
                {(isHighlighted || isHovered) && (
                  <circle cx={x} cy={y} r={r + 8 + pulseR} fill={node.color} fillOpacity={0.15} />
                )}
                <circle
                  cx={x} cy={y} r={r}
                  fill={node.color} fillOpacity={alpha * 0.2}
                  stroke={node.color} strokeOpacity={alpha}
                  strokeWidth={isHighlighted ? 1.25 : 0.75}
                />
                <text
                  x={x} y={y + r + 10}
                  fill={`rgba(255,255,255,${alpha * (isHighlighted ? 1 : 0.7)})`}
                  fontSize={isHovered ? 8.5 : 7}
                  fontWeight={isHighlighted ? 'bold' : 'normal'}
                  fontFamily={FONT_FAMILY_SANS}
                  textAnchor="middle"
                >
                  {label}
                </text>
              </g>
            )
          })}
        </g>
      </svg>

      {/* Zoom controls */}
      <div className="absolute bottom-4 right-4 flex flex-col gap-1.5 z-10">
        <button onClick={() => setZoom((z) => Math.min(4, z * 1.3))} className="h-7 w-7 rounded-md border border-white/[0.06] bg-[#0A0A0F]/80 backdrop-blur text-slate-500 hover:text-slate-300 flex items-center justify-center transition-colors" title="Acercar">
          <IconZoomIn className="h-3.5 w-3.5" />
        </button>
        <button onClick={() => setZoom((z) => Math.max(0.25, z / 1.3))} className="h-7 w-7 rounded-md border border-white/[0.06] bg-[#0A0A0F]/80 backdrop-blur text-slate-500 hover:text-slate-300 flex items-center justify-center transition-colors" title="Alejar">
          <IconZoomOut className="h-3.5 w-3.5" />
        </button>
        <button onClick={handleReset} className="h-7 w-7 rounded-md border border-white/[0.06] bg-[#0A0A0F]/80 backdrop-blur text-slate-500 hover:text-slate-300 flex items-center justify-center transition-colors" title="Centrar">
          <IconFocusCentered className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Tooltip */}
      {hovered && (() => {
        const node = nodeMap.get(hovered)
        if (!node) return null
        const { x, y } = getPos(node, time, settled)
        const screenX = x * zoom + pan.x
        const screenY = y * zoom + pan.y

        return (
          <div className="absolute z-20 pointer-events-none" style={{ left: screenX + 20, top: screenY - 20 }}>
            <div className="rounded-lg px-3 py-2.5 backdrop-blur-xl" style={{ background: 'rgba(10,10,15,0.95)', border: `1px solid ${node.color}44`, minWidth: 180 }}>
              <div className="font-bold text-[13px]" style={{ color: node.color, fontFamily: FONT_FAMILY_MONO }}>
                {node.label}
              </div>
              <div className="text-[11px] mt-1" style={{ color: '#888', fontFamily: FONT_FAMILY_MONO }}>
                <div><span className="text-slate-600">tipo:</span> <span className="text-slate-300">{node.type}</span></div>
                {node.definition && (
                  <div className="mt-1 text-slate-400 leading-tight" style={{ maxWidth: 240 }}>
                    {node.definition.length > 100 ? node.definition.slice(0, 98) + '…' : node.definition}
                  </div>
                )}
                <div><span className="text-slate-600">conexiones:</span> <span className="text-slate-300">{node.connectionCount}</span></div>
              </div>
            </div>
          </div>
        )
      })()}
    </div>
  )
}
