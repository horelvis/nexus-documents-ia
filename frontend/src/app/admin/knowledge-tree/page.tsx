"use client"

import { useState, useEffect, useCallback } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import {
  IconBinaryTree,
  IconLoader2,
  IconRefresh,
  IconChevronLeft,
  IconBrain,
  IconAlertCircle,
} from "@tabler/icons-react"
import {
  SidebarProvider,
  SidebarInset,
  SidebarTrigger,
  Alert,
  AlertDescription,
} from "@/components/ui"
import { useAuth } from "@/contexts/auth-context"
import { AppSidebar } from "@/components/layout/app-sidebar"
import {
  knowledgeTreeApi,
  type TreeStats,
  type EntitySearchResult,
} from "@/lib/services/knowledge-tree.service"
import { ForceGraph } from "./components/ForceGraph"
import { SearchPanel } from "./components/SearchPanel"
import { GraphLegend } from "./components/GraphLegend"
import { StatsBar } from "./components/StatsBar"
import {
  apiNodesToSim,
  apiEdgesToSim,
  getNodeColor,
  type SimNode,
  type SimLink,
} from "./components/graph-theme"

export default function KnowledgeTreePage() {
  const { isLoaded, isAuthenticated } = useAuth()
  const router = useRouter()

  // ── State ──
  const [nodes, setNodes] = useState<SimNode[]>([])
  const [links, setLinks] = useState<SimLink[]>([])
  const [treeStats, setTreeStats] = useState<TreeStats | null>(null)
  const [highlightedIds, setHighlightedIds] = useState<Set<string> | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isSearching, setIsSearching] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedNode, setSelectedNode] = useState<SimNode | null>(null)

  // ── Auth guard ──
  useEffect(() => {
    if (isLoaded && !isAuthenticated) router.push("/auth/sign-in")
  }, [isLoaded, isAuthenticated, router])

  // ── Load data ──
  useEffect(() => {
    if (isLoaded && isAuthenticated) loadData()
  }, [isLoaded, isAuthenticated])

  const loadData = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    setHighlightedIds(null)
    setSelectedNode(null)

    try {
      const [statsRes, structureRes] = await Promise.all([
        knowledgeTreeApi.getStats(),
        knowledgeTreeApi.getGraphStructure(),
      ])

      if (statsRes.data) setTreeStats(statsRes.data)

      if (structureRes.error) {
        setError(structureRes.error)
        return
      }

      const data = structureRes.data
      if (!data || data.nodes.length === 0) {
        setNodes([])
        setLinks([])
        return
      }

      const simNodes = apiNodesToSim(data.nodes)
      const nodeIds = new Set(simNodes.map((n) => n.id))
      setNodes(simNodes)
      setLinks(apiEdgesToSim(data.edges, nodeIds))
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cargar el grafo")
    } finally {
      setIsLoading(false)
    }
  }, [])

  // ── Entity search ──
  const handleSearch = useCallback(async (query: string): Promise<EntitySearchResult[]> => {
    setIsSearching(true)
    try {
      const res = await knowledgeTreeApi.searchEntities(query, 30)
      return res.data || []
    } catch {
      return []
    } finally {
      setIsSearching(false)
    }
  }, [])

  // ── Select entity → load its subgraph ──
  const handleSelectEntity = useCallback(async (entity: EntitySearchResult) => {
    setIsLoading(true)
    setError(null)
    try {
      const res = await knowledgeTreeApi.getSubgraph(entity.name, 2, 100)
      if (res.error) {
        setError(res.error)
        return
      }
      const data = res.data
      if (!data || data.nodes.length === 0) return

      const simNodes = apiNodesToSim(data.nodes)
      const nodeIds = new Set(simNodes.map((n) => n.id))
      setNodes(simNodes)
      setLinks(apiEdgesToSim(data.edges, nodeIds))

      // Highlight root entities
      const rootSet = new Set(data.root_entities)
      const rootIds = data.nodes
        .filter((n) => rootSet.has(n.name))
        .map((n) => n.id)
      setHighlightedIds(rootIds.length > 0 ? new Set(rootIds) : null)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cargar subgrafo")
    } finally {
      setIsLoading(false)
    }
  }, [])

  // ── Node click → show details ──
  const handleNodeClick = useCallback((node: SimNode) => {
    setSelectedNode((prev) => prev?.id === node.id ? null : node)
  }, [])

  // ── Loading guard ──
  if (!isLoaded) {
    return (
      <div className="flex items-center justify-center h-screen bg-[#07090f]">
        <IconLoader2 className="h-8 w-8 animate-spin text-cyan-500" />
      </div>
    )
  }

  if (!isAuthenticated) return null

  return (
    <SidebarProvider>
      <AppSidebar variant="inset" />
      <SidebarInset>
        {/* Header */}
        <header className="kt-header">
          <SidebarTrigger className="-ml-1" />
          <div className="h-3.5 w-px bg-slate-700/50" />
          <Link href="/" className="flex items-center gap-1.5 text-slate-500 hover:text-slate-300 transition-colors">
            <IconChevronLeft className="h-3.5 w-3.5" />
            <IconBrain className="h-4 w-4 text-cyan-500" />
          </Link>
          <div className="h-3.5 w-px bg-slate-700/50" />

          {/* Title */}
          <div className="flex items-center gap-1.5">
            <IconBinaryTree className="h-3.5 w-3.5 text-slate-500" />
            <span className="text-xs font-semibold text-slate-300 tracking-wide">Knowledge Tree</span>
          </div>

          {/* Mode indicator */}
          <div className="ml-3 flex items-center gap-1.5 rounded-lg border border-white/[0.04] bg-white/[0.02] px-2.5 py-1">
            <IconBinaryTree className="h-3 w-3 text-cyan-500" />
            <span className="text-[11px] font-medium text-cyan-400 tracking-wide" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
              Grafo Unificado
            </span>
          </div>

          {/* Stats */}
          <div className="ml-3">
            <StatsBar
              treeStats={treeStats}
              legalStats={null}
              nodeCount={nodes.length}
              edgeCount={links.length}
            />
          </div>

          {/* Refresh */}
          <div className="ml-auto">
            <button
              onClick={loadData}
              disabled={isLoading}
              className="kt-control-btn"
              title="Recargar"
            >
              <IconRefresh className={`h-3.5 w-3.5 ${isLoading ? "animate-spin" : ""}`} />
            </button>
          </div>
        </header>

        {/* Main */}
        <main className="flex-1 flex overflow-hidden relative">
          {/* Error */}
          {error && (
            <div className="absolute top-3 left-1/2 -translate-x-1/2 z-30 w-[400px]">
              <Alert variant="destructive" className="bg-red-950/80 border-red-500/20 backdrop-blur-sm">
                <IconAlertCircle className="h-4 w-4" />
                <AlertDescription className="text-xs">{error}</AlertDescription>
              </Alert>
            </div>
          )}

          {/* Graph canvas */}
          {isLoading ? (
            <div className="flex-1 flex items-center justify-center bg-[#07090f]">
              <div className="flex flex-col items-center gap-3">
                <IconLoader2 className="h-6 w-6 animate-spin text-cyan-500/60" />
                <span className="text-[11px] text-slate-600 tracking-widest uppercase">Cargando grafo</span>
              </div>
            </div>
          ) : nodes.length === 0 && !error ? (
            <div className="flex-1 flex items-center justify-center bg-[#07090f]">
              <div className="text-center">
                <IconBinaryTree className="h-12 w-12 mx-auto mb-3 text-slate-800" />
                <p className="text-sm font-medium text-slate-500">Sin datos en el grafo</p>
                <p className="text-xs text-slate-700 mt-1">
                  Indexa documentos para ver el Knowledge Tree
                </p>
              </div>
            </div>
          ) : (
            <ForceGraph
              nodes={nodes}
              links={links}
              highlightedIds={highlightedIds}
              onNodeClick={handleNodeClick}
            />
          )}

          {/* Floating search panel — top left */}
          <div className="absolute top-3 left-3 z-20">
            <SearchPanel
              onSelectEntity={handleSelectEntity}
              onSearch={handleSearch}
              isSearching={isSearching}
            />
          </div>

          {/* Legend — bottom left */}
          <div className="absolute bottom-4 left-3 z-20">
            <GraphLegend viewMode="unified" />
          </div>

          {/* Selected node detail — bottom center */}
          {selectedNode && (
            <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-20 kt-tooltip emma-message-enter" style={{ minWidth: 260 }}>
              <div className="flex items-center gap-2 mb-2">
                <span
                  className="h-3 w-3 rounded-full shrink-0"
                  style={{ backgroundColor: getNodeColor(selectedNode) }}
                />
                <span className="font-semibold text-xs text-white">{selectedNode.name}</span>
                <button
                  onClick={() => setSelectedNode(null)}
                  className="ml-auto text-slate-600 hover:text-slate-300 transition-colors"
                >
                  <span className="text-[10px]">✕</span>
                </button>
              </div>
              <div className="text-[10px] text-slate-500 uppercase tracking-widest mb-1.5">{selectedNode.label}</div>
              <div className="space-y-1 text-[11px]">
                {Object.entries(selectedNode.properties).map(([key, val]) =>
                  val ? (
                    <div key={key} className="flex items-center justify-between gap-4">
                      <span className="text-slate-500">{key}</span>
                      <span className="text-slate-300 truncate max-w-[160px] text-right">{String(val)}</span>
                    </div>
                  ) : null
                )}
              </div>
            </div>
          )}
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}
