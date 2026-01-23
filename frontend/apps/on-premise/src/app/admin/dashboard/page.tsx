"use client"

/**
 * Admin Dashboard for NouxCube On-Premise
 *
 * Provides system administration features:
 * - System statistics (from /admin/stats)
 * - Weaviate service health
 * - Knowledge Graph stats
 * - Maintenance operations
 *
 * All data is fetched from the main backend API (/api/v1).
 * The backend proxies requests to microservices as needed.
 */

import { useState, useEffect } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import {
  IconDashboard,
  IconLoader2,
  IconRefresh,
  IconChevronLeft,
  IconBrain,
  IconDatabase,
  IconFile,
  IconFolder,
  IconAlertCircle,
  IconCircleCheck,
  IconTrash,
  IconReload,
  IconPlayerPlay,
  IconChartBar,
  IconActivity,
  IconServer,
  IconSchool,
  IconBinaryTree,
  IconChartPie,
  IconUsers,
  IconBuilding,
  IconHeart,
} from "@tabler/icons-react"
import {
  SidebarProvider,
  SidebarInset,
  SidebarTrigger,
  Alert,
  AlertDescription,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Button,
  Badge,
  Label,
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@nexus/shared/ui"
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from "@/components/ui/card"
import { Switch } from "@/components/ui/switch"
import { useApiClient } from "@/lib/api-client"
import { useAuth } from "@/contexts/auth-context"
import { AppSidebar } from "@/components/layout/app-sidebar"

// ============================================================================
// API Response Interfaces (matching real backend /admin/stats response)
// ============================================================================

interface SystemStats {
  users: {
    total: number
    active: number
  }
  tenants: {
    total: number
    active: number
  }
  documents: {
    total: number
    indexed: number
    error: number
    by_type: Record<string, number>
  }
  storage: {
    total_bytes: number
    total_mb: number
  }
}

interface WeaviateHealth {
  weaviate_service: {
    status: string
    weaviate_connected?: boolean
  }
  emma_ai: {
    status: string
    agents?: string[]
  }
  overall_status: string
  error?: string
}

interface KnowledgeStats {
  total_entities: number
  entities_by_type: Record<string, number>
  entities_by_domain: Record<string, number>
}

interface MaintenanceResult {
  message: string
  operations_performed: string[]
  duration_seconds: number
}

interface DeleteResult {
  deleted_count: number
  message: string
}

interface RecentDocument {
  id: string
  title: string
  type: string
  created_at: string
}

interface TopFolder {
  path: string
  count: number
}

interface SILGraphStats {
  tenant_id: string
  total_documents: number
  total_folders: number
  total_relationships: number
  types_breakdown: Record<string, number>
  domains_breakdown: Record<string, number>
  relationships_breakdown: Record<string, number>
  top_folders: TopFolder[]
  recent_documents: RecentDocument[]
  graph_name: string
  sil_enabled: boolean
  error?: string
}

interface SILReindexResult {
  success: boolean
  total_documents: number
  documents_processed: number
  documents_skipped: number
  errors: number
  message: string
}

interface BOEPreset {
  name: string
  description: string
  legislation_count: number
  legislation_ids: string[]
}

interface BOEDownloadResult {
  success: boolean
  boe_id: string
  title?: string
  indexed: boolean
  error?: string
}

interface PublicKnowledgeStats {
  total_documents: number
  documents_by_category: Record<string, number>
  documents_by_jurisdiction: Record<string, number>
}

interface KnowledgeExtractionResult {
  total_documents: number
  processed: number
  entities_extracted: number
  errors: number
  details: { document_id: string; title?: string; entities_count: number }[]
}

// ============================================================================
// Main Component
// ============================================================================

export default function AdminDashboardPage() {
  const { isLoaded, isAuthenticated, user } = useAuth()
  const router = useRouter()
  const apiClient = useApiClient()

  // Data states
  const [systemStats, setSystemStats] = useState<SystemStats | null>(null)
  const [weaviateHealth, setWeaviateHealth] = useState<WeaviateHealth | null>(null)
  const [knowledgeStats, setKnowledgeStats] = useState<KnowledgeStats | null>(null)
  const [silStats, setSilStats] = useState<SILGraphStats | null>(null)
  const [boePresets, setBoePresets] = useState<BOEPreset[]>([])
  const [publicKnowledgeStats, setPublicKnowledgeStats] = useState<PublicKnowledgeStats | null>(null)

  // Loading states
  const [isLoading, setIsLoading] = useState(true)
  const [isRunningMaintenance, setIsRunningMaintenance] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [isReindexingSil, setIsReindexingSil] = useState(false)
  const [isClearingSil, setIsClearingSil] = useState(false)
  const [isDownloadingBoe, setIsDownloadingBoe] = useState(false)
  const [isSyncingBoe, setIsSyncingBoe] = useState(false)
  const [isExtractingKnowledge, setIsExtractingKnowledge] = useState(false)

  // Error state
  const [error, setError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  // Maintenance options
  const [optimizeDatabase, setOptimizeDatabase] = useState(true)
  const [cleanOrphanedFiles, setCleanOrphanedFiles] = useState(true)
  const [rebuildSearchIndex, setRebuildSearchIndex] = useState(false)

  // Dialogs
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  const [showMaintenanceDialog, setShowMaintenanceDialog] = useState(false)
  const [showSilReindexDialog, setShowSilReindexDialog] = useState(false)
  const [showSilClearDialog, setShowSilClearDialog] = useState(false)
  const [showBoeDownloadDialog, setShowBoeDownloadDialog] = useState(false)
  const [showBoeSyncDialog, setShowBoeSyncDialog] = useState(false)
  const [showKnowledgeExtractDialog, setShowKnowledgeExtractDialog] = useState(false)

  // SIL options
  const [silFullReindex, setSilFullReindex] = useState(false)

  // BOE options
  const [selectedBoePreset, setSelectedBoePreset] = useState<string>("")
  const [boeDownloadResults, setBoeDownloadResults] = useState<BOEDownloadResult[]>([])
  const [boeSyncResults, setBoeSyncResults] = useState<any[]>([])

  // Knowledge extraction
  const [knowledgeExtractionResult, setKnowledgeExtractionResult] = useState<KnowledgeExtractionResult | null>(null)

  // Results
  const [maintenanceResult, setMaintenanceResult] = useState<MaintenanceResult | null>(null)
  const [silReindexResult, setSilReindexResult] = useState<SILReindexResult | null>(null)

  // ============================================================================
  // Effects
  // ============================================================================

  useEffect(() => {
    if (isLoaded && isAuthenticated) {
      loadAllStats()
    }
  }, [isLoaded, isAuthenticated])

  useEffect(() => {
    if (isLoaded && !isAuthenticated) {
      router.push('/auth/sign-in')
    }
  }, [isLoaded, isAuthenticated, router])

  // Clear success message after 5 seconds
  useEffect(() => {
    if (successMessage) {
      const timer = setTimeout(() => setSuccessMessage(null), 5000)
      return () => clearTimeout(timer)
    }
  }, [successMessage])

  // ============================================================================
  // Data Loading - Real API Calls
  // ============================================================================

  const loadAllStats = async () => {
    setIsLoading(true)
    setError(null)

    try {
      // Load all stats in parallel
      await Promise.all([
        loadSystemStats(),
        loadWeaviateHealth(),
        loadKnowledgeStats(),
        loadSilStats(),
        loadBoePresets(),
        loadPublicKnowledgeStats(),
      ])
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Error al cargar estadísticas'
      setError(errorMessage)
    } finally {
      setIsLoading(false)
    }
  }

  const loadSystemStats = async () => {
    try {
      // Call /admin/stats endpoint
      const response = await apiClient.get<SystemStats>('/admin/stats')
      if (!response.error && response.data) {
        setSystemStats(response.data)
      } else if (response.error) {
        console.error('System stats error:', response.error)
      }
    } catch (error) {
      console.error('Failed to load system stats:', error)
    }
  }

  const loadWeaviateHealth = async () => {
    try {
      // Call /weaviate/health endpoint
      const response = await apiClient.get<WeaviateHealth>('/weaviate/health')
      if (!response.error && response.data) {
        setWeaviateHealth(response.data)
      }
    } catch (error) {
      console.error('Failed to load Weaviate health:', error)
    }
  }

  const loadKnowledgeStats = async () => {
    try {
      // Call /weaviate/knowledge/stats endpoint
      const response = await apiClient.get<KnowledgeStats>('/weaviate/knowledge/stats')
      if (!response.error && response.data) {
        setKnowledgeStats(response.data)
      }
    } catch (error) {
      console.error('Failed to load knowledge stats:', error)
    }
  }

  const loadSilStats = async () => {
    try {
      // Call /weaviate/sil/graph/stats endpoint
      const response = await apiClient.get<SILGraphStats>('/weaviate/sil/graph/stats')
      if (!response.error && response.data) {
        setSilStats(response.data)
      }
    } catch (error) {
      console.error('Failed to load SIL stats:', error)
    }
  }

  const loadBoePresets = async () => {
    try {
      // Call /weaviate/boe/presets endpoint
      const response = await apiClient.get<BOEPreset[]>('/weaviate/boe/presets')
      if (!response.error && response.data) {
        setBoePresets(response.data)
      }
    } catch (error) {
      console.error('Failed to load BOE presets:', error)
    }
  }

  const loadPublicKnowledgeStats = async () => {
    try {
      // Call /weaviate/public-knowledge/stats endpoint
      const response = await apiClient.get<PublicKnowledgeStats>('/weaviate/public-knowledge/stats')
      if (!response.error && response.data) {
        setPublicKnowledgeStats(response.data)
      }
    } catch (error) {
      console.error('Failed to load public knowledge stats:', error)
    }
  }

  // ============================================================================
  // Actions - Real API Operations
  // ============================================================================

  const handleRunMaintenance = async () => {
    setShowMaintenanceDialog(false)
    setIsRunningMaintenance(true)
    setMaintenanceResult(null)
    setError(null)

    try {
      // Call /admin/maintenance endpoint
      const response = await apiClient.post<MaintenanceResult>('/admin/maintenance', {
        optimize_database: optimizeDatabase,
        clean_orphaned_files: cleanOrphanedFiles,
        rebuild_search_index: rebuildSearchIndex,
      })

      if (response.error) {
        throw new Error(response.error)
      }

      setMaintenanceResult(response.data || null)
      setSuccessMessage(`Mantenimiento completado en ${response.data?.duration_seconds || 0} segundos`)

      // Reload stats after maintenance
      await loadAllStats()

    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Error al ejecutar mantenimiento'
      setError(errorMessage)
    } finally {
      setIsRunningMaintenance(false)
    }
  }

  const handleDeleteAllDocuments = async () => {
    setShowDeleteDialog(false)
    setIsDeleting(true)
    setError(null)

    try {
      // Call /admin/delete-all-documents endpoint
      const response = await apiClient.post<DeleteResult>('/admin/delete-all-documents', {
        confirm: true,
      })

      if (response.error) {
        throw new Error(response.error)
      }

      setSuccessMessage(`${response.data?.deleted_count || 0} documentos eliminados`)

      // Reload stats after deletion
      await loadAllStats()

    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Error al eliminar documentos'
      setError(errorMessage)
    } finally {
      setIsDeleting(false)
    }
  }

  // ============================================================================
  // SIL Actions
  // ============================================================================

  const handleSilReindex = async () => {
    setShowSilReindexDialog(false)
    setIsReindexingSil(true)
    setSilReindexResult(null)
    setError(null)

    try {
      // Call /weaviate/sil/reindex endpoint
      const response = await apiClient.post<SILReindexResult>('/weaviate/sil/reindex', {
        full_reindex: silFullReindex,
      })

      if (response.error) {
        throw new Error(response.error)
      }

      setSilReindexResult(response.data || null)
      setSuccessMessage(
        `SIL reindex completado: ${response.data?.documents_processed || 0} documentos procesados`
      )

      // Reload SIL stats
      await loadSilStats()

    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Error al reindexar SIL'
      setError(errorMessage)
    } finally {
      setIsReindexingSil(false)
    }
  }

  const handleSilClear = async () => {
    setShowSilClearDialog(false)
    setIsClearingSil(true)
    setError(null)

    try {
      // Call /weaviate/sil/graph/clear endpoint
      const response = await apiClient.delete('/weaviate/sil/graph/clear')

      if (response.error) {
        throw new Error(response.error)
      }

      setSuccessMessage('Grafo SIL limpiado correctamente')

      // Reload SIL stats
      await loadSilStats()

    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Error al limpiar grafo SIL'
      setError(errorMessage)
    } finally {
      setIsClearingSil(false)
    }
  }

  // ============================================================================
  // BOE Legislation Actions
  // ============================================================================

  const handleBoeDownloadPreset = async () => {
    if (!selectedBoePreset) {
      setError('Selecciona una categoría de legislación')
      return
    }

    setShowBoeDownloadDialog(false)
    setIsDownloadingBoe(true)
    setBoeDownloadResults([])
    setError(null)

    try {
      // Call /weaviate/boe/download/preset endpoint
      const response = await apiClient.post<BOEDownloadResult[]>('/weaviate/boe/download/preset', {
        preset: selectedBoePreset,
        index_to_weaviate: true,
      })

      if (response.error) {
        throw new Error(response.error)
      }

      const results = response.data || []
      setBoeDownloadResults(results)

      const successCount = results.filter(r => r.success && r.indexed).length
      const errorCount = results.filter(r => !r.success).length

      setSuccessMessage(
        `Descarga completada: ${successCount} leyes indexadas, ${errorCount} errores`
      )

      // Reload public knowledge stats
      await loadPublicKnowledgeStats()

    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Error al descargar legislación'
      setError(errorMessage)
    } finally {
      setIsDownloadingBoe(false)
    }
  }

  const handleBoeSyncAll = async () => {
    setShowBoeSyncDialog(false)
    setIsSyncingBoe(true)
    setBoeSyncResults([])
    setError(null)

    try {
      // Call /weaviate/boe/sync/all endpoint
      const response = await apiClient.post<any[]>('/weaviate/boe/sync/all', {})

      if (response.error) {
        throw new Error(response.error)
      }

      const results = response.data || []
      setBoeSyncResults(results)

      const changesCount = results.filter(r => r.has_changes).length

      setSuccessMessage(
        `Sincronización completada: ${results.length} leyes verificadas, ${changesCount} con cambios`
      )

      // Reload public knowledge stats
      await loadPublicKnowledgeStats()

    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Error al sincronizar legislación'
      setError(errorMessage)
    } finally {
      setIsSyncingBoe(false)
    }
  }

  const handleExtractKnowledge = async () => {
    setShowKnowledgeExtractDialog(false)
    setIsExtractingKnowledge(true)
    setKnowledgeExtractionResult(null)
    setError(null)

    try {
      // Call /weaviate/public-knowledge/extract endpoint
      const response = await apiClient.post<KnowledgeExtractionResult>(
        '/weaviate/public-knowledge/extract',
        {},
        { params: { limit: 200 } }
      )

      if (response.error) {
        throw new Error(response.error)
      }

      const result = response.data
      setKnowledgeExtractionResult(result || null)

      setSuccessMessage(
        `Extracción completada: ${result?.entities_extracted || 0} entidades extraídas de ${result?.processed || 0} documentos`
      )

      // Reload knowledge stats
      await loadKnowledgeStats()

    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Error al extraer conocimiento'
      setError(errorMessage)
    } finally {
      setIsExtractingKnowledge(false)
    }
  }

  // ============================================================================
  // Render Helpers
  // ============================================================================

  const getStatusBadge = (status: string | boolean | undefined) => {
    if (status === true || status === 'healthy' || status === 'ready' || status === 'ok') {
      return <Badge variant="default" className="bg-green-500">Activo</Badge>
    }
    if (status === false || status === 'error' || status === 'unhealthy') {
      return <Badge variant="destructive">Error</Badge>
    }
    if (status === 'degraded') {
      return <Badge variant="secondary">Degradado</Badge>
    }
    return <Badge variant="outline">Desconocido</Badge>
  }

  const formatNumber = (num: number | undefined): string => {
    if (num === undefined || num === null) return '0'
    return num.toLocaleString('es-ES')
  }

  const formatBytes = (bytes: number | undefined): string => {
    if (!bytes) return '0 B'
    const units = ['B', 'KB', 'MB', 'GB', 'TB']
    let i = 0
    let size = bytes
    while (size >= 1024 && i < units.length - 1) {
      size /= 1024
      i++
    }
    return `${size.toFixed(1)} ${units[i]}`
  }

  // ============================================================================
  // Loading States
  // ============================================================================

  if (!isLoaded) {
    return (
      <div className="flex items-center justify-center h-screen bg-background">
        <IconLoader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  if (!isAuthenticated) {
    return null
  }

  // ============================================================================
  // Main Render
  // ============================================================================

  return (
    <SidebarProvider>
      <AppSidebar variant="inset" />

      <SidebarInset>
        {/* Header */}
        <header className="h-14 border-b flex items-center gap-2 px-4 shrink-0">
          <SidebarTrigger className="-ml-1" />
          <div className="h-4 w-px bg-border" />
          <Link href="/" className="flex items-center gap-2 text-muted-foreground hover:text-foreground">
            <IconChevronLeft className="h-4 w-4" />
            <IconBrain className="h-5 w-5 text-primary" />
            <span className="font-semibold text-foreground">Emma</span>
          </Link>
          <div className="h-4 w-px bg-border" />
          <IconDashboard className="h-4 w-4 text-muted-foreground" />
          <span className="text-muted-foreground">Dashboard Admin</span>
        </header>

        {/* Main Content */}
        <main className="flex-1 overflow-auto p-6">
          <div className="max-w-7xl mx-auto space-y-6">
            {/* Title & Refresh */}
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-2xl font-bold">Panel de Administración</h1>
                <p className="text-muted-foreground">
                  Gestión del sistema, estadísticas y mantenimiento de Emma AI
                </p>
              </div>
              <Button variant="outline" onClick={loadAllStats} disabled={isLoading}>
                <IconRefresh className={`mr-2 h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
                Actualizar
              </Button>
            </div>

            {/* Alerts */}
            {error && (
              <Alert variant="destructive">
                <IconAlertCircle className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            {successMessage && (
              <Alert>
                <IconCircleCheck className="h-4 w-4" />
                <AlertDescription>{successMessage}</AlertDescription>
              </Alert>
            )}

            {maintenanceResult && (
              <Alert>
                <IconCircleCheck className="h-4 w-4" />
                <AlertDescription>
                  {maintenanceResult.message} — Operaciones: {maintenanceResult.operations_performed.join(', ')}
                </AlertDescription>
              </Alert>
            )}

            {/* Stats Overview Cards */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
              {/* Total Documents */}
              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">Documentos</CardTitle>
                  <IconFile className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  {isLoading ? (
                    <div className="h-7 w-20 bg-muted animate-pulse rounded" />
                  ) : (
                    <div className="text-2xl font-bold">{formatNumber(systemStats?.documents.total)}</div>
                  )}
                  <p className="text-xs text-muted-foreground">
                    {formatNumber(systemStats?.documents.indexed)} indexados,{' '}
                    <span className="text-red-500">{formatNumber(systemStats?.documents.error)} errores</span>
                  </p>
                </CardContent>
              </Card>

              {/* Users */}
              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">Usuarios</CardTitle>
                  <IconUsers className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  {isLoading ? (
                    <div className="h-7 w-20 bg-muted animate-pulse rounded" />
                  ) : (
                    <div className="text-2xl font-bold">{formatNumber(systemStats?.users.total)}</div>
                  )}
                  <p className="text-xs text-muted-foreground">
                    {formatNumber(systemStats?.users.active)} activos
                  </p>
                </CardContent>
              </Card>

              {/* Tenants */}
              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">Tenants</CardTitle>
                  <IconBuilding className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  {isLoading ? (
                    <div className="h-7 w-20 bg-muted animate-pulse rounded" />
                  ) : (
                    <div className="text-2xl font-bold">{formatNumber(systemStats?.tenants.total)}</div>
                  )}
                  <p className="text-xs text-muted-foreground">
                    {formatNumber(systemStats?.tenants.active)} activos
                  </p>
                </CardContent>
              </Card>

              {/* Storage */}
              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">Almacenamiento</CardTitle>
                  <IconDatabase className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  {isLoading ? (
                    <div className="h-7 w-20 bg-muted animate-pulse rounded" />
                  ) : (
                    <div className="text-2xl font-bold">{formatBytes(systemStats?.storage.total_bytes)}</div>
                  )}
                  <p className="text-xs text-muted-foreground">
                    Total usado
                  </p>
                </CardContent>
              </Card>
            </div>

            {/* Tabs for different admin sections */}
            <Tabs defaultValue="system" className="space-y-4">
              <TabsList className="grid w-full grid-cols-6">
                <TabsTrigger value="system">
                  <IconServer className="h-4 w-4 mr-2" />
                  Sistema
                </TabsTrigger>
                <TabsTrigger value="documents">
                  <IconFile className="h-4 w-4 mr-2" />
                  Documentos
                </TabsTrigger>
                <TabsTrigger value="knowledge">
                  <IconBinaryTree className="h-4 w-4 mr-2" />
                  Knowledge
                </TabsTrigger>
                <TabsTrigger value="sil">
                  <IconSchool className="h-4 w-4 mr-2" />
                  SIL
                </TabsTrigger>
                <TabsTrigger value="boe">
                  <IconDatabase className="h-4 w-4 mr-2" />
                  BOE
                </TabsTrigger>
                <TabsTrigger value="maintenance">
                  <IconActivity className="h-4 w-4 mr-2" />
                  Mantenimiento
                </TabsTrigger>
              </TabsList>

              {/* System Tab */}
              <TabsContent value="system" className="space-y-4">
                <div className="grid gap-4 md:grid-cols-2">
                  {/* Weaviate Status */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <IconHeart className="h-5 w-5" />
                        Estado del Sistema
                      </CardTitle>
                      <CardDescription>Servicios principales</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="flex items-center justify-between">
                        <span className="text-sm">Weaviate Service</span>
                        {getStatusBadge(weaviateHealth?.weaviate_service?.status)}
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-sm">Emma AI</span>
                        {getStatusBadge(weaviateHealth?.emma_ai?.status)}
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-sm">Estado General</span>
                        {getStatusBadge(weaviateHealth?.overall_status)}
                      </div>
                      {weaviateHealth?.error && (
                        <Alert variant="destructive">
                          <IconAlertCircle className="h-4 w-4" />
                          <AlertDescription>{weaviateHealth.error}</AlertDescription>
                        </Alert>
                      )}
                    </CardContent>
                  </Card>

                  {/* Emma AI Agents */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <IconBrain className="h-5 w-5" />
                        Emma AI
                      </CardTitle>
                      <CardDescription>Agentes disponibles</CardDescription>
                    </CardHeader>
                    <CardContent>
                      {isLoading ? (
                        <div className="space-y-2">
                          {[1, 2, 3].map(i => (
                            <div key={i} className="h-8 bg-muted animate-pulse rounded" />
                          ))}
                        </div>
                      ) : weaviateHealth?.emma_ai?.agents && weaviateHealth.emma_ai.agents.length > 0 ? (
                        <div className="space-y-2">
                          {weaviateHealth.emma_ai.agents.map((agent) => (
                            <div key={agent} className="flex items-center justify-between p-2 bg-muted/50 rounded text-sm">
                              <span className="capitalize">{agent.replace(/_/g, ' ')}</span>
                              <Badge variant="outline">Activo</Badge>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-sm text-muted-foreground">
                          Emma AI con agentes multi-propósito
                        </p>
                      )}
                    </CardContent>
                  </Card>
                </div>
              </TabsContent>

              {/* Documents Tab */}
              <TabsContent value="documents" className="space-y-4">
                <div className="grid gap-4 md:grid-cols-2">
                  {/* Document Stats */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <IconChartPie className="h-5 w-5" />
                        Distribución por Tipo
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      {isLoading ? (
                        <div className="space-y-2">
                          {[1, 2, 3].map(i => (
                            <div key={i} className="h-8 bg-muted animate-pulse rounded" />
                          ))}
                        </div>
                      ) : systemStats?.documents.by_type && Object.keys(systemStats.documents.by_type).length > 0 ? (
                        <div className="space-y-2 max-h-60 overflow-y-auto">
                          {Object.entries(systemStats.documents.by_type).map(([type, count]) => (
                            <div key={type} className="flex items-center justify-between p-2 bg-muted/50 rounded">
                              <span className="text-sm uppercase">{type || 'Sin tipo'}</span>
                              <Badge variant="outline">{formatNumber(count)}</Badge>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-sm text-muted-foreground">No hay documentos indexados</p>
                      )}
                    </CardContent>
                  </Card>

                  {/* Document Health */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <IconChartBar className="h-5 w-5" />
                        Estado de Documentos
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="flex items-center justify-between">
                        <span className="text-sm">Total</span>
                        <span className="font-medium">{formatNumber(systemStats?.documents.total)}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-sm">Indexados</span>
                        <span className="font-medium text-green-600">{formatNumber(systemStats?.documents.indexed)}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-sm">Con errores</span>
                        <span className="font-medium text-red-600">{formatNumber(systemStats?.documents.error)}</span>
                      </div>
                      {systemStats?.documents.total && systemStats.documents.total > 0 && (
                        <div className="pt-2">
                          <div className="text-xs text-muted-foreground mb-1">
                            Tasa de éxito: {((systemStats.documents.indexed / systemStats.documents.total) * 100).toFixed(1)}%
                          </div>
                          <div className="h-2 bg-muted rounded-full overflow-hidden">
                            <div
                              className="h-full bg-green-500"
                              style={{ width: `${(systemStats.documents.indexed / systemStats.documents.total) * 100}%` }}
                            />
                          </div>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                </div>
              </TabsContent>

              {/* Knowledge Tab */}
              <TabsContent value="knowledge" className="space-y-4">
                <div className="grid gap-4 md:grid-cols-2">
                  {/* Knowledge Stats */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <IconBinaryTree className="h-5 w-5" />
                        Knowledge Graph
                      </CardTitle>
                      <CardDescription>Entidades extraídas de documentos</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="flex items-center justify-between">
                        <span className="text-sm">Total entidades</span>
                        <span className="font-medium text-2xl">{formatNumber(knowledgeStats?.total_entities)}</span>
                      </div>
                    </CardContent>
                  </Card>

                  {/* Entities by Type */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <IconChartPie className="h-5 w-5" />
                        Entidades por Tipo
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      {isLoading ? (
                        <div className="space-y-2">
                          {[1, 2, 3].map(i => (
                            <div key={i} className="h-8 bg-muted animate-pulse rounded" />
                          ))}
                        </div>
                      ) : knowledgeStats?.entities_by_type && Object.keys(knowledgeStats.entities_by_type).length > 0 ? (
                        <div className="space-y-2 max-h-60 overflow-y-auto">
                          {Object.entries(knowledgeStats.entities_by_type).map(([type, count]) => (
                            <div key={type} className="flex items-center justify-between p-2 bg-muted/50 rounded">
                              <span className="text-sm capitalize">{type.replace(/_/g, ' ')}</span>
                              <Badge variant="outline">{formatNumber(count)}</Badge>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-sm text-muted-foreground">No hay entidades extraídas</p>
                      )}
                    </CardContent>
                  </Card>
                </div>

                {/* Entities by Domain */}
                {knowledgeStats?.entities_by_domain && Object.keys(knowledgeStats.entities_by_domain).length > 0 && (
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <IconFolder className="h-5 w-5" />
                        Entidades por Dominio
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="grid gap-2 md:grid-cols-3 lg:grid-cols-4">
                        {Object.entries(knowledgeStats.entities_by_domain).map(([domain, count]) => (
                          <div key={domain} className="flex items-center justify-between p-3 bg-muted/50 rounded">
                            <span className="text-sm font-medium capitalize">{domain.replace(/_/g, ' ')}</span>
                            <Badge variant="outline">{formatNumber(count)}</Badge>
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                )}
              </TabsContent>

              {/* SIL (Structural Intelligence Layer) Tab */}
              <TabsContent value="sil" className="space-y-4">
                {/* SIL Info Banner */}
                <Alert>
                  <IconSchool className="h-4 w-4" />
                  <AlertDescription>
                    <strong>Structural Intelligence Layer (SIL)</strong> — Aprende la ESTRUCTURA de documentos, no su contenido.
                    Permite respuestas rápidas (70% menos tokens) para consultas estructurales como conteos, ubicaciones y relaciones.
                  </AlertDescription>
                </Alert>

                {silReindexResult && (
                  <Alert>
                    <IconCircleCheck className="h-4 w-4" />
                    <AlertDescription>
                      SIL Reindex: {silReindexResult.message} — Procesados: {silReindexResult.documents_processed},
                      Omitidos: {silReindexResult.documents_skipped}, Errores: {silReindexResult.errors}
                    </AlertDescription>
                  </Alert>
                )}

                {/* Overview Stats Cards */}
                <div className="grid gap-4 md:grid-cols-4">
                  <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                      <CardTitle className="text-sm font-medium">Documentos</CardTitle>
                      <IconFile className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                      <div className="text-2xl font-bold">{formatNumber(silStats?.total_documents)}</div>
                      <p className="text-xs text-muted-foreground">En el grafo estructural</p>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                      <CardTitle className="text-sm font-medium">Carpetas</CardTitle>
                      <IconFolder className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                      <div className="text-2xl font-bold">{formatNumber(silStats?.total_folders)}</div>
                      <p className="text-xs text-muted-foreground">Jerarquía rastreada</p>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                      <CardTitle className="text-sm font-medium">Relaciones</CardTitle>
                      <IconBinaryTree className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                      <div className="text-2xl font-bold">{formatNumber(silStats?.total_relationships)}</div>
                      <p className="text-xs text-muted-foreground">Conexiones en el grafo</p>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                      <CardTitle className="text-sm font-medium">Estado</CardTitle>
                      <IconHeart className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                      <div className="flex items-center gap-2">
                        {getStatusBadge(silStats?.sil_enabled)}
                      </div>
                      <p className="text-xs text-muted-foreground mt-1">{silStats?.graph_name || 'knowledge_graph'}</p>
                    </CardContent>
                  </Card>
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  {/* Types Breakdown */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <IconChartPie className="h-5 w-5" />
                        Por Tipo Semántico
                      </CardTitle>
                      <CardDescription>Clasificación automática de documentos</CardDescription>
                    </CardHeader>
                    <CardContent>
                      {isLoading ? (
                        <div className="space-y-2">
                          {[1, 2, 3].map(i => (
                            <div key={i} className="h-8 bg-muted animate-pulse rounded" />
                          ))}
                        </div>
                      ) : silStats?.types_breakdown && Object.keys(silStats.types_breakdown).length > 0 ? (
                        <div className="space-y-2 max-h-60 overflow-y-auto">
                          {Object.entries(silStats.types_breakdown)
                            .sort(([, a], [, b]) => b - a)
                            .map(([type, count]) => (
                            <div key={type} className="flex items-center justify-between p-2 bg-muted/50 rounded">
                              <span className="text-sm capitalize">{type.replace(/_/g, ' ')}</span>
                              <Badge variant="outline">{formatNumber(count)}</Badge>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-sm text-muted-foreground">
                          No hay documentos indexados. Ejecuta un reindex para poblar el SIL.
                        </p>
                      )}
                    </CardContent>
                  </Card>

                  {/* Domains Breakdown */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <IconBuilding className="h-5 w-5" />
                        Por Dominio
                      </CardTitle>
                      <CardDescription>Área de negocio de los documentos</CardDescription>
                    </CardHeader>
                    <CardContent>
                      {isLoading ? (
                        <div className="space-y-2">
                          {[1, 2, 3].map(i => (
                            <div key={i} className="h-8 bg-muted animate-pulse rounded" />
                          ))}
                        </div>
                      ) : silStats?.domains_breakdown && Object.keys(silStats.domains_breakdown).length > 0 ? (
                        <div className="space-y-2 max-h-60 overflow-y-auto">
                          {Object.entries(silStats.domains_breakdown)
                            .sort(([, a], [, b]) => b - a)
                            .map(([domain, count]) => (
                            <div key={domain} className="flex items-center justify-between p-2 bg-muted/50 rounded">
                              <span className="text-sm capitalize">{domain.replace(/_/g, ' ')}</span>
                              <Badge variant="outline">{formatNumber(count)}</Badge>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-sm text-muted-foreground">
                          No hay dominios detectados aún.
                        </p>
                      )}
                    </CardContent>
                  </Card>
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  {/* Top Folders */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <IconFolder className="h-5 w-5" />
                        Top Carpetas
                      </CardTitle>
                      <CardDescription>Carpetas con más documentos</CardDescription>
                    </CardHeader>
                    <CardContent>
                      {isLoading ? (
                        <div className="space-y-2">
                          {[1, 2, 3].map(i => (
                            <div key={i} className="h-8 bg-muted animate-pulse rounded" />
                          ))}
                        </div>
                      ) : silStats?.top_folders && silStats.top_folders.length > 0 ? (
                        <div className="space-y-2 max-h-60 overflow-y-auto">
                          {silStats.top_folders.map((folder, index) => (
                            <div key={index} className="flex items-center justify-between p-2 bg-muted/50 rounded">
                              <span className="text-sm truncate max-w-[200px]" title={folder.path}>
                                {folder.path.split('/').pop() || folder.path}
                              </span>
                              <Badge variant="outline">{formatNumber(folder.count)}</Badge>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-sm text-muted-foreground">
                          No hay carpetas indexadas aún.
                        </p>
                      )}
                    </CardContent>
                  </Card>

                  {/* Recent Documents */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <IconActivity className="h-5 w-5" />
                        Documentos Recientes
                      </CardTitle>
                      <CardDescription>Últimos documentos indexados</CardDescription>
                    </CardHeader>
                    <CardContent>
                      {isLoading ? (
                        <div className="space-y-2">
                          {[1, 2, 3].map(i => (
                            <div key={i} className="h-10 bg-muted animate-pulse rounded" />
                          ))}
                        </div>
                      ) : silStats?.recent_documents && silStats.recent_documents.length > 0 ? (
                        <div className="space-y-2 max-h-60 overflow-y-auto">
                          {silStats.recent_documents.map((doc) => (
                            <div key={doc.id} className="p-2 bg-muted/50 rounded">
                              <div className="flex items-center justify-between">
                                <span className="text-sm font-medium truncate max-w-[180px]" title={doc.title}>
                                  {doc.title}
                                </span>
                                <Badge variant="secondary" className="text-xs capitalize">
                                  {doc.type.replace(/_/g, ' ')}
                                </Badge>
                              </div>
                              <p className="text-xs text-muted-foreground mt-1">
                                {doc.created_at ? new Date(doc.created_at).toLocaleDateString('es-ES') : 'Fecha desconocida'}
                              </p>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-sm text-muted-foreground">
                          No hay documentos recientes.
                        </p>
                      )}
                    </CardContent>
                  </Card>
                </div>

                {/* Relationships Breakdown - Full Width */}
                {silStats?.relationships_breakdown && Object.keys(silStats.relationships_breakdown).length > 0 && (
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <IconBinaryTree className="h-5 w-5" />
                        Relaciones en el Grafo
                      </CardTitle>
                      <CardDescription>Tipos de conexiones entre nodos</CardDescription>
                    </CardHeader>
                    <CardContent>
                      <div className="grid gap-2 md:grid-cols-4">
                        {Object.entries(silStats.relationships_breakdown).map(([relType, count]) => (
                          <div key={relType} className="flex items-center justify-between p-3 bg-muted/50 rounded">
                            <span className="text-sm font-medium capitalize">{relType.replace(/_/g, ' ')}</span>
                            <Badge variant="outline">{formatNumber(count)}</Badge>
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                )}

                {/* SIL Actions */}
                <div className="grid gap-4 md:grid-cols-2">
                  {/* Reindex SIL */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <IconReload className="h-5 w-5" />
                        Reindexar SIL
                      </CardTitle>
                      <CardDescription>
                        Extrae metadatos estructurales de documentos e indexa al grafo
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="flex items-center justify-between">
                        <div className="space-y-0.5">
                          <Label htmlFor="sil-full-reindex">Reindex completo</Label>
                          <p className="text-xs text-muted-foreground">
                            Si está desactivado, solo procesa documentos nuevos
                          </p>
                        </div>
                        <Switch
                          id="sil-full-reindex"
                          checked={silFullReindex}
                          onCheckedChange={setSilFullReindex}
                        />
                      </div>
                      <div className="rounded-lg bg-muted p-4 text-sm">
                        <p className="text-muted-foreground">
                          El reindex extrae: tipo semántico, dominio, ruta de carpeta,
                          propiedades clave y descripción estructural de cada documento.
                        </p>
                      </div>
                    </CardContent>
                    <CardFooter>
                      <Button
                        onClick={() => setShowSilReindexDialog(true)}
                        disabled={isReindexingSil}
                        className="w-full"
                      >
                        {isReindexingSil ? (
                          <>
                            <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                            Reindexando...
                          </>
                        ) : (
                          <>
                            <IconReload className="mr-2 h-4 w-4" />
                            Reindexar SIL
                          </>
                        )}
                      </Button>
                    </CardFooter>
                  </Card>

                  {/* Clear SIL Graph */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2 text-destructive">
                        <IconTrash className="h-5 w-5" />
                        Limpiar Grafo SIL
                      </CardTitle>
                      <CardDescription>
                        Elimina todos los nodos y relaciones del grafo estructural
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <Alert variant="destructive">
                        <IconAlertCircle className="h-4 w-4" />
                        <AlertDescription>
                          Esta acción eliminará permanentemente todos los metadatos estructurales.
                          Los documentos originales NO se verán afectados.
                        </AlertDescription>
                      </Alert>
                      <div className="rounded-lg bg-muted p-4">
                        <h4 className="font-medium mb-2">Se eliminarán:</h4>
                        <ul className="text-sm text-muted-foreground space-y-1">
                          <li>• {formatNumber(silStats?.total_documents)} nodos de documentos</li>
                          <li>• {formatNumber(silStats?.total_folders)} nodos de carpetas</li>
                          <li>• Todas las relaciones estructurales</li>
                          <li>• Embeddings estructurales en Weaviate</li>
                        </ul>
                      </div>
                    </CardContent>
                    <CardFooter>
                      <Button
                        variant="destructive"
                        onClick={() => setShowSilClearDialog(true)}
                        disabled={isClearingSil}
                        className="w-full"
                      >
                        {isClearingSil ? (
                          <>
                            <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                            Limpiando...
                          </>
                        ) : (
                          <>
                            <IconTrash className="mr-2 h-4 w-4" />
                            Limpiar Grafo SIL
                          </>
                        )}
                      </Button>
                    </CardFooter>
                  </Card>
                </div>
              </TabsContent>

              {/* BOE (Public Knowledge Base) Tab */}
              <TabsContent value="boe" className="space-y-4">
                {/* BOE Info Banner */}
                <Alert>
                  <IconDatabase className="h-4 w-4" />
                  <AlertDescription>
                    <strong>Base de Conocimiento Público (BOE)</strong> — Legislación española consolidada
                    descargada del Boletín Oficial del Estado. Emma AI usa este conocimiento para
                    consultas legales generales.
                  </AlertDescription>
                </Alert>

                {boeDownloadResults.length > 0 && (
                  <Alert>
                    <IconCircleCheck className="h-4 w-4" />
                    <AlertDescription>
                      Última descarga: {boeDownloadResults.filter(r => r.success).length} leyes indexadas,{' '}
                      {boeDownloadResults.filter(r => !r.success).length} errores
                    </AlertDescription>
                  </Alert>
                )}

                <div className="grid gap-4 md:grid-cols-2">
                  {/* Public Knowledge Stats */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <IconChartBar className="h-5 w-5" />
                        Estadísticas del Conocimiento Público
                      </CardTitle>
                      <CardDescription>
                        Documentos indexados en la base de conocimiento
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="flex items-center justify-between">
                        <span className="text-sm">Total documentos</span>
                        <span className="text-2xl font-bold">
                          {formatNumber(publicKnowledgeStats?.total_documents)}
                        </span>
                      </div>
                      {publicKnowledgeStats?.documents_by_category &&
                        Object.keys(publicKnowledgeStats.documents_by_category).length > 0 && (
                        <div className="space-y-2">
                          <span className="text-sm text-muted-foreground">Por categoría:</span>
                          {Object.entries(publicKnowledgeStats.documents_by_category).map(([cat, count]) => (
                            <div key={cat} className="flex items-center justify-between p-2 bg-muted/50 rounded">
                              <span className="text-sm capitalize">{cat.replace(/_/g, ' ')}</span>
                              <Badge variant="outline">{formatNumber(count)}</Badge>
                            </div>
                          ))}
                        </div>
                      )}
                    </CardContent>
                  </Card>

                  {/* BOE Presets */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <IconFolder className="h-5 w-5" />
                        Categorías Disponibles (BOE)
                      </CardTitle>
                      <CardDescription>
                        Presets de legislación listos para indexar
                      </CardDescription>
                    </CardHeader>
                    <CardContent>
                      {isLoading ? (
                        <div className="space-y-2">
                          {[1, 2, 3].map(i => (
                            <div key={i} className="h-10 bg-muted animate-pulse rounded" />
                          ))}
                        </div>
                      ) : boePresets.length > 0 ? (
                        <div className="space-y-2 max-h-60 overflow-y-auto">
                          {boePresets.map((preset) => (
                            <div
                              key={preset.name}
                              className={`flex items-center justify-between p-3 rounded cursor-pointer transition-colors ${
                                selectedBoePreset === preset.name
                                  ? 'bg-primary/10 border border-primary'
                                  : 'bg-muted/50 hover:bg-muted'
                              }`}
                              onClick={() => setSelectedBoePreset(preset.name)}
                            >
                              <div>
                                <span className="text-sm font-medium capitalize">
                                  {preset.name.replace(/_/g, ' ')}
                                </span>
                                <p className="text-xs text-muted-foreground">{preset.description}</p>
                              </div>
                              <Badge variant="outline">{preset.legislation_count} leyes</Badge>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-sm text-muted-foreground">
                          No se pudieron cargar los presets de BOE
                        </p>
                      )}
                    </CardContent>
                  </Card>
                </div>

                {/* BOE Actions */}
                <div className="grid gap-4 md:grid-cols-2">
                  {/* Download Preset */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <IconReload className="h-5 w-5" />
                        Descargar e Indexar Legislación
                      </CardTitle>
                      <CardDescription>
                        Descarga leyes del BOE y las indexa en la base de conocimiento
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="rounded-lg bg-muted p-4 text-sm">
                        {selectedBoePreset ? (
                          <div>
                            <p className="font-medium">Categoría seleccionada:</p>
                            <p className="text-primary capitalize mt-1">
                              {selectedBoePreset.replace(/_/g, ' ')}
                            </p>
                            <p className="text-muted-foreground mt-2">
                              {boePresets.find(p => p.name === selectedBoePreset)?.legislation_count || 0} leyes
                              serán descargadas e indexadas.
                            </p>
                          </div>
                        ) : (
                          <p className="text-muted-foreground">
                            Selecciona una categoría de la lista para descargar e indexar su legislación.
                          </p>
                        )}
                      </div>
                    </CardContent>
                    <CardFooter>
                      <Button
                        onClick={() => setShowBoeDownloadDialog(true)}
                        disabled={isDownloadingBoe || !selectedBoePreset}
                        className="w-full"
                      >
                        {isDownloadingBoe ? (
                          <>
                            <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                            Descargando...
                          </>
                        ) : (
                          <>
                            <IconReload className="mr-2 h-4 w-4" />
                            Descargar e Indexar
                          </>
                        )}
                      </Button>
                    </CardFooter>
                  </Card>

                  {/* Sync All Legislation */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <IconRefresh className="h-5 w-5" />
                        Sincronizar Legislación
                      </CardTitle>
                      <CardDescription>
                        Detecta cambios en las leyes ya indexadas
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="rounded-lg bg-muted p-4 text-sm">
                        <p className="text-muted-foreground">
                          Compara las leyes indexadas con las versiones actuales del BOE.
                          Detecta modificaciones a nivel de artículo y actualiza el contenido.
                        </p>
                        {boeSyncResults.length > 0 && (
                          <div className="mt-3 pt-3 border-t">
                            <p className="font-medium">Última sincronización:</p>
                            <p>
                              {boeSyncResults.filter(r => r.has_changes).length} leyes con cambios de{' '}
                              {boeSyncResults.length} verificadas
                            </p>
                          </div>
                        )}
                      </div>
                    </CardContent>
                    <CardFooter>
                      <Button
                        variant="outline"
                        onClick={() => setShowBoeSyncDialog(true)}
                        disabled={isSyncingBoe}
                        className="w-full"
                      >
                        {isSyncingBoe ? (
                          <>
                            <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                            Sincronizando...
                          </>
                        ) : (
                          <>
                            <IconRefresh className="mr-2 h-4 w-4" />
                            Sincronizar Todo
                          </>
                        )}
                      </Button>
                    </CardFooter>
                  </Card>
                </div>

                {/* Knowledge Extraction Card */}
                <Card className="border-2 border-primary/20">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <IconBinaryTree className="h-5 w-5 text-primary" />
                      Extraer Entidades al Knowledge Graph
                    </CardTitle>
                    <CardDescription>
                      Procesa los documentos públicos y extrae entidades para consultas semánticas
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <Alert>
                      <IconSchool className="h-4 w-4" />
                      <AlertDescription>
                        <strong>¿Por qué hacer esto?</strong> — Los documentos del BOE están indexados,
                        pero para que Emma pueda responder preguntas como "¿Cuántos artículos hablan de vacaciones?"
                        necesita extraer entidades (artículos, términos, referencias) al Knowledge Graph.
                      </AlertDescription>
                    </Alert>
                    {knowledgeExtractionResult && (
                      <div className="rounded-lg bg-muted p-4">
                        <p className="font-medium">Última extracción:</p>
                        <ul className="text-sm text-muted-foreground mt-2 space-y-1">
                          <li>• {knowledgeExtractionResult.processed} documentos procesados</li>
                          <li>• {knowledgeExtractionResult.entities_extracted} entidades extraídas</li>
                          <li>• {knowledgeExtractionResult.errors} errores</li>
                        </ul>
                      </div>
                    )}
                  </CardContent>
                  <CardFooter>
                    <Button
                      onClick={() => setShowKnowledgeExtractDialog(true)}
                      disabled={isExtractingKnowledge}
                      className="w-full"
                    >
                      {isExtractingKnowledge ? (
                        <>
                          <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                          Extrayendo entidades...
                        </>
                      ) : (
                        <>
                          <IconBinaryTree className="mr-2 h-4 w-4" />
                          Extraer Entidades al Knowledge Graph
                        </>
                      )}
                    </Button>
                  </CardFooter>
                </Card>
              </TabsContent>

              {/* Maintenance Tab */}
              <TabsContent value="maintenance" className="space-y-4">
                <div className="grid gap-4 md:grid-cols-2">
                  {/* Maintenance Card */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <IconReload className="h-5 w-5" />
                        Mantenimiento
                      </CardTitle>
                      <CardDescription>
                        Ejecutar tareas de mantenimiento del sistema
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="flex items-center justify-between">
                        <div className="space-y-0.5">
                          <Label htmlFor="optimize-db">Optimizar base de datos</Label>
                          <p className="text-xs text-muted-foreground">
                            Ejecuta ANALYZE en las tablas principales
                          </p>
                        </div>
                        <Switch
                          id="optimize-db"
                          checked={optimizeDatabase}
                          onCheckedChange={setOptimizeDatabase}
                        />
                      </div>
                      <div className="flex items-center justify-between">
                        <div className="space-y-0.5">
                          <Label htmlFor="clean-orphans">Limpiar archivos huérfanos</Label>
                          <p className="text-xs text-muted-foreground">
                            Elimina archivos sin referencia en BD
                          </p>
                        </div>
                        <Switch
                          id="clean-orphans"
                          checked={cleanOrphanedFiles}
                          onCheckedChange={setCleanOrphanedFiles}
                        />
                      </div>
                      <div className="flex items-center justify-between">
                        <div className="space-y-0.5">
                          <Label htmlFor="rebuild-index">Reconstruir índice de búsqueda</Label>
                          <p className="text-xs text-muted-foreground">
                            Reindexa documentos faltantes (puede tardar)
                          </p>
                        </div>
                        <Switch
                          id="rebuild-index"
                          checked={rebuildSearchIndex}
                          onCheckedChange={setRebuildSearchIndex}
                        />
                      </div>
                    </CardContent>
                    <CardFooter>
                      <Button
                        onClick={() => setShowMaintenanceDialog(true)}
                        disabled={isRunningMaintenance}
                        className="w-full"
                      >
                        {isRunningMaintenance ? (
                          <>
                            <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                            Ejecutando...
                          </>
                        ) : (
                          <>
                            <IconPlayerPlay className="mr-2 h-4 w-4" />
                            Ejecutar Mantenimiento
                          </>
                        )}
                      </Button>
                    </CardFooter>
                  </Card>

                  {/* Delete All Documents Card */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2 text-destructive">
                        <IconTrash className="h-5 w-5" />
                        Eliminar Documentos
                      </CardTitle>
                      <CardDescription>
                        Eliminar TODOS los documentos del tenant actual
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <Alert variant="destructive">
                        <IconAlertCircle className="h-4 w-4" />
                        <AlertDescription>
                          <strong>¡Peligro!</strong> Esta acción eliminará permanentemente todos los documentos,
                          sus archivos en el almacenamiento y sus datos vectoriales.
                        </AlertDescription>
                      </Alert>
                      <div className="rounded-lg bg-muted p-4">
                        <h4 className="font-medium mb-2">Se eliminarán:</h4>
                        <ul className="text-sm text-muted-foreground space-y-1">
                          <li>• {formatNumber(systemStats?.documents.total)} documentos</li>
                          <li>• {formatBytes(systemStats?.storage.total_bytes)} de archivos</li>
                          <li>• Todos los datos vectoriales asociados</li>
                          <li>• Métricas y vistas de documentos</li>
                        </ul>
                      </div>
                    </CardContent>
                    <CardFooter>
                      <Button
                        variant="destructive"
                        onClick={() => setShowDeleteDialog(true)}
                        disabled={isDeleting}
                        className="w-full"
                      >
                        {isDeleting ? (
                          <>
                            <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                            Eliminando...
                          </>
                        ) : (
                          <>
                            <IconTrash className="mr-2 h-4 w-4" />
                            Eliminar Todos los Documentos
                          </>
                        )}
                      </Button>
                    </CardFooter>
                  </Card>
                </div>

                {/* Additional Links */}
                <Card>
                  <CardHeader>
                    <CardTitle>Operaciones Adicionales</CardTitle>
                    <CardDescription>Otras tareas de gestión disponibles</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-4">
                      <div className="flex items-center justify-between p-4 border rounded-lg">
                        <div className="flex items-center gap-4">
                          <IconReload className="h-8 w-8 text-blue-500" />
                          <div>
                            <h4 className="font-medium">Conectores</h4>
                            <p className="text-sm text-muted-foreground">
                              Configura fuentes de datos externas (Alfresco, SharePoint, etc.)
                            </p>
                          </div>
                        </div>
                        <Button variant="outline" asChild>
                          <Link href="/connectors">Configurar</Link>
                        </Button>
                      </div>

                      <div className="flex items-center justify-between p-4 border rounded-lg">
                        <div className="flex items-center gap-4">
                          <IconDatabase className="h-8 w-8 text-green-500" />
                          <div>
                            <h4 className="font-medium">Base de Conocimiento Público</h4>
                            <p className="text-sm text-muted-foreground">
                              Gestiona legislación y normativa indexada
                            </p>
                          </div>
                        </div>
                        <Button variant="outline" asChild>
                          <Link href="/admin/public-knowledge">Ver</Link>
                        </Button>
                      </div>

                      <div className="flex items-center justify-between p-4 border rounded-lg">
                        <div className="flex items-center gap-4">
                          <IconSchool className="h-8 w-8 text-purple-500" />
                          <div>
                            <h4 className="font-medium">Data Learning</h4>
                            <p className="text-sm text-muted-foreground">
                              Configuración de aprendizaje de estructura
                            </p>
                          </div>
                        </div>
                        <Button variant="outline" asChild>
                          <Link href="/data-learning">Configurar</Link>
                        </Button>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </TabsContent>
            </Tabs>
          </div>
        </main>
      </SidebarInset>

      {/* Maintenance Confirmation Dialog */}
      <AlertDialog open={showMaintenanceDialog} onOpenChange={setShowMaintenanceDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Ejecutar mantenimiento?</AlertDialogTitle>
            <AlertDialogDescription>
              Se ejecutarán las siguientes operaciones:
              <ul className="mt-2 list-disc list-inside">
                {optimizeDatabase && <li>Optimizar base de datos</li>}
                {cleanOrphanedFiles && <li>Limpiar archivos huérfanos</li>}
                {rebuildSearchIndex && <li>Reconstruir índice de búsqueda</li>}
              </ul>
              {rebuildSearchIndex && (
                <p className="mt-2 text-amber-600">
                  ⚠️ La reconstrucción del índice puede tardar varios minutos.
                </p>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={handleRunMaintenance}>
              <IconPlayerPlay className="mr-2 h-4 w-4" />
              Ejecutar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Delete All Documents Confirmation Dialog */}
      <AlertDialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="text-destructive">¿Eliminar TODOS los documentos?</AlertDialogTitle>
            <AlertDialogDescription>
              Esta acción no se puede deshacer. Se eliminarán permanentemente:
              <ul className="mt-2 list-disc list-inside">
                <li>{formatNumber(systemStats?.documents.total)} documentos</li>
                <li>{formatBytes(systemStats?.storage.total_bytes)} de archivos</li>
                <li>Todos los datos vectoriales</li>
              </ul>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteAllDocuments}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              <IconTrash className="mr-2 h-4 w-4" />
              Eliminar Todo
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* SIL Reindex Confirmation Dialog */}
      <AlertDialog open={showSilReindexDialog} onOpenChange={setShowSilReindexDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Reindexar SIL?</AlertDialogTitle>
            <AlertDialogDescription>
              {silFullReindex ? (
                <>
                  Se ejecutará un <strong>reindex completo</strong>:
                  <ul className="mt-2 list-disc list-inside">
                    <li>Limpiará el grafo existente</li>
                    <li>Procesará TODOS los documentos</li>
                    <li>Puede tardar varios minutos</li>
                  </ul>
                </>
              ) : (
                <>
                  Se ejecutará un <strong>reindex incremental</strong>:
                  <ul className="mt-2 list-disc list-inside">
                    <li>Solo procesará documentos nuevos</li>
                    <li>Más rápido que el reindex completo</li>
                    <li>No eliminará datos existentes</li>
                  </ul>
                </>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={handleSilReindex}>
              <IconReload className="mr-2 h-4 w-4" />
              Reindexar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* SIL Clear Graph Confirmation Dialog */}
      <AlertDialog open={showSilClearDialog} onOpenChange={setShowSilClearDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="text-destructive">¿Limpiar grafo SIL?</AlertDialogTitle>
            <AlertDialogDescription>
              Esta acción eliminará permanentemente:
              <ul className="mt-2 list-disc list-inside">
                <li>{formatNumber(silStats?.total_documents)} nodos de documentos</li>
                <li>{formatNumber(silStats?.total_folders)} nodos de carpetas</li>
                <li>Todas las relaciones estructurales</li>
              </ul>
              <p className="mt-2 text-sm">
                Los documentos originales NO se eliminarán. Deberás ejecutar un reindex
                completo para volver a poblar el grafo.
              </p>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleSilClear}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              <IconTrash className="mr-2 h-4 w-4" />
              Limpiar Grafo
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* BOE Download Confirmation Dialog */}
      <AlertDialog open={showBoeDownloadDialog} onOpenChange={setShowBoeDownloadDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Descargar legislación del BOE?</AlertDialogTitle>
            <AlertDialogDescription>
              Se descargarán e indexarán las siguientes leyes:
              <div className="mt-2 p-3 bg-muted rounded-lg">
                <p className="font-medium capitalize">{selectedBoePreset?.replace(/_/g, ' ')}</p>
                <p className="text-sm mt-1">
                  {boePresets.find(p => p.name === selectedBoePreset)?.legislation_count || 0} documentos
                </p>
              </div>
              <p className="mt-2 text-sm text-amber-600">
                ⚠️ Este proceso puede tardar varios minutos dependiendo del número de leyes.
              </p>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={handleBoeDownloadPreset}>
              <IconReload className="mr-2 h-4 w-4" />
              Descargar e Indexar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* BOE Sync Confirmation Dialog */}
      <AlertDialog open={showBoeSyncDialog} onOpenChange={setShowBoeSyncDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Sincronizar toda la legislación?</AlertDialogTitle>
            <AlertDialogDescription>
              Se verificarán todas las leyes indexadas contra las versiones actuales del BOE.
              <ul className="mt-2 list-disc list-inside">
                <li>Detecta modificaciones a nivel de artículo</li>
                <li>Actualiza el contenido si hay cambios</li>
                <li>Genera diffs para visualización</li>
              </ul>
              <p className="mt-2 text-sm text-amber-600">
                ⚠️ Este proceso puede tardar varios minutos si hay muchas leyes indexadas.
              </p>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={handleBoeSyncAll}>
              <IconRefresh className="mr-2 h-4 w-4" />
              Sincronizar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Knowledge Extraction Confirmation Dialog */}
      <AlertDialog open={showKnowledgeExtractDialog} onOpenChange={setShowKnowledgeExtractDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Extraer entidades al Knowledge Graph?</AlertDialogTitle>
            <AlertDialogDescription>
              Se procesarán los documentos públicos (legislación) para extraer entidades:
              <ul className="mt-2 list-disc list-inside">
                <li>Artículos de leyes (Art. 1, Art. 2...)</li>
                <li>Referencias legales (BOE-A-2015-11430...)</li>
                <li>Organizaciones (Ministerios, Agencias...)</li>
                <li>Fechas y términos clave</li>
              </ul>
              <p className="mt-2 text-sm">
                Las entidades extraídas permitirán a Emma responder preguntas como
                "¿Cuántos artículos mencionan las vacaciones?" o "¿Qué leyes regulan el teletrabajo?"
              </p>
              <p className="mt-2 text-sm text-amber-600">
                ⚠️ Este proceso puede tardar varios minutos.
              </p>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={handleExtractKnowledge}>
              <IconBinaryTree className="mr-2 h-4 w-4" />
              Extraer Entidades
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </SidebarProvider>
  )
}
