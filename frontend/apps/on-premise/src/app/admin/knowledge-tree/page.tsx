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
  IconScale,
  IconSearch,
  IconX,
} from "@tabler/icons-react"
import {
  SidebarProvider,
  SidebarInset,
  SidebarTrigger,
  Alert,
  AlertDescription,
  Button,
  Input,
  Badge,
} from "@/components/ui"
import { useApiClient } from "@/lib/api-client"
import { useAuth } from "@/contexts/auth-context"
import { AppSidebar } from "@/components/layout/app-sidebar"
import type { GraphStructure, TreeStats, GraphViewMode } from "@/lib/services/knowledge-tree.service"

// ============================================================================
// Types
// ============================================================================

interface GraphNode extends SimulationNodeDatum {
  id: string
  label: string
  nodeType: "folder" | "document" | "law"
  folderType?: string
  semanticType?: string
  docCount?: number
  // Legal graph fields
  domain?: string
  status?: string
  title?: string
}

interface GraphLink extends SimulationLinkDatum<GraphNode> {
  id: string
  label?: string
}

// ============================================================================
// Color palettes
// ============================================================================

// Dynamic color palette — colors are assigned to folder/doc types at runtime
// so any new type automatically gets a distinct color.
const COLOR_PALETTE = [
  "#6366f1", // Indigo
  "#06b6d4", // Cyan
  "#8b5cf6", // Purple
  "#22c55e", // Green
  "#f59e0b", // Amber
  "#ec4899", // Pink
  "#14b8a6", // Teal
  "#f97316", // Orange
  "#3b82f6", // Blue
  "#ef4444", // Red
  "#a855f7", // Violet
  "#0ea5e9", // Sky
  "#84cc16", // Lime
  "#e879f9", // Fuchsia
  "#fb923c", // Light orange
]

const SPECIAL_FOLDER_COLORS: Record<string, string> = {
  virtual: "#64748b",
  unknown: "#94a3b8",
}

// Stable color assignment: same type always gets same color across renders
const typeColorCache = new Map<string, string>()
let nextColorIdx = 0

function getTypeColor(type: string): string {
  if (SPECIAL_FOLDER_COLORS[type]) return SPECIAL_FOLDER_COLORS[type]
  let color = typeColorCache.get(type)
  if (!color) {
    color = COLOR_PALETTE[nextColorIdx % COLOR_PALETTE.length]
    nextColorIdx++
    typeColorCache.set(type, color)
  }
  return color
}

const LAW_DOMAIN_COLORS: Record<string, string> = {
  labor: "#ef4444",
  fiscal: "#f59e0b",
  privacy: "#8b5cf6",
  mercantile: "#06b6d4",
  civil: "#3b82f6",
  administrative: "#64748b",
  compliance: "#f97316",
  ip: "#ec4899",
  commerce: "#22c55e",
  real_estate: "#14b8a6",
  education: "#a855f7",
  general: "#94a3b8",
}

function getNodeColor(node: GraphNode): string {
  if (node.nodeType === "law") {
    return LAW_DOMAIN_COLORS[node.domain || "general"] || LAW_DOMAIN_COLORS.general
  }
  if (node.nodeType === "folder") {
    return getTypeColor(node.folderType || "unknown")
  }
  return getTypeColor(node.semanticType || "unknown")
}

