"use client"

import { useState, useEffect, useRef, useCallback } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import {
  forceSimulation,
  forceLink,
  forceManyBody,
  forceCenter,
  forceCollide,
  forceX,
  forceY,
  type SimulationNodeDatum,
  type SimulationLinkDatum,
} from "d3-force"
import { select } from "d3-selection"
import { zoom as d3Zoom, zoomIdentity } from "d3-zoom"
import "d3-transition"
import { drag as d3Drag } from "d3-drag"
import {
  IconBinaryTree,
  IconLoader2,
  IconRefresh,
  IconChevronLeft,
  IconBrain,
  IconFolder,
  IconFile,
  IconCategory,
  IconAlertCircle,
  IconZoomIn,
  IconZoomOut,
  IconFocusCentered,
} from "@tabler/icons-react"
import {
  SidebarProvider,
  SidebarInset,
  SidebarTrigger,
  Alert,
  AlertDescription,
  Button,
} from "@nexus/shared/ui"
import { useApiClient } from "@/lib/api-client"
import { useAuth } from "@/contexts/auth-context"
import { AppSidebar } from "@/components/layout/app-sidebar"
import type { GraphStructure, TreeStats } from "@/lib/services/knowledge-tree.service"

// ============================================================================
// Types
// ============================================================================

interface GraphNode extends SimulationNodeDatum {
  id: string
  label: string
  nodeType: "folder" | "document"
  folderType?: string
  semanticType?: string
  docCount?: number
}

interface GraphLink extends SimulationLinkDatum<GraphNode> {
  id: string
}

// ============================================================================
// Color palette (Logseq-inspired)
// ============================================================================

const FOLDER_COLORS: Record<string, string> = {
  expedientes: "#6366f1",    // indigo
  "exp.conf": "#8b5cf6",    // violet
  registros: "#06b6d4",     // cyan
  virtual: "#64748b",       // slate
  unknown: "#94a3b8",       // gray
}

const DOC_COLORS: Record<string, string> = {
  adjuntos: "#3b82f6",      // blue
  escrituras: "#f59e0b",    // amber
  contratos: "#a855f7",     // purple
  facturas: "#22c55e",      // green
  nominas: "#ec4899",       // pink
  plantillas: "#14b8a6",    // teal
  generados: "#f97316",     // orange
  unknown: "#6b7280",       // gray
}

function getNodeColor(node: GraphNode): string {
  if (node.nodeType === "folder") {
    return FOLDER_COLORS[node.folderType || "unknown"] || FOLDER_COLORS.unknown
  }
  return DOC_COLORS[node.semanticType || "unknown"] || DOC_COLORS.unknown
}

function getNodeRadius(node: GraphNode): number {
  if (node.nodeType === "folder") {
    const count = node.docCount || 0
    return Math.max(8, Math.min(22, 8 + Math.sqrt(count) * 2.5))
  }
  return 4
}

// ============================================================================
// Force Graph Canvas Component
// ============================================================================

