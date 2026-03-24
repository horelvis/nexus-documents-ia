"use client"

import { useState, useEffect } from "react"
import dynamic from "next/dynamic"
import { useRouter } from "next/navigation"
import {
  IconNetwork,
  IconLoader2,
  IconAlertCircle,
  IconRefresh,
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
import { explainabilityApi } from "@/lib/services/explainability.service"
import type { ExplainNode, ExplainLink } from "./components/explainability-theme"
import { ExplainabilityStatsBar } from "./components/ExplainabilityStatsBar"
import { ExplainabilityLegend } from "./components/ExplainabilityLegend"
import { ExplainabilitySearchBar } from "./components/ExplainabilitySearchBar"
import { NodeDetailsDrawer } from "./components/NodeDetailsDrawer"

// Dynamic import to avoid SSR issues with Three.js / WebGL
const ExplainabilityGraph3D = dynamic(
  () => import("./components/ExplainabilityGraph3D"),
  {
    ssr: false,
    loading: () => (
      <div className="flex-1 flex items-center justify-center bg-[#07090f]">
        <div className="flex flex-col items-center gap-3">
          <IconLoader2 className="h-6 w-6 animate-spin text-cyan-500/60" />
          <span className="text-[11px] text-slate-600 tracking-widest uppercase">
            Cargando grafo 3D...
          </span>
        </div>
      </div>
    ),
  }
)

interface GraphStats {
  total_entities: number
  total_documents: number
  total_claims: number
  total_laws: number
  total_contradictions: number
}

export default function KnowledgeGraphPage() {
  const { isLoaded, isAuthenticated, tenantId } = useAuth()
  const router = useRouter()

  // ── State ──
  const [nodes, setNodes] = useState<ExplainNode[]>([])
  const [links, setLinks] = useState<ExplainLink[]>([])
  const [stats, setStats] = useState<GraphStats | null>(null)
  const [selectedNode, setSelectedNode] = useState<ExplainNode | null>(null)
  const [highlightedIds, setHighlightedIds] = useState<Set<string> | null>(null)
  const [focusNodeId, setFocusNodeId] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // ── Auth guard ──
  useEffect(() => {
    if (isLoaded && !isAuthenticated) router.push("/auth/sign-in")
  }, [isLoaded, isAuthenticated, router])

  // ── Load data ──
  useEffect(() => {
    if (isLoaded && isAuthenticated) loadData()
  }, [isLoaded, isAuthenticated]) // eslint-disable-line react-hooks/exhaustive-deps

  async function loadData() {
    if (!tenantId) return
    setIsLoading(true)
    setError(null)
    setSelectedNode(null)
    setHighlightedIds(null)
    setFocusNodeId(null)
    try {
      const res = await explainabilityApi.getExplainabilityGraph(tenantId)
      if (res.error) {
        setError(res.error)
        return
      }
      const data = res.data
      if (!data || data.nodes.length === 0) {
        setNodes([])
        setLinks([])
        setStats(null)
        return
      }
      // Map API types to ExplainNode / ExplainLink (shapes match directly)
      setNodes(data.nodes as unknown as ExplainNode[])
      setLinks(data.edges as unknown as ExplainLink[])
      setStats(data.stats)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cargar el grafo")
    } finally {
      setIsLoading(false)
    }
  }

  // ── Node click → open drawer ──
  function handleNodeClick(node: ExplainNode | null) {
    if (!node) {
      setSelectedNode(null)
      return
    }
    setSelectedNode((prev) => (prev?.id === node.id ? null : node))
  }

  // ── Navigate to a related node ──
  function handleNavigate(nodeId: string) {
    const target = nodes.find((n) => n.id === nodeId)
    if (target) {
      setSelectedNode(target)
      setFocusNodeId(nodeId)
    }
  }

  // ── Search filter ──
  function handleFilter(ids: Set<string> | null) {
    setHighlightedIds(ids)
  }

  function handleFocus(nodeId: string) {
    setFocusNodeId(nodeId)
  }

  // ── Auth loading guard ──
  if (!isLoaded) {
    return (
      <div className="flex items-center justify-center h-screen bg-[#07090f]">
        <IconLoader2 className="h-8 w-8 animate-spin text-cyan-500" />
      </div>
    )
  }

  if (!isAuthenticated) return null

  const emptyState = !isLoading && nodes.length === 0 && !error

  return (
    <SidebarProvider>
      <AppSidebar variant="inset" />
      <SidebarInset>
        {/* Header */}
        <header className="flex h-10 shrink-0 items-center gap-2 border-b border-white/[0.06] bg-[#07090f] px-3">
          <SidebarTrigger className="-ml-1" />
          <div className="h-3.5 w-px bg-slate-700/50" />

          {/* Title */}
          <div className="flex items-center gap-1.5">
            <IconNetwork className="h-3.5 w-3.5 text-cyan-500" />
            <span
              className="text-xs font-semibold text-slate-300 tracking-wide"
              style={{ fontFamily: "'JetBrains Mono', monospace" }}
            >
              Knowledge Graph
            </span>
          </div>

          {/* Stats inline */}
          {stats && (
            <div className="ml-3 flex-1 overflow-x-auto">
              <ExplainabilityStatsBar stats={stats} />
            </div>
          )}

          {/* Refresh */}
          <div className="ml-auto">
            <button
              onClick={loadData}
              disabled={isLoading}
              className="flex items-center justify-center h-7 w-7 rounded-md border border-white/[0.06] text-slate-500 hover:text-slate-300 hover:bg-white/[0.04] transition-colors disabled:opacity-40"
              title="Recargar"
            >
              <IconRefresh className={`h-3.5 w-3.5 ${isLoading ? "animate-spin" : ""}`} />
            </button>
          </div>
        </header>

        {/* Main */}
        <main className="flex flex-col flex-1 overflow-hidden bg-[#07090f]">
          {/* Error banner */}
          {error && (
            <div className="absolute top-12 left-1/2 -translate-x-1/2 z-30 w-[420px] mt-2">
              <Alert
                variant="destructive"
                className="bg-red-950/80 border-red-500/20 backdrop-blur-sm"
              >
                <IconAlertCircle className="h-4 w-4" />
                <AlertDescription className="text-xs">{error}</AlertDescription>
              </Alert>
            </div>
          )}

          {/* Graph area */}
          <div className="relative flex-1 overflow-hidden">
            {isLoading ? (
              <div className="flex-1 flex items-center justify-center h-full">
                <div className="flex flex-col items-center gap-3">
                  <IconLoader2 className="h-6 w-6 animate-spin text-cyan-500/60" />
                  <span className="text-[11px] text-slate-600 tracking-widest uppercase">
                    Cargando grafo de conocimiento...
                  </span>
                </div>
              </div>
            ) : emptyState ? (
              <div className="flex items-center justify-center h-full">
                <div className="text-center">
                  <IconNetwork className="h-12 w-12 mx-auto mb-3 text-slate-800" />
                  <p className="text-sm font-medium text-slate-500">Sin datos</p>
                  <p className="text-xs text-slate-700 mt-1">
                    Indexa documentos para construir el grafo.
                  </p>
                </div>
              </div>
            ) : (
              <ExplainabilityGraph3D
                nodes={nodes}
                links={links}
                highlightedIds={highlightedIds}
                onNodeClick={handleNodeClick}
                focusNodeId={focusNodeId}
                className="absolute inset-0"
              />
            )}

            {/* Search — top left overlay */}
            {!isLoading && nodes.length > 0 && (
              <ExplainabilitySearchBar
                nodes={nodes}
                onFilter={handleFilter}
                onFocus={handleFocus}
              />
            )}

            {/* Legend — bottom left overlay */}
            {!isLoading && nodes.length > 0 && <ExplainabilityLegend />}
          </div>
        </main>

        {/* Node details drawer — rendered outside main so it slides over correctly */}
        <NodeDetailsDrawer
          node={selectedNode}
          edges={links}
          allNodes={nodes}
          onClose={() => setSelectedNode(null)}
          onNavigate={handleNavigate}
        />
      </SidebarInset>
    </SidebarProvider>
  )
}
