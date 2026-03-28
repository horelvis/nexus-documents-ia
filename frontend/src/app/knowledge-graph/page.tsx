"use client"

import { useState, useEffect } from "react"
import dynamic from "next/dynamic"
import { useRouter, useSearchParams } from "next/navigation"
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
import {
  knowledgeTreeApi,
  buildTrustGraphData,
  type TrustGraphNode,
  type TrustGraphEdge,
  type EntityProperty,
  type Contradiction,
} from "@/lib/services/knowledge-tree.service"
import { EntitySearchBar } from "@/components/graph/EntitySearchBar"
import { ExplainabilityLegend } from "./components/ExplainabilityLegend"
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

export default function KnowledgeGraphPage() {
  const { isLoaded, isAuthenticated, tenantId } = useAuth()
  const router = useRouter()
  const searchParams = useSearchParams()

  // ── State ──
  const [nodes, setNodes] = useState<TrustGraphNode[]>([])
  const [links, setLinks] = useState<TrustGraphEdge[]>([])
  const [properties, setProperties] = useState<Map<string, EntityProperty[]>>(new Map())
  const [contradictions, setContradictions] = useState<Contradiction[]>([])
  const [selectedNode, setSelectedNode] = useState<TrustGraphNode | null>(null)
  const [highlightedIds, setHighlightedIds] = useState<Set<string> | null>(null)
  const [focusNodeId, setFocusNodeId] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // ── Auth guard ──
  useEffect(() => {
    if (isLoaded && !isAuthenticated) router.push("/auth/sign-in")
  }, [isLoaded, isAuthenticated, router])

  // ── Deep-link: ?entity= from chat entity tags ──
  const initialEntity = searchParams.get("entity")

  // ── Load data ──
  useEffect(() => {
    if (isLoaded && isAuthenticated && tenantId) {
      if (initialEntity) {
        loadGraph([decodeURIComponent(initialEntity)])
      } else {
        loadGraph()
      }
    }
  }, [isLoaded, isAuthenticated, tenantId, initialEntity]) // eslint-disable-line react-hooks/exhaustive-deps

  async function loadGraph(seedUris?: string[]) {
    if (!tenantId) return
    setIsLoading(true)
    setError(null)
    setSelectedNode(null)
    setHighlightedIds(null)
    setFocusNodeId(null)
    try {
      // If no seeds provided, fetch top entities by degree centrality
      let seeds = seedUris ?? []
      if (seeds.length === 0) {
        const topEntities = await knowledgeTreeApi.getTopEntities(tenantId, 5)
        seeds = topEntities.map((e) => e.uri)
      }
      if (seeds.length === 0) {
        setNodes([])
        setLinks([])
        setIsLoading(false)
        return
      }
      const response = await knowledgeTreeApi.getTripleNeighbors(
        tenantId, seeds, 2, 150,
      )
      const { nodes: n, edges: e, properties: props, contradictions: contras } = buildTrustGraphData(response.edges)
      setNodes(n)
      setLinks(e)
      setProperties(props)
      setContradictions(contras)

      // If loaded from entity deep-link, focus on the seed
      if (seedUris?.length === 1) {
        setFocusNodeId(seedUris[0])
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cargar el grafo")
    } finally {
      setIsLoading(false)
    }
  }

  // ── Node click → open drawer ──
  function handleNodeClick(node: TrustGraphNode | null) {
    if (!node) {
      setSelectedNode(null)
      return
    }
    setSelectedNode((prev) => (prev?.id === node.id ? null : node))
  }

  // ── Navigate to a related node ──
  function handleNavigate(nodeUri: string) {
    const target = nodes.find((n) => n.id === nodeUri)
    if (target) {
      setSelectedNode(target)
      setFocusNodeId(nodeUri)
    } else {
      // Entity not in current subgraph — reload centered on it
      loadGraph([nodeUri])
    }
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
          {nodes.length > 0 && (
            <div className="ml-3 flex items-center gap-3 text-[10px] text-slate-500 font-mono">
              <span>{nodes.length} nodos</span>
              <span>{links.length} relaciones</span>
              {contradictions.length > 0 && (
                <span className="text-rose-400">{contradictions.length} conflictos</span>
              )}
            </div>
          )}

          {/* Refresh */}
          <div className="ml-auto">
            <button
              onClick={() => loadGraph()}
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

            {/* Entity search — top left overlay */}
            {!isLoading && tenantId && (
              <EntitySearchBar
                tenantId={tenantId}
                onSelect={(entity) => {
                  loadGraph([entity.entity_uri])
                }}
                className="absolute top-4 left-4 w-72 z-10"
              />
            )}

            {/* Legend — bottom left overlay */}
            {!isLoading && nodes.length > 0 && <ExplainabilityLegend />}
          </div>
        </main>

        {/* Node details drawer */}
        <NodeDetailsDrawer
          node={selectedNode}
          edges={links}
          allNodes={nodes}
          properties={selectedNode ? (properties.get(selectedNode.id) ?? []) : []}
          contradictions={contradictions}
          onClose={() => setSelectedNode(null)}
          onNavigate={handleNavigate}
        />
      </SidebarInset>
    </SidebarProvider>
  )
}