function ForceGraph({
  nodes,
  links,
}: {
  nodes: GraphNode[]
  links: GraphLink[]
}) {
  const svgRef = useRef<SVGSVGElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const simulationRef = useRef<ReturnType<typeof forceSimulation<GraphNode>> | null>(null)
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null)
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 })

  useEffect(() => {
    if (!svgRef.current || !containerRef.current || nodes.length === 0) return

    const svg = select(svgRef.current)
    const container = containerRef.current
    const width = container.clientWidth
    const height = container.clientHeight

    svg.attr("viewBox", `0 0 ${width} ${height}`)
    svg.selectAll("*").remove()

    const g = svg.append("g")

    // Zoom behavior
    const zoomBehavior = d3Zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.05, 5])
      .on("zoom", (event) => {
        g.attr("transform", event.transform)
      })

    svg.call(zoomBehavior)
    svg.call(zoomBehavior.transform, zoomIdentity.translate(width / 2, height / 2).scale(0.6))

    // Store zoom for controls
    ;(svgRef.current as any).__zoomBehavior = zoomBehavior

    // Links
    const linkGroup = g
      .append("g")
      .attr("class", "links")
      .selectAll("line")
      .data(links)
      .join("line")
      .attr("stroke", "#334155")
      .attr("stroke-opacity", 0.15)
      .attr("stroke-width", 0.5)

    // Nodes
    const nodeGroup = g
      .append("g")
      .attr("class", "nodes")
      .selectAll("circle")
      .data(nodes)
      .join("circle")
      .attr("r", (d) => getNodeRadius(d))
      .attr("fill", (d) => getNodeColor(d))
      .attr("stroke", (d) => d.nodeType === "folder" ? "rgba(255,255,255,0.3)" : "none")
      .attr("stroke-width", (d) => d.nodeType === "folder" ? 1.5 : 0)
      .attr("cursor", "pointer")
      .attr("opacity", (d) => d.nodeType === "folder" ? 0.9 : 0.7)
      .on("mouseenter", function (event, d) {
        select(this)
          .attr("opacity", 1)
          .attr("stroke", "#ffffff")
          .attr("stroke-width", 2)
        // Highlight connected
        linkGroup
          .attr("stroke-opacity", (l: any) =>
            l.source.id === d.id || l.target.id === d.id ? 0.6 : 0.05
          )
          .attr("stroke-width", (l: any) =>
            l.source.id === d.id || l.target.id === d.id ? 1.5 : 0.5
          )
          .attr("stroke", (l: any) =>
            l.source.id === d.id || l.target.id === d.id ? getNodeColor(d) : "#334155"
          )
        nodeGroup.attr("opacity", (n: any) => {
          if (n.id === d.id) return 1
          const connected = links.some(
            (l: any) =>
              (l.source.id === d.id && l.target.id === n.id) ||
              (l.target.id === d.id && l.source.id === n.id)
          )
          return connected ? 1 : 0.15
        })
        setHoveredNode(d)
        setTooltipPos({ x: event.clientX, y: event.clientY })
      })
      .on("mousemove", function (event) {
        setTooltipPos({ x: event.clientX, y: event.clientY })
      })
      .on("mouseleave", function () {
        nodeGroup.attr("opacity", (d: any) => d.nodeType === "folder" ? 0.9 : 0.7)
          .attr("stroke", (d: any) => d.nodeType === "folder" ? "rgba(255,255,255,0.3)" : "none")
          .attr("stroke-width", (d: any) => d.nodeType === "folder" ? 1.5 : 0)
        linkGroup
          .attr("stroke-opacity", 0.15)
          .attr("stroke-width", 0.5)
          .attr("stroke", "#334155")
        setHoveredNode(null)
      })

    // Labels only for folders
    const labelGroup = g
      .append("g")
      .attr("class", "labels")
      .selectAll("text")
      .data(nodes.filter((n) => n.nodeType === "folder"))
      .join("text")
      .text((d) => d.label)
      .attr("font-size", (d) => {
        const r = getNodeRadius(d)
        return Math.max(6, Math.min(11, r * 0.8))
      })
      .attr("fill", "#e2e8f0")
      .attr("text-anchor", "middle")
      .attr("dy", (d) => getNodeRadius(d) + 12)
      .attr("pointer-events", "none")
      .attr("font-family", "system-ui, sans-serif")

    // Drag
    function dragstarted(event: any, d: any) {
      if (!event.active) simulationRef.current?.alphaTarget(0.3).restart()
      d.fx = d.x
      d.fy = d.y
    }
    function dragged(event: any, d: any) {
      d.fx = event.x
      d.fy = event.y
    }
    function dragended(event: any, d: any) {
      if (!event.active) simulationRef.current?.alphaTarget(0)
      d.fx = null
      d.fy = null
    }

    nodeGroup.call(
      d3Drag<SVGCircleElement, GraphNode>()
        .on("start", dragstarted)
        .on("drag", dragged)
        .on("end", dragended) as any
    )

    // Simulation
    const simulation = forceSimulation<GraphNode>(nodes)
      .force(
        "link",
        forceLink<GraphNode, GraphLink>(links)
          .id((d) => d.id)
          .distance((l: any) => {
            const src = l.source as GraphNode
            const tgt = l.target as GraphNode
            if (src.nodeType === "folder" && tgt.nodeType === "folder") return 60
            return 30
          })
          .strength(0.8)
      )
      .force("charge", forceManyBody().strength((d: any) => d.nodeType === "folder" ? -200 : -30))
      .force("center", forceCenter(0, 0))
      .force("collision", forceCollide<GraphNode>().radius((d) => getNodeRadius(d) + 3))
      .force("x", forceX(0).strength(0.03))
      .force("y", forceY(0).strength(0.03))
      .on("tick", () => {
        linkGroup
          .attr("x1", (d: any) => d.source.x)
          .attr("y1", (d: any) => d.source.y)
          .attr("x2", (d: any) => d.target.x)
          .attr("y2", (d: any) => d.target.y)

        nodeGroup.attr("cx", (d: any) => d.x).attr("cy", (d: any) => d.y)

        labelGroup.attr("x", (d: any) => d.x).attr("y", (d: any) => d.y)
      })

    simulationRef.current = simulation

    return () => {
      simulation.stop()
    }
  }, [nodes, links])

  const handleZoomIn = useCallback(() => {
    if (!svgRef.current) return
    const svg = select(svgRef.current)
    const zoomBehavior = (svgRef.current as any).__zoomBehavior
    if (zoomBehavior) svg.transition().duration(300).call(zoomBehavior.scaleBy, 1.5)
  }, [])

  const handleZoomOut = useCallback(() => {
    if (!svgRef.current) return
    const svg = select(svgRef.current)
    const zoomBehavior = (svgRef.current as any).__zoomBehavior
    if (zoomBehavior) svg.transition().duration(300).call(zoomBehavior.scaleBy, 0.67)
  }, [])

  const handleFitView = useCallback(() => {
    if (!svgRef.current || !containerRef.current) return
    const svg = select(svgRef.current)
    const zoomBehavior = (svgRef.current as any).__zoomBehavior
    const width = containerRef.current.clientWidth
    const height = containerRef.current.clientHeight
    if (zoomBehavior) {
      svg
        .transition()
        .duration(500)
        .call(zoomBehavior.transform, zoomIdentity.translate(width / 2, height / 2).scale(0.6))
    }
  }, [])

  return (
    <div ref={containerRef} className="relative w-full h-full bg-[#0f1117]">
      <svg
        ref={svgRef}
        className="w-full h-full"
        style={{ background: "radial-gradient(circle at 50% 50%, #1a1d2e 0%, #0f1117 70%)" }}
      />

      {/* Zoom controls */}
      <div className="absolute bottom-4 right-4 flex flex-col gap-1">
        <Button variant="secondary" size="icon" className="h-8 w-8 bg-gray-800/80 hover:bg-gray-700" onClick={handleZoomIn}>
          <IconZoomIn className="h-4 w-4" />
        </Button>
        <Button variant="secondary" size="icon" className="h-8 w-8 bg-gray-800/80 hover:bg-gray-700" onClick={handleZoomOut}>
          <IconZoomOut className="h-4 w-4" />
        </Button>
        <Button variant="secondary" size="icon" className="h-8 w-8 bg-gray-800/80 hover:bg-gray-700" onClick={handleFitView}>
          <IconFocusCentered className="h-4 w-4" />
        </Button>
      </div>

      {/* Legend */}
      <div className="absolute top-4 left-4 bg-gray-900/90 rounded-lg p-3 text-xs space-y-2 border border-gray-800">
        <div className="text-gray-400 font-medium mb-1">Carpetas</div>
        {Object.entries(FOLDER_COLORS).filter(([k]) => k !== "unknown").map(([key, color]) => (
          <div key={key} className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full" style={{ backgroundColor: color }} />
            <span className="text-gray-300 capitalize">{key}</span>
          </div>
        ))}
        <div className="border-t border-gray-700 my-1" />
        <div className="text-gray-400 font-medium mb-1">Documentos</div>
        {Object.entries(DOC_COLORS).filter(([k]) => k !== "unknown").map(([key, color]) => (
          <div key={key} className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
            <span className="text-gray-300 capitalize">{key}</span>
          </div>
        ))}
      </div>

      {/* Tooltip */}
      {hoveredNode && (
        <div
          className="fixed z-50 bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 pointer-events-none shadow-xl"
          style={{ left: tooltipPos.x + 12, top: tooltipPos.y - 10 }}
        >
          <div className="flex items-center gap-2 mb-1">
            {hoveredNode.nodeType === "folder" ? (
              <IconFolder className="h-4 w-4 text-amber-500" />
            ) : (
              <IconFile className="h-4 w-4 text-blue-400" />
            )}
            <span className="text-sm font-medium text-gray-100">{hoveredNode.label}</span>
          </div>
          <div className="text-xs text-gray-400">
            {hoveredNode.nodeType === "folder" ? (
              <>
                <span className="capitalize">{hoveredNode.folderType}</span>
                {hoveredNode.docCount ? ` · ${hoveredNode.docCount} docs` : ""}
              </>
            ) : (
              <span className="capitalize">{hoveredNode.semanticType}</span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ============================================================================
// Main Page
// ============================================================================

export default function KnowledgeTreePage() {
  const { isLoaded, isAuthenticated } = useAuth()
  const router = useRouter()
  const apiClient = useApiClient()

  const [graphNodes, setGraphNodes] = useState<GraphNode[]>([])
  const [graphLinks, setGraphLinks] = useState<GraphLink[]>([])
  const [stats, setStats] = useState<TreeStats | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (isLoaded && isAuthenticated) {
      loadData()
    }
  }, [isLoaded, isAuthenticated])

  useEffect(() => {
    if (isLoaded && !isAuthenticated) {
      router.push("/auth/sign-in")
    }
  }, [isLoaded, isAuthenticated, router])

  const loadData = async () => {
    setIsLoading(true)
    setError(null)

    try {
      const [structureRes, statsRes] = await Promise.all([
        apiClient.get<GraphStructure>("/weaviate/tree/graph/structure"),
        apiClient.get<TreeStats>("/weaviate/tree/stats"),
      ])

      if (statsRes.data) setStats(statsRes.data)

      if (structureRes.error) {
        setError(structureRes.error)
        return
      }

      const data = structureRes.data
      if (!data || data.nodes.length === 0) {
        setGraphNodes([])
        setGraphLinks([])
        return
      }

      const nodes: GraphNode[] = data.nodes.map((n) => ({
        id: n.id,
        label: n.label,
        nodeType: n.node_type,
        folderType: n.folder_type,
        semanticType: n.semantic_type,
        docCount: n.doc_count,
      }))

      const links: GraphLink[] = data.edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
      }))

      setGraphNodes(nodes)
      setGraphLinks(links)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cargar el grafo")
    } finally {
      setIsLoading(false)
    }
  }

  if (!isLoaded) {
    return (
      <div className="flex items-center justify-center h-screen bg-background">
        <IconLoader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  if (!isAuthenticated) return null

  const uniqueTypes = stats ? Object.keys(stats.types_breakdown).length : 0
  const uniqueDomains = stats ? Object.keys(stats.domains_breakdown).length : 0

  return (
    <SidebarProvider>
      <AppSidebar variant="inset" />

      <SidebarInset>
        {/* Compact header with stats inline */}
        <header className="h-10 border-b flex items-center gap-2 px-3 shrink-0">
          <SidebarTrigger className="-ml-1" />
          <div className="h-3.5 w-px bg-border" />
          <Link href="/" className="flex items-center gap-1.5 text-muted-foreground hover:text-foreground">
            <IconChevronLeft className="h-3.5 w-3.5" />
            <IconBrain className="h-4 w-4 text-primary" />
          </Link>
          <div className="h-3.5 w-px bg-border" />
          <IconBinaryTree className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-semibold text-foreground">Knowledge Tree</span>

          {/* Inline stats */}
          <div className="ml-3 flex items-center gap-1.5">
            <span className="inline-flex items-center gap-1 rounded-md bg-amber-500/10 px-1.5 py-0.5 text-[11px] text-amber-500">
              <IconFolder className="h-3 w-3" />
              {stats?.total_folders ?? "-"}
            </span>
            <span className="inline-flex items-center gap-1 rounded-md bg-blue-500/10 px-1.5 py-0.5 text-[11px] text-blue-500">
              <IconFile className="h-3 w-3" />
              {stats?.total_documents ?? "-"}
            </span>
            <span className="inline-flex items-center gap-1 rounded-md bg-purple-500/10 px-1.5 py-0.5 text-[11px] text-purple-500">
              <IconCategory className="h-3 w-3" />
              {uniqueTypes}
            </span>
            <span className="inline-flex items-center gap-1 rounded-md bg-green-500/10 px-1.5 py-0.5 text-[11px] text-green-500">
              <IconBinaryTree className="h-3 w-3" />
              {uniqueDomains}
            </span>
          </div>

          <div className="ml-auto">
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={loadData} disabled={isLoading}>
              <IconRefresh className={`h-3.5 w-3.5 ${isLoading ? "animate-spin" : ""}`} />
            </Button>
          </div>
        </header>

        {/* Main */}
        <main className="flex-1 flex flex-col overflow-hidden">

          {/* Error */}
          {error && (
            <div className="px-4 py-2">
              <Alert variant="destructive">
                <IconAlertCircle className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            </div>
          )}

          {/* Graph canvas */}
          {isLoading ? (
            <div className="flex-1 flex items-center justify-center bg-[#0f1117]">
              <IconLoader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
          ) : graphNodes.length === 0 && !error ? (
            <div className="flex-1 flex items-center justify-center bg-[#0f1117]">
              <div className="text-center text-gray-500">
                <IconBinaryTree className="h-12 w-12 mx-auto mb-3 opacity-30" />
                <p className="text-lg font-medium">No hay datos en el grafo</p>
                <p className="text-sm">Indexa documentos para ver el Knowledge Tree</p>
              </div>
            </div>
          ) : (
            <ForceGraph nodes={graphNodes} links={graphLinks} />
          )}
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}
