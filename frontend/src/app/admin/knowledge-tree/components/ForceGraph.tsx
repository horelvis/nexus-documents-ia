"use client"

import { useRef, useEffect, useState } from "react"
import {
  forceSimulation,
  forceLink,
  forceManyBody,
  forceCenter,
  forceCollide,
  forceX,
  forceY,
} from "d3-force"
import { select } from "d3-selection"
import { zoom as d3Zoom, zoomIdentity } from "d3-zoom"
import "d3-transition"
import { drag as d3Drag } from "d3-drag"
import {
  IconZoomIn,
  IconZoomOut,
  IconFocusCentered,
  IconLoader2,
} from "@tabler/icons-react"
import type { SimNode, SimLink } from "./graph-theme"
import { getNodeColor, getNodeGlow, getNodeRadius, getEdgeStyle } from "./graph-theme"

interface ForceGraphProps {
  nodes: SimNode[]
  links: SimLink[]
  highlightedIds?: Set<string> | null
  onNodeClick?: (node: SimNode) => void
}

export function ForceGraph({ nodes, links, highlightedIds, onNodeClick }: ForceGraphProps) {
  const svgRef = useRef<SVGSVGElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [hoveredNode, setHoveredNode] = useState<SimNode | null>(null)
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 })
  const [isSimulating, setIsSimulating] = useState(true)

  useEffect(() => {
    setIsSimulating(true)
  }, [nodes, links])

  useEffect(() => {
    if (!svgRef.current || !containerRef.current || nodes.length === 0) return

    const svg = select(svgRef.current)
    const container = containerRef.current
    const width = container.clientWidth
    const height = container.clientHeight

    svg.attr("viewBox", `0 0 ${width} ${height}`)
    svg.selectAll("*").remove()

    // Background
    const defs = svg.append("defs")
    const bgGrad = defs.append("radialGradient").attr("id", "bg-void")
    bgGrad.append("stop").attr("offset", "0%").attr("stop-color", "#0c1020")
    bgGrad.append("stop").attr("offset", "100%").attr("stop-color", "#07090f")

    // Glow filter
    const glow = defs.append("filter").attr("id", "node-glow").attr("x", "-50%").attr("y", "-50%").attr("width", "200%").attr("height", "200%")
    glow.append("feGaussianBlur").attr("stdDeviation", "3").attr("result", "blur")
    const merge = glow.append("feMerge")
    merge.append("feMergeNode").attr("in", "blur")
    merge.append("feMergeNode").attr("in", "SourceGraphic")

    svg.append("rect").attr("width", width).attr("height", height).attr("fill", "url(#bg-void)")

    const g = svg.append("g")

    // Zoom
    const zoomBehavior = d3Zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.05, 6])
      .on("zoom", (event) => g.attr("transform", event.transform))

    svg.call(zoomBehavior)
    svg.call(zoomBehavior.transform, zoomIdentity.translate(width / 2, height / 2).scale(0.5))
    ;(svgRef.current as any).__zoomBehavior = zoomBehavior

    // Links
    const linkGroup = g.append("g").attr("class", "links")
      .selectAll("line")
      .data(links)
      .join("line")
      .attr("stroke", "#334155")
      .attr("stroke-opacity", (d) => {
        if (highlightedIds?.size) {
          const s = typeof d.source === "object" ? (d.source as SimNode).id : d.source
          const t = typeof d.target === "object" ? (d.target as SimNode).id : d.target
          return (highlightedIds.has(s as string) && highlightedIds.has(t as string)) ? 0.5 : 0.03
        }
        return getEdgeStyle(d.edgeLabel).opacity
      })
      .attr("stroke-width", 1)
      .attr("stroke-dasharray", (d) => getEdgeStyle(d.edgeLabel).dash)

    // Edge labels
    const edgeLabelGroup = g.append("g").attr("class", "edge-labels")
      .selectAll("text")
      .data(links.filter((l) => l.edgeLabel))
      .join("text")
      .text((d) => d.edgeLabel)
      .attr("font-size", 6)
      .attr("fill", "#475569")
      .attr("text-anchor", "middle")
      .attr("pointer-events", "none")
      .attr("font-family", "'JetBrains Mono', monospace")
      .attr("opacity", 0.6)

    // Nodes
    const nodeGroup = g.append("g").attr("class", "nodes")
      .selectAll("circle")
      .data(nodes)
      .join("circle")
      .attr("r", (d) => getNodeRadius(d))
      .attr("fill", (d) => getNodeColor(d))
      .attr("stroke", "none")
      .attr("cursor", "pointer")
      .attr("filter", (d) => d.kind === "law" || d.kind === "person" ? "url(#node-glow)" : "none")
      .attr("opacity", (d) => {
        if (highlightedIds?.size) return highlightedIds.has(d.id) ? 1 : 0.08
        return d.kind === "document" || d.kind === "memory" ? 0.6 : 0.85
      })
      .on("mouseenter", function (event, d) {
        select(this)
          .transition().duration(150)
          .attr("r", getNodeRadius(d) * 1.5)
          .attr("fill", getNodeGlow(d))
          .attr("filter", "url(#node-glow)")
          .attr("opacity", 1)

        // Dim non-connected
        const connectedIds = new Set<string>([d.id])
        links.forEach((l) => {
          const s = typeof l.source === "object" ? (l.source as SimNode).id : l.source as string
          const t = typeof l.target === "object" ? (l.target as SimNode).id : l.target as string
          if (s === d.id) connectedIds.add(t)
          if (t === d.id) connectedIds.add(s)
        })

        nodeGroup.transition().duration(150)
          .attr("opacity", (n: any) => connectedIds.has(n.id) ? 1 : 0.06)

        linkGroup.transition().duration(150)
          .attr("stroke-opacity", (l: any) => {
            const s = typeof l.source === "object" ? l.source.id : l.source
            const t = typeof l.target === "object" ? l.target.id : l.target
            return (s === d.id || t === d.id) ? 0.6 : 0.02
          })
          .attr("stroke", (l: any) => {
            const s = typeof l.source === "object" ? l.source.id : l.source
            const t = typeof l.target === "object" ? l.target.id : l.target
            return (s === d.id || t === d.id) ? getNodeGlow(d) : "#1e293b"
          })

        setHoveredNode(d)
        setTooltipPos({ x: event.clientX, y: event.clientY })
      })
      .on("mousemove", (event) => setTooltipPos({ x: event.clientX, y: event.clientY }))
      .on("mouseleave", function () {
        nodeGroup.transition().duration(300)
          .attr("r", (d: any) => getNodeRadius(d))
          .attr("fill", (d: any) => getNodeColor(d))
          .attr("filter", (d: any) => d.kind === "law" || d.kind === "person" ? "url(#node-glow)" : "none")
          .attr("opacity", (d: any) => {
            if (highlightedIds?.size) return highlightedIds.has(d.id) ? 1 : 0.08
            return d.kind === "document" || d.kind === "memory" ? 0.6 : 0.85
          })

        linkGroup.transition().duration(300)
          .attr("stroke", "#334155")
          .attr("stroke-opacity", (d: any) => getEdgeStyle(d.edgeLabel).opacity)

        setHoveredNode(null)
      })
      .on("click", (_event, d) => onNodeClick?.(d))

    // Node labels
    const labelGroup = g.append("g").attr("class", "labels")
      .selectAll("text")
      .data(nodes.filter((n) => n.kind !== "memory"))
      .join("text")
      .text((d: any) => {
        const name = (d as SimNode).name || ""
        return name.length > 24 ? name.slice(0, 22) + "…" : name
      })
      .attr("font-size", (d: any) => (d as SimNode).kind === "law" ? 8 : (d as SimNode).kind === "person" ? 7.5 : 6)
      .attr("fill", (d: any) => {
        const node = d as SimNode
        if (highlightedIds?.size) return highlightedIds.has(node.id) ? "#e2e8f0" : "#1e293b"
        return node.kind === "document" || node.kind === "memory" ? "#475569" : "#94a3b8"
      })
      .attr("text-anchor", "middle")
      .attr("pointer-events", "none")
      .attr("font-family", "'JetBrains Mono', monospace")
      .attr("font-weight", (d) => d.kind === "law" || d.kind === "person" ? 600 : 400)

    // Drag
    const dragBehavior = d3Drag<SVGCircleElement, SimNode>()
      .on("start", (event, d) => {
        if (!event.active) simulation.alphaTarget(0.3).restart()
        d.fx = d.x
        d.fy = d.y
      })
      .on("drag", (event, d) => {
        d.fx = event.x
        d.fy = event.y
      })
      .on("end", (event, d) => {
        if (!event.active) simulation.alphaTarget(0)
        d.fx = null
        d.fy = null
      })

    nodeGroup.call(dragBehavior as any)

    // Simulation
    const simulation = forceSimulation<SimNode>(nodes)
      .force("link", forceLink<SimNode, SimLink>(links).id((d: any) => d.id).distance(90))
      .force("charge", forceManyBody().strength(-250))
      .force("center", forceCenter(0, 0))
      .force("collision", forceCollide<SimNode>().radius((d) => getNodeRadius(d) + 4))
      .force("x", forceX(0).strength(0.04))
      .force("y", forceY(0).strength(0.04))
      .on("tick", () => {
        linkGroup
          .attr("x1", (d: any) => d.source.x)
          .attr("y1", (d: any) => d.source.y)
          .attr("x2", (d: any) => d.target.x)
          .attr("y2", (d: any) => d.target.y)

        edgeLabelGroup
          .attr("x", (d: any) => (d.source.x + d.target.x) / 2)
          .attr("y", (d: any) => (d.source.y + d.target.y) / 2)

        nodeGroup
          .attr("cx", (d: any) => d.x)
          .attr("cy", (d: any) => d.y)

        labelGroup
          .attr("x", (d: any) => d.x)
          .attr("y", (d: any) => d.y + getNodeRadius(d) + 10)
      })
      .on("end", () => setIsSimulating(false))

    // Hide loader after first few ticks even if simulation hasn't fully settled
    const earlyReveal = setTimeout(() => setIsSimulating(false), 1500)

    return () => { simulation.stop(); clearTimeout(earlyReveal) }
  }, [nodes, links, highlightedIds, onNodeClick])

  // Zoom controls
  const handleZoom = (factor: number) => {
    const svg = svgRef.current
    if (!svg) return
    const behavior = (svg as any).__zoomBehavior
    if (!behavior) return
    select(svg).transition().duration(300).call(behavior.scaleBy, factor)
  }

  const handleFitView = () => {
    const svg = svgRef.current
    const container = containerRef.current
    if (!svg || !container) return
    const behavior = (svg as any).__zoomBehavior
    if (!behavior) return
    const w = container.clientWidth
    const h = container.clientHeight
    select(svg).transition().duration(500)
      .call(behavior.transform, zoomIdentity.translate(w / 2, h / 2).scale(0.5))
  }

  return (
    <div ref={containerRef} className="relative w-full h-full overflow-hidden bg-[#07090f]">
      <svg ref={svgRef} className="w-full h-full" />

      {/* Simulation loader */}
      {isSimulating && nodes.length > 0 && (
        <div className="absolute inset-0 flex items-center justify-center bg-[#07090f]/80 z-10 transition-opacity duration-500">
          <div className="flex flex-col items-center gap-3">
            <IconLoader2 className="h-6 w-6 animate-spin text-cyan-500/60" />
            <span className="text-[11px] text-slate-600 tracking-widest uppercase">
              Calculando layout ({nodes.length} nodos)
            </span>
          </div>
        </div>
      )}

      {/* Zoom controls — bottom right */}
      <div className="absolute bottom-4 right-4 flex flex-col gap-1.5">
        <button onClick={() => handleZoom(1.4)} className="kt-control-btn" title="Acercar">
          <IconZoomIn className="h-4 w-4" />
        </button>
        <button onClick={() => handleZoom(1 / 1.4)} className="kt-control-btn" title="Alejar">
          <IconZoomOut className="h-4 w-4" />
        </button>
        <button onClick={handleFitView} className="kt-control-btn" title="Centrar">
          <IconFocusCentered className="h-4 w-4" />
        </button>
      </div>

      {/* Tooltip */}
      {hoveredNode && (
        <div
          className="fixed z-50 pointer-events-none kt-tooltip"
          style={{ left: tooltipPos.x + 14, top: tooltipPos.y - 10 }}
        >
          <div className="flex items-center gap-2 mb-1">
            <span
              className="h-2.5 w-2.5 rounded-full shrink-0"
              style={{ backgroundColor: getNodeColor(hoveredNode), boxShadow: `0 0 6px ${getNodeGlow(hoveredNode)}` }}
            />
            <span className="font-semibold text-[11px] text-white truncate max-w-[200px]">
              {hoveredNode.name}
            </span>
          </div>
          <div className="text-[10px] text-slate-400 space-y-0.5 pl-[18px]">
            <div className="uppercase tracking-widest text-slate-500">{hoveredNode.label}</div>
            {hoveredNode.properties.domain && (
              <div>Dominio: <span className="text-slate-300">{hoveredNode.properties.domain as string}</span></div>
            )}
            {hoveredNode.properties.semantic_type && (
              <div>Tipo: <span className="text-slate-300">{hoveredNode.properties.semantic_type as string}</span></div>
            )}
            {hoveredNode.properties.status && (
              <div>Estado: <span className="text-slate-300">{hoveredNode.properties.status as string}</span></div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