function getNodeRadius(node: GraphNode): number {
  if (node.nodeType === "law") return 14
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
  viewMode,
  highlightedNodeIds,
}: {
  nodes: GraphNode[]
  links: GraphLink[]
  viewMode: GraphViewMode
  highlightedNodeIds?: Set<string> | null
}) {
  // Derive legend entries from actual data (dynamic types)
  const folderTypes = Array.from(new Set(nodes.filter(n => n.nodeType === "folder").map(n => n.folderType || "unknown")))
    .filter(t => t !== "virtual" && t !== "unknown")
  const docTypes = Array.from(new Set(nodes.filter(n => n.nodeType === "document").map(n => n.semanticType || "unknown")))
    .filter(t => t !== "unknown")

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

    ;(svgRef.current as any).__zoomBehavior = zoomBehavior

    // Links — same visual style as legal graph (labeled, visible)
    const linkGroup = g
      .append("g")
      .attr("class", "links")
      .selectAll("line")
      .data(links)
      .join("line")
      .attr("stroke", "#475569")
      .attr("stroke-opacity", (d: any) => {
        if (highlightedNodeIds && highlightedNodeIds.size > 0) {
          const srcId = typeof d.source === "object" ? d.source.id : d.source
          const tgtId = typeof d.target === "object" ? d.target.id : d.target
          return (highlightedNodeIds.has(srcId) && highlightedNodeIds.has(tgtId)) ? 0.5 : 0.03
        }
        return d.label ? 0.4 : 0.15
      })
      .attr("stroke-width", (d: any) => d.label ? 1.5 : 0.5)
      .attr("stroke-dasharray", (d: any) => {
        if (d.label === "DEROGATES") return "4 2"
        if (d.label === "MODIFIES") return "2 2"
        if (d.label === "HAS_DOCUMENT") return "2 2"
        return "none"
      })

    // Edge labels (both structural and legal)
    g.append("g")
      .attr("class", "edge-labels")
      .selectAll("text")
      .data(links.filter((l) => l.label))
      .join("text")
      .text((d) => d.label || "")
      .attr("font-size", 7)
      .attr("fill", "#64748b")
      .attr("text-anchor", "middle")
      .attr("pointer-events", "none")
      .attr("font-family", "system-ui, sans-serif")

    // Nodes
    const nodeGroup = g
      .append("g")
      .attr("class", "nodes")
      .selectAll("circle")
      .data(nodes)
      .join("circle")
      .attr("r", (d) => getNodeRadius(d))
      .attr("fill", (d) => getNodeColor(d))
      .attr("stroke", (d) => d.nodeType === "document" ? "none" : "rgba(255,255,255,0.3)")
      .attr("stroke-width", (d) => d.nodeType === "document" ? 0 : 1.5)
      .attr("cursor", "pointer")
      .attr("opacity", (d) => {
        if (highlightedNodeIds && highlightedNodeIds.size > 0) {
          return highlightedNodeIds.has(d.id) ? 1 : 0.12
        }
        return d.nodeType === "document" ? 0.7 : 0.9
      })
      .on("mouseenter", function (event, d) {
        select(this)
          .attr("opacity", 1)
          .attr("stroke", "#ffffff")
          .attr("stroke-width", 2)
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
        nodeGroup.attr("opacity", (d: any) => {
            if (highlightedNodeIds && highlightedNodeIds.size > 0) {
              return highlightedNodeIds.has(d.id) ? 1 : 0.12
            }
            return d.nodeType === "document" ? 0.7 : 0.9
          })
          .attr("stroke", (d: any) => d.nodeType === "document" ? "none" : "rgba(255,255,255,0.3)")
          .attr("stroke-width", (d: any) => d.nodeType === "document" ? 0 : 1.5)
        linkGroup
          .attr("stroke-opacity", (d: any) => d.label ? 0.4 : 0.15)
          .attr("stroke-width", (d: any) => d.label ? 1.5 : 0.5)
          .attr("stroke", "#475569")
        setHoveredNode(null)
      })

    // Labels — show all nodes (same as legal)
    const labelNodes = nodes
    const labelGroup = g
      .append("g")
      .attr("class", "labels")
      .selectAll("text")
      .data(labelNodes)
      .join("text")
      .text((d) => d.label)
      .attr("font-size", (d) => {
        if (d.nodeType === "law") return 9
        const r = getNodeRadius(d)
        return Math.max(6, Math.min(11, r * 0.8))
      })
      .attr("fill", (d) => {
        if (highlightedNodeIds && highlightedNodeIds.size > 0) {
          return highlightedNodeIds.has(d.id) ? "#ffffff" : "#334155"
        }
        return "#e2e8f0"
      })
      .attr("text-anchor", "middle")
      .attr("dy", (d) => getNodeRadius(d) + 12)
      .attr("pointer-events", "none")
      .attr("font-family", "system-ui, sans-serif")
      .attr("font-weight", (d) => {
        if (highlightedNodeIds && highlightedNodeIds.size > 0 && highlightedNodeIds.has(d.id)) return "600"
        return d.nodeType === "law" ? "600" : "400"
      })

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

    // Simulation — same force config for both views
    const chargeStrength = -300
    const linkDistance = 100

    const simulation = forceSimulation<GraphNode>(nodes)
      .force(
        "link",
        forceLink<GraphNode, GraphLink>(links)
          .id((d) => d.id)
          .distance(linkDistance as any)
          .strength(0.8)
      )
      .force("charge", forceManyBody().strength(chargeStrength as any))
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

        // Update edge labels position
        g.selectAll(".edge-labels text")
          .attr("x", (d: any) => ((d.source.x || 0) + (d.target.x || 0)) / 2)
          .attr("y", (d: any) => ((d.source.y || 0) + (d.target.y || 0)) / 2)
      })

    simulationRef.current = simulation

    return () => {
      simulation.stop()
    }
  }, [nodes, links, viewMode, highlightedNodeIds])

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
      <div className="absolute top-4 left-4 bg-gray-900/90 rounded-lg p-3 text-xs space-y-2 border border-gray-800 max-h-[60vh] overflow-y-auto">
        {viewMode === "legal" ? (
          <>
            <div className="text-gray-400 font-medium mb-1">Dominios legales</div>
            {Object.entries(LAW_DOMAIN_COLORS).filter(([k]) => k !== "general").map(([key, color]) => (
              <div key={key} className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: color }} />
                <span className="text-gray-300 capitalize">{key.replace("_", " ")}</span>
              </div>
            ))}
          </>
        ) : (
          <>
            {folderTypes.length > 0 && (
              <>
                <div className="text-gray-400 font-medium mb-1">Carpetas</div>
                {folderTypes.map((type) => (
                  <div key={type} className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full" style={{ backgroundColor: getTypeColor(type) }} />
                    <span className="text-gray-300 capitalize">{type.replace(/_/g, " ")}</span>
                  </div>
                ))}
              </>
            )}
            {docTypes.length > 0 && (
              <>
                <div className="border-t border-gray-700 my-1" />
                <div className="text-gray-400 font-medium mb-1">Documentos</div>
                {docTypes.map((type) => (
                  <div key={type} className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full" style={{ backgroundColor: getTypeColor(type) }} />
                    <span className="text-gray-300 capitalize">{type.replace(/_/g, " ")}</span>
                  </div>
                ))}
              </>
            )}
          </>
        )}
      </div>

      {/* Tooltip */}
      {hoveredNode && (
        <div
          className="fixed z-50 bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 pointer-events-none shadow-xl max-w-sm"
          style={{ left: tooltipPos.x + 12, top: tooltipPos.y - 10 }}
        >
          <div className="flex items-center gap-2 mb-1">
            {hoveredNode.nodeType === "law" ? (
              <IconScale className="h-4 w-4 text-amber-500" />
            ) : hoveredNode.nodeType === "folder" ? (
              <IconFolder className="h-4 w-4 text-amber-500" />
            ) : (
              <IconFile className="h-4 w-4 text-blue-400" />
            )}
            <span className="text-sm font-medium text-gray-100">{hoveredNode.label}</span>
          </div>
          <div className="text-xs text-gray-400">
            {hoveredNode.nodeType === "law" ? (
              <>
                <div className="capitalize">{hoveredNode.domain} · {hoveredNode.status}</div>
                {hoveredNode.title && (
                  <div className="mt-1 text-gray-500 line-clamp-2">{hoveredNode.title}</div>
                )}
              </>
            ) : hoveredNode.nodeType === "folder" ? (
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

  const [viewMode, setViewMode] = useState<GraphViewMode>("structural")
  const [graphNodes, setGraphNodes] = useState<GraphNode[]>([])
  const [graphLinks, setGraphLinks] = useState<GraphLink[]>([])
  const [stats, setStats] = useState<TreeStats | null>(null)
  const [legalNodeCount, setLegalNodeCount] = useState<number | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Search state
  const [searchQuery, setSearchQuery] = useState("")
  const [isSearching, setIsSearching] = useState(false)
  const [highlightedNodeIds, setHighlightedNodeIds] = useState<Set<string> | null>(null)
  const [searchResultCount, setSearchResultCount] = useState<number | null>(null)
  // Store full graph for restoring after search clear
  const fullGraphRef = useRef<{ nodes: GraphNode[]; links: GraphLink[] } | null>(null)

  useEffect(() => {
    if (isLoaded && isAuthenticated) {
      clearSearch()
      loadData()
    }
  }, [isLoaded, isAuthenticated, viewMode])

  useEffect(() => {
    if (isLoaded && !isAuthenticated) {
      router.push("/auth/sign-in")
    }
  }, [isLoaded, isAuthenticated, router])

  const loadData = async () => {
    setIsLoading(true)
    setError(null)

    try {
      if (viewMode === "structural") {
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
          nodeType: n.node_type as "folder" | "document",
          folderType: n.folder_type,
          semanticType: n.semantic_type,
          docCount: n.doc_count,
        }))

        const links: GraphLink[] = data.edges.map((e) => ({
          id: e.id,
          source: e.source,
          target: e.target,
          label: e.label,
        }))

        setGraphNodes(nodes)
        setGraphLinks(links)
        fullGraphRef.current = { nodes, links }
      } else {
        // Legal graph
        const structureRes = await apiClient.get<GraphStructure>("/weaviate/legal/graph/structure")

        if (structureRes.error) {
          setError(structureRes.error)
          return
        }

        const data = structureRes.data
        if (!data || data.nodes.length === 0) {
          setGraphNodes([])
          setGraphLinks([])
          setLegalNodeCount(0)
          return
        }

        setLegalNodeCount(data.nodes.length)

        const nodes: GraphNode[] = data.nodes.map((n) => ({
          id: n.id,
          label: n.label,
          nodeType: "law" as const,
          domain: n.domain,
          status: n.status,
          title: n.title,
        }))

        const links: GraphLink[] = data.edges.map((e) => ({
          id: e.id,
          source: e.source,
          target: e.target,
          label: e.label,
        }))

        setGraphNodes(nodes)
        setGraphLinks(links)
        fullGraphRef.current = { nodes, links }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cargar el grafo")
    } finally {
      setIsLoading(false)
    }
  }

  // ── Search ────────────────────────────────────────────────────────────────
  const handleSearch = async () => {
    const q = searchQuery.trim()
    if (!q) return

    setIsSearching(true)
    setError(null)

    try {
      if (viewMode === "legal") {
        // Backend search: returns filtered subgraph with neighbors
        const res = await apiClient.get<GraphStructure & { query?: { matched_count?: number } }>(
          `/weaviate/legal/graph/search?q=${encodeURIComponent(q)}&include_neighbors=true&limit=50`
        )

        if (res.error) {
          setError(res.error)
          return
        }

        if (res.data && res.data.nodes.length > 0) {
          const nodes: GraphNode[] = res.data.nodes.map((n) => ({
            id: n.id,
            label: n.label,
            nodeType: "law" as const,
            domain: n.domain,
            status: n.status,
            title: n.title,
          }))
          const links: GraphLink[] = res.data.edges.map((e) => ({
            id: e.id,
            source: e.source,
            target: e.target,
            label: e.label,
          }))
          setGraphNodes(nodes)
          setGraphLinks(links)
          setHighlightedNodeIds(null) // all visible nodes are results
          setSearchResultCount((res.data as any).query?.matched_count ?? nodes.length)
        } else {
          setSearchResultCount(0)
        }
      } else {
        // Client-side search: highlight matching nodes in the full graph
        const full = fullGraphRef.current
        if (!full) return

        const qLower = q.toLowerCase()
        const matchedIds = new Set<string>()

        for (const node of full.nodes) {
          const label = node.label.toLowerCase()
          const folderType = (node.folderType || "").toLowerCase()
          const semanticType = (node.semanticType || "").toLowerCase()
          if (label.includes(qLower) || folderType.includes(qLower) || semanticType.includes(qLower)) {
            matchedIds.add(node.id)
          }
        }

        // Add neighbors of matched nodes
        const neighborIds = new Set<string>()
        for (const link of full.links) {
          const srcId = typeof link.source === "object" ? (link.source as GraphNode).id : link.source as string
          const tgtId = typeof link.target === "object" ? (link.target as GraphNode).id : link.target as string
          if (matchedIds.has(srcId)) neighborIds.add(tgtId)
          if (matchedIds.has(tgtId)) neighborIds.add(srcId)
        }

        const allHighlighted = new Set([...matchedIds, ...neighborIds])
        setHighlightedNodeIds(allHighlighted)
        setSearchResultCount(matchedIds.size)

        // Restore full graph data in case it was replaced by previous legal search
        setGraphNodes(full.nodes)
        setGraphLinks(full.links)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error en la búsqueda")
    } finally {
      setIsSearching(false)
    }
  }

  const clearSearch = () => {
    setSearchQuery("")
    setHighlightedNodeIds(null)
    setSearchResultCount(null)
    // Restore full graph if we had replaced it (legal search)
    if (fullGraphRef.current && viewMode === "legal") {
      setGraphNodes(fullGraphRef.current.nodes)
      setGraphLinks(fullGraphRef.current.links)
    }
  }

  const handleSearchKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleSearch()
    if (e.key === "Escape") clearSearch()
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

          {/* Graph selector */}
          <div className="ml-3 flex items-center rounded-md border border-border overflow-hidden">
            <button
              onClick={() => setViewMode("structural")}
              className={`px-2 py-0.5 text-[11px] font-medium transition-colors ${
                viewMode === "structural"
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted"
              }`}
            >
              <IconBinaryTree className="h-3 w-3 inline mr-1" />
              Structural
            </button>
            <button
              onClick={() => setViewMode("legal")}
              className={`px-2 py-0.5 text-[11px] font-medium transition-colors ${
                viewMode === "legal"
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted"
              }`}
            >
              <IconScale className="h-3 w-3 inline mr-1" />
              Legal
            </button>
          </div>

          {/* Inline stats */}
          <div className="ml-3 flex items-center gap-1.5">
            {viewMode === "structural" ? (
              <>
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
              </>
            ) : (
              <>
                <span className="inline-flex items-center gap-1 rounded-md bg-amber-500/10 px-1.5 py-0.5 text-[11px] text-amber-500">
                  <IconScale className="h-3 w-3" />
                  {legalNodeCount ?? "-"} leyes
                </span>
              </>
            )}
          </div>

          {/* Search */}
          <div className="ml-auto flex items-center gap-1.5">
            <div className="relative flex items-center">
              <IconSearch className="absolute left-2 h-3 w-3 text-gray-500 pointer-events-none" />
              <input
                type="text"
                placeholder={viewMode === "legal" ? "Buscar ley..." : "Buscar nodo..."}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={handleSearchKeyDown}
                className="h-7 w-40 rounded-md border border-border bg-background pl-7 pr-7 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
              />
              {searchQuery && (
                <button
                  onClick={clearSearch}
                  className="absolute right-1.5 text-gray-500 hover:text-foreground"
                >
                  <IconX className="h-3 w-3" />
                </button>
              )}
            </div>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={handleSearch}
              disabled={isSearching || !searchQuery.trim()}
            >
              {isSearching ? (
                <IconLoader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <IconSearch className="h-3.5 w-3.5" />
              )}
            </Button>
            {searchResultCount !== null && (
              <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                {searchResultCount} resultado{searchResultCount !== 1 ? "s" : ""}
              </Badge>
            )}
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => { clearSearch(); loadData() }} disabled={isLoading}>
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
                <p className="text-sm">
                  {viewMode === "structural"
                    ? "Indexa documentos para ver el Knowledge Tree"
                    : "Ejecuta el seed de legislación o indexa BOE para poblar el grafo legal"
                  }
                </p>
              </div>
            </div>
          ) : (
            <ForceGraph nodes={graphNodes} links={graphLinks} viewMode={viewMode} highlightedNodeIds={highlightedNodeIds} />
          )}
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}
