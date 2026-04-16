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
  IconCpu,
  IconRobot,
  IconCheck,
  IconHeartbeat,
  IconMail,
  IconBrandSlack,
  IconClock,
  IconBell,
  IconSparkles,
  IconExternalLink,
  IconGavel,
} from "@tabler/icons-react"
import {
  SidebarProvider,
  SidebarInset,
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
} from "@/components/ui"
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from "@/components/ui/card"
import { Switch } from "@/components/ui/switch"
import { useApiClient } from "@/lib/api-client"
import { useAuth } from "@/contexts/auth-context"
import { AppSidebar } from "@/components/layout/app-sidebar"
import { PageHeader } from '@/components/layout/page-header'

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
  tenant_entities?: number   // Entities specific to this tenant
  public_entities?: number   // Shared entities from public knowledge
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

interface TrainingSectorStatus {
  sector: string
  has_trained_model: boolean
  model_path: string | null
  qa_concepts_count: number
  qa_questions_count: number
}

interface TrainingStatus {
  active_sector: string
  sectors: TrainingSectorStatus[]
  training_in_progress: string | null
  training_progress: {
    stage: string
    message: string
    total_examples?: number
    epochs?: number
    elapsed_seconds?: number
  } | null
}

interface TrainingProgress {
  in_progress: string | null
  progress: {
    stage: string
    message: string
    total_examples?: number
    epoch?: number
    total_epochs?: number
    elapsed_seconds?: number
    model_path?: string
  }
  last_error: string | null
}

interface HeartbeatConfig {
  enabled: boolean
  run_interval_hours: number
  priority_threshold: number
  max_insights_per_day: number
  max_insights_per_hour: number
  min_interval_minutes: number
  quiet_hours_start: string
  quiet_hours_end: string
  channel_priority: string[]
  email_recipients: string[]
  batch_low_priority: boolean
  digest_hour: number
}

interface HeartbeatStatus {
  enabled: boolean
  last_run_at: string | null
  next_run_at: string | null
  insights_pending: number
  insights_delivered_today: number
  config: HeartbeatConfig
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
const [boePresets, setBoePresets] = useState<BOEPreset[]>([])
  const [publicKnowledgeStats, setPublicKnowledgeStats] = useState<PublicKnowledgeStats | null>(null)

  // Loading states
  const [isLoading, setIsLoading] = useState(true)
  const [isRunningMaintenance, setIsRunningMaintenance] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
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
  const [showBoeDownloadDialog, setShowBoeDownloadDialog] = useState(false)
  const [showBoeSyncDialog, setShowBoeSyncDialog] = useState(false)
  const [showKnowledgeExtractDialog, setShowKnowledgeExtractDialog] = useState(false)

  // BOE options
  const [selectedBoePreset, setSelectedBoePreset] = useState<string>("")
  const [boeDownloadResults, setBoeDownloadResults] = useState<BOEDownloadResult[]>([])
  const [boeSyncResults, setBoeSyncResults] = useState<any[]>([])

  // Knowledge extraction
  const [knowledgeExtractionResult, setKnowledgeExtractionResult] = useState<KnowledgeExtractionResult | null>(null)

  // Training
  const [trainingStatus, setTrainingStatus] = useState<TrainingStatus | null>(null)
  const [isLoadingTraining, setIsLoadingTraining] = useState(false)
  const [isStartingTraining, setIsStartingTraining] = useState(false)
  const [trainingProgress, setTrainingProgress] = useState<TrainingProgress | null>(null)
  const [selectedTrainingSector, setSelectedTrainingSector] = useState<string>("")
  const [trainingHfDataset, setTrainingHfDataset] = useState<string>("")
  const [trainingEpochs, setTrainingEpochs] = useState<number>(3)
  const [showTrainingDialog, setShowTrainingDialog] = useState(false)

  // Heartbeat
  const [heartbeatStatus, setHeartbeatStatus] = useState<HeartbeatStatus | null>(null)
  const [heartbeatConfig, setHeartbeatConfig] = useState<HeartbeatConfig | null>(null)
  const [isLoadingHeartbeat, setIsLoadingHeartbeat] = useState(false)
  const [isSavingHeartbeat, setIsSavingHeartbeat] = useState(false)
  const [isRunningHeartbeat, setIsRunningHeartbeat] = useState(false)
  const [newEmailRecipient, setNewEmailRecipient] = useState("")

  // CENDOJ
  const [cendojEnabled, setCendojEnabled] = useState<boolean | null>(null)
  const [cendojSector, setCendojSector] = useState<string>("")
  const [isSavingCendoj, setIsSavingCendoj] = useState(false)

  // Results
  const [maintenanceResult, setMaintenanceResult] = useState<MaintenanceResult | null>(null)

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
        loadBoePresets(),
        loadPublicKnowledgeStats(),
        loadTrainingStatus(),
        loadHeartbeatStatus(),
        loadCendojStatus(),
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

  const loadTrainingStatus = async () => {
    try {
      const response = await apiClient.get<TrainingStatus>('/emma/training/status')
      if (!response.error && response.data) {
        setTrainingStatus(response.data)
        if (!selectedTrainingSector && response.data.active_sector) {
          setSelectedTrainingSector(response.data.active_sector)
        }
      }
    } catch (error) {
      console.error('Failed to load training status:', error)
    }
  }

  const loadTrainingProgress = async () => {
    try {
      const response = await apiClient.get<TrainingProgress>('/emma/training/progress')
      if (!response.error && response.data) {
        setTrainingProgress(response.data)
      }
    } catch (error) {
      console.error('Failed to load training progress:', error)
    }
  }

  const loadHeartbeatStatus = async () => {
    setIsLoadingHeartbeat(true)
    try {
      const response = await apiClient.get<HeartbeatStatus>('/emma/heartbeat/status')
      if (!response.error && response.data) {
        setHeartbeatStatus(response.data)
        setHeartbeatConfig(response.data.config)
      }
    } catch (error) {
      console.error('Failed to load heartbeat status:', error)
    } finally {
      setIsLoadingHeartbeat(false)
    }
  }

  const handleUpdateHeartbeatConfig = async (updates: Partial<HeartbeatConfig>) => {
    setIsSavingHeartbeat(true)
    setError(null)
    try {
      const response = await apiClient.patch<HeartbeatConfig>('/emma/heartbeat/config', updates)
      if (response.error) {
        throw new Error(response.error)
      }
      if (response.data) {
        setHeartbeatConfig(response.data)
        setSuccessMessage('Configuración de Heartbeat actualizada')
      }
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Error al actualizar configuración'
      setError(errorMessage)
    } finally {
      setIsSavingHeartbeat(false)
    }
  }

  const handleRunHeartbeat = async () => {
    setIsRunningHeartbeat(true)
    setError(null)
    try {
      const response = await apiClient.post<any>('/emma/heartbeat/run', null, { params: { force: 'true' } })
      if (response.error) {
        throw new Error(response.error)
      }
      setSuccessMessage(`Heartbeat ejecutado: ${response.data?.insights_delivered || 0} insights generados`)
      await loadHeartbeatStatus()
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Error al ejecutar heartbeat'
      setError(errorMessage)
    } finally {
      setIsRunningHeartbeat(false)
    }
  }

  const handleAddEmailRecipient = () => {
    if (!newEmailRecipient || !heartbeatConfig) return
    const email = newEmailRecipient.trim().toLowerCase()
    if (!email.includes('@')) {
      setError('Email inválido')
      return
    }
    if (heartbeatConfig.email_recipients.includes(email)) {
      setError('Email ya está en la lista')
      return
    }
    const updated = [...heartbeatConfig.email_recipients, email]
    handleUpdateHeartbeatConfig({ email_recipients: updated })
    setNewEmailRecipient("")
  }

  const handleRemoveEmailRecipient = (email: string) => {
    if (!heartbeatConfig) return
    const updated = heartbeatConfig.email_recipients.filter(e => e !== email)
    handleUpdateHeartbeatConfig({ email_recipients: updated })
  }

  // CENDOJ
  const loadCendojStatus = async () => {
    try {
      const response = await apiClient.get<{ enabled: boolean; sector: string; docker_image: string }>('/emma/cendoj/status')
      if (!response.error && response.data) {
        setCendojEnabled(response.data.enabled)
        setCendojSector(response.data.sector)
      }
    } catch (error) {
      console.error('Failed to load CENDOJ status:', error)
    }
  }

  const handleToggleCendoj = async (checked: boolean) => {
    setIsSavingCendoj(true)
    setError(null)
    try {
      const response = await apiClient.patch<{ enabled: boolean; sector: string }>('/emma/cendoj/status', { enabled: checked })
      if (response.error) {
        throw new Error(response.error)
      }
      if (response.data) {
        setCendojEnabled(response.data.enabled)
        setSuccessMessage(checked ? 'CENDOJ habilitado' : 'CENDOJ deshabilitado')
      }
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Error al actualizar CENDOJ'
      setError(errorMessage)
    } finally {
      setIsSavingCendoj(false)
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
  // Training Actions
  // ============================================================================

  const handleStartTraining = async () => {
    setShowTrainingDialog(false)
    setIsStartingTraining(true)
    setError(null)

    try {
      const response = await apiClient.post<{ status: string; message: string }>('/emma/training/start', {
        sector: selectedTrainingSector,
        hf_dataset: trainingHfDataset || undefined,
        epochs: trainingEpochs,
        batch_size: 16,
      })

      if (response.error) {
        throw new Error(response.error)
      }

      setSuccessMessage(response.data?.message || 'Entrenamiento iniciado')

      // Poll progress every 3 seconds
      const pollInterval = setInterval(async () => {
        await loadTrainingProgress()
        await loadTrainingStatus()
        const progressRes = await apiClient.get<TrainingProgress>('/emma/training/progress')
        if (progressRes.data && !progressRes.data.in_progress) {
          clearInterval(pollInterval)
          if (progressRes.data.progress?.stage === 'completed') {
            setSuccessMessage(progressRes.data.progress.message || 'Entrenamiento completado')
          } else if (progressRes.data.last_error) {
            setError(`Error en entrenamiento: ${progressRes.data.last_error}`)
          }
        }
      }, 3000)

    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Error al iniciar entrenamiento'
      setError(errorMessage)
    } finally {
      setIsStartingTraining(false)
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
        <PageHeader>
          <Link href="/" className="flex items-center gap-2 text-muted-foreground hover:text-foreground">
            <IconChevronLeft className="h-4 w-4" />
            <IconBrain className="h-5 w-5 text-primary" />
            <span className="font-semibold text-foreground">Emma</span>
          </Link>
          <div className="h-4 w-px bg-border" />
          <IconDashboard className="h-4 w-4 text-muted-foreground" />
          <span className="text-muted-foreground">Administración</span>
        </PageHeader>

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
              <TabsList className="grid w-full grid-cols-7">
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
                <TabsTrigger value="boe">
                  <IconDatabase className="h-4 w-4 mr-2" />
                  BOE
                </TabsTrigger>
                <TabsTrigger value="heartbeat">
                  <IconHeartbeat className="h-4 w-4 mr-2" />
                  Heartbeat
                </TabsTrigger>
                <TabsTrigger value="training">
                  <IconCpu className="h-4 w-4 mr-2" />
                  IA Training
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

                  {/* CENDOJ Jurisprudence */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <IconGavel className="h-5 w-5" />
                        Jurisprudencia CENDOJ
                      </CardTitle>
                      <CardDescription>
                        Consulta de jurisprudencia del Poder Judicial
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="flex items-center justify-between">
                        <div className="space-y-0.5">
                          <Label htmlFor="cendoj-toggle">Habilitado</Label>
                          <p className="text-xs text-muted-foreground">
                            Busca sentencias en CENDOJ durante el análisis predictivo
                          </p>
                        </div>
                        <Switch
                          id="cendoj-toggle"
                          checked={cendojEnabled ?? false}
                          onCheckedChange={handleToggleCendoj}
                          disabled={isSavingCendoj || cendojEnabled === null}
                        />
                      </div>
                      <div className="space-y-2 text-sm text-muted-foreground">
                        <p>
                          Lanza un contenedor Docker efímero con Playwright para consultar
                          la base de datos de jurisprudencia del CENDOJ. Los resultados se
                          usan como evidencia en el análisis predictivo.
                        </p>
                        <div className="flex items-center gap-2">
                          <Badge variant="outline">{cendojSector || "—"}</Badge>
                          <span className="text-xs">Sector activo</span>
                        </div>
                      </div>
                      <Alert>
                        <IconAlertCircle className="h-4 w-4" />
                        <AlertDescription className="text-xs">
                          Solo uso personal de consulta (art. 560 LOPJ). No se almacena
                          contenido. Las sentencias se procesan en memoria y se descartan.
                        </AlertDescription>
                      </Alert>
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
                {/* Info banner when no entities */}
                {!isLoading && knowledgeStats && knowledgeStats.total_entities === 0 && (
                  <Alert>
                    <IconSchool className="h-4 w-4" />
                    <AlertDescription>
                      <strong>No hay entidades en el Knowledge Graph.</strong> Para extraer entidades de los documentos
                      públicos (legislación BOE), usa el botón "Extraer Entidades al Knowledge Graph" más abajo.
                      Las entidades permiten consultas semánticas avanzadas.
                    </AlertDescription>
                  </Alert>
                )}

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
                      {isLoading ? (
                        <div className="h-8 bg-muted animate-pulse rounded" />
                      ) : (
                        <>
                          <div className="flex items-center justify-between">
                            <span className="text-sm">Total entidades</span>
                            <span className="font-medium text-2xl">{formatNumber(knowledgeStats?.total_entities)}</span>
                          </div>
                          {(knowledgeStats?.tenant_entities !== undefined || knowledgeStats?.public_entities !== undefined) && (
                            <div className="pt-2 border-t space-y-1">
                              <div className="flex items-center justify-between text-sm text-muted-foreground">
                                <span>Propias del tenant</span>
                                <span>{formatNumber(knowledgeStats?.tenant_entities || 0)}</span>
                              </div>
                              <div className="flex items-center justify-between text-sm text-muted-foreground">
                                <span>Públicas (legislación)</span>
                                <span>{formatNumber(knowledgeStats?.public_entities || 0)}</span>
                              </div>
                            </div>
                          )}
                        </>
                      )}
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

              {/* Heartbeat Tab */}
              <TabsContent value="heartbeat" className="space-y-4">
                {/* Heartbeat Info Banner */}
                <Alert>
                  <IconHeartbeat className="h-4 w-4" />
                  <AlertDescription>
                    <strong>Emma Heartbeat — Inteligencia Proactiva</strong> — Sistema que evalúa periódicamente
                    el contexto del tenant (documentos, contratos, actividad) y genera insights automáticamente.
                    Configura notificaciones por email, Slack y otros canales.
                  </AlertDescription>
                </Alert>

                <div className="grid gap-4 md:grid-cols-2">
                  {/* Heartbeat Status */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <IconHeart className="h-5 w-5" />
                        Estado del Heartbeat
                      </CardTitle>
                      <CardDescription>
                        Estado actual y métricas del sistema proactivo
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      {isLoadingHeartbeat ? (
                        <div className="space-y-2">
                          {[1, 2, 3].map(i => (
                            <div key={i} className="h-8 bg-muted animate-pulse rounded" />
                          ))}
                        </div>
                      ) : heartbeatStatus ? (
                        <>
                          <div className="flex items-center justify-between">
                            <span className="text-sm">Estado</span>
                            {heartbeatStatus.enabled ? (
                              <Badge variant="default" className="bg-green-500">Activo</Badge>
                            ) : (
                              <Badge variant="secondary">Desactivado</Badge>
                            )}
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-sm">Última ejecución</span>
                            <span className="text-sm text-muted-foreground">
                              {heartbeatStatus.last_run_at
                                ? new Date(heartbeatStatus.last_run_at).toLocaleString('es-ES')
                                : 'Nunca'}
                            </span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-sm">Próxima ejecución</span>
                            <span className="text-sm text-muted-foreground">
                              {heartbeatStatus.next_run_at
                                ? new Date(heartbeatStatus.next_run_at).toLocaleString('es-ES')
                                : 'No programada'}
                            </span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-sm">Insights hoy</span>
                            <span className="font-medium">{heartbeatStatus.insights_delivered_today}</span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-sm">Pendientes</span>
                            <span className="font-medium">{heartbeatStatus.insights_pending}</span>
                          </div>
                        </>
                      ) : (
                        <p className="text-sm text-muted-foreground">No se pudo cargar el estado</p>
                      )}
                    </CardContent>
                    <CardFooter>
                      <Button
                        onClick={handleRunHeartbeat}
                        disabled={isRunningHeartbeat}
                        className="w-full"
                      >
                        {isRunningHeartbeat ? (
                          <>
                            <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                            Ejecutando...
                          </>
                        ) : (
                          <>
                            <IconPlayerPlay className="mr-2 h-4 w-4" />
                            Ejecutar Heartbeat Ahora
                          </>
                        )}
                      </Button>
                    </CardFooter>
                  </Card>

                  {/* General Configuration */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <IconActivity className="h-5 w-5" />
                        Configuración General
                      </CardTitle>
                      <CardDescription>
                        Ajusta la frecuencia y comportamiento del heartbeat
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      {heartbeatConfig ? (
                        <>
                          <div className="flex items-center justify-between">
                            <div className="space-y-0.5">
                              <Label>Heartbeat activo</Label>
                              <p className="text-xs text-muted-foreground">
                                Habilita o deshabilita el sistema
                              </p>
                            </div>
                            <Switch
                              checked={heartbeatConfig.enabled}
                              onCheckedChange={(checked) =>
                                handleUpdateHeartbeatConfig({ enabled: checked })
                              }
                              disabled={isSavingHeartbeat}
                            />
                          </div>
                          <div className="space-y-2">
                            <Label>Intervalo de ejecución</Label>
                            <div className="flex gap-2">
                              {[1, 2, 4, 6, 12, 24].map((hours) => (
                                <Button
                                  key={hours}
                                  variant={heartbeatConfig.run_interval_hours === hours ? "default" : "outline"}
                                  size="sm"
                                  onClick={() => handleUpdateHeartbeatConfig({ run_interval_hours: hours })}
                                  disabled={isSavingHeartbeat}
                                >
                                  {hours}h
                                </Button>
                              ))}
                            </div>
                          </div>
                          <div className="space-y-2">
                            <Label>Máx. insights por día</Label>
                            <div className="flex gap-2">
                              {[1, 3, 5, 10, 20].map((n) => (
                                <Button
                                  key={n}
                                  variant={heartbeatConfig.max_insights_per_day === n ? "default" : "outline"}
                                  size="sm"
                                  onClick={() => handleUpdateHeartbeatConfig({ max_insights_per_day: n })}
                                  disabled={isSavingHeartbeat}
                                >
                                  {n}
                                </Button>
                              ))}
                            </div>
                          </div>
                          <div className="space-y-2">
                            <Label>Umbral de prioridad (0-1)</Label>
                            <div className="flex gap-2">
                              {[0.3, 0.5, 0.6, 0.7, 0.8].map((t) => (
                                <Button
                                  key={t}
                                  variant={heartbeatConfig.priority_threshold === t ? "default" : "outline"}
                                  size="sm"
                                  onClick={() => handleUpdateHeartbeatConfig({ priority_threshold: t })}
                                  disabled={isSavingHeartbeat}
                                >
                                  {t}
                                </Button>
                              ))}
                            </div>
                            <p className="text-xs text-muted-foreground">
                              Solo insights con prioridad mayor a este valor serán entregados
                            </p>
                          </div>
                        </>
                      ) : (
                        <p className="text-sm text-muted-foreground">Cargando configuración...</p>
                      )}
                    </CardContent>
                  </Card>
                </div>

                {/* Rate Limiting & Digest */}
                <div className="grid gap-4 md:grid-cols-2">
                  {/* Rate Limiting */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <IconActivity className="h-5 w-5" />
                        Control de Frecuencia
                      </CardTitle>
                      <CardDescription>
                        Limita la cantidad de notificaciones para evitar saturación
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      {heartbeatConfig ? (
                        <>
                          <div className="space-y-2">
                            <Label>Máx. insights por hora</Label>
                            <div className="flex gap-2">
                              {[1, 2, 3, 5, 10].map((n) => (
                                <Button
                                  key={n}
                                  variant={heartbeatConfig.max_insights_per_hour === n ? "default" : "outline"}
                                  size="sm"
                                  onClick={() => handleUpdateHeartbeatConfig({ max_insights_per_hour: n })}
                                  disabled={isSavingHeartbeat}
                                >
                                  {n}
                                </Button>
                              ))}
                            </div>
                            <p className="text-xs text-muted-foreground">
                              Límite de notificaciones por hora
                            </p>
                          </div>
                          <div className="space-y-2">
                            <Label>Intervalo mínimo entre insights (min)</Label>
                            <div className="flex gap-2">
                              {[5, 15, 30, 60, 120].map((min) => (
                                <Button
                                  key={min}
                                  variant={heartbeatConfig.min_interval_minutes === min ? "default" : "outline"}
                                  size="sm"
                                  onClick={() => handleUpdateHeartbeatConfig({ min_interval_minutes: min })}
                                  disabled={isSavingHeartbeat}
                                >
                                  {min}
                                </Button>
                              ))}
                            </div>
                            <p className="text-xs text-muted-foreground">
                              Tiempo mínimo entre notificaciones consecutivas
                            </p>
                          </div>
                        </>
                      ) : (
                        <p className="text-sm text-muted-foreground">Cargando...</p>
                      )}
                    </CardContent>
                  </Card>

                  {/* Daily Digest */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <IconMail className="h-5 w-5" />
                        Resumen Diario (Digest)
                      </CardTitle>
                      <CardDescription>
                        Configura el envío del resumen diario de insights
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      {heartbeatConfig ? (
                        <>
                          <div className="space-y-2">
                            <Label>Hora del digest diario</Label>
                            <div className="flex flex-wrap gap-2">
                              {[7, 8, 9, 10, 12, 18].map((hour) => (
                                <Button
                                  key={hour}
                                  variant={heartbeatConfig.digest_hour === hour ? "default" : "outline"}
                                  size="sm"
                                  onClick={() => handleUpdateHeartbeatConfig({ digest_hour: hour })}
                                  disabled={isSavingHeartbeat}
                                >
                                  {hour}:00
                                </Button>
                              ))}
                            </div>
                            <p className="text-xs text-muted-foreground">
                              Hora a la que se enviará el resumen diario (zona horaria del servidor)
                            </p>
                          </div>
                          <div className="pt-2 border-t">
                            <p className="text-sm text-muted-foreground">
                              El digest incluye todos los insights de baja prioridad agrupados
                              (si "Agrupar baja prioridad" está activo).
                            </p>
                          </div>
                        </>
                      ) : (
                        <p className="text-sm text-muted-foreground">Cargando...</p>
                      )}
                    </CardContent>
                  </Card>
                </div>

                {/* Email Recipients & Quiet Hours */}
                <div className="grid gap-4 md:grid-cols-2">
                  {/* Email Recipients */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <IconMail className="h-5 w-5" />
                        Destinatarios de Email
                      </CardTitle>
                      <CardDescription>
                        Lista de emails que recibirán los insights proactivos
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      {heartbeatConfig ? (
                        <>
                          <div className="flex gap-2">
                            <input
                              type="email"
                              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                              placeholder="email@ejemplo.com"
                              value={newEmailRecipient}
                              onChange={(e) => setNewEmailRecipient(e.target.value)}
                              onKeyDown={(e) => e.key === 'Enter' && handleAddEmailRecipient()}
                            />
                            <Button
                              onClick={handleAddEmailRecipient}
                              disabled={isSavingHeartbeat || !newEmailRecipient}
                            >
                              Añadir
                            </Button>
                          </div>
                          <div className="space-y-2 max-h-48 overflow-y-auto">
                            {heartbeatConfig.email_recipients.length > 0 ? (
                              heartbeatConfig.email_recipients.map((email) => (
                                <div
                                  key={email}
                                  className="flex items-center justify-between p-2 bg-muted/50 rounded"
                                >
                                  <span className="text-sm">{email}</span>
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => handleRemoveEmailRecipient(email)}
                                    disabled={isSavingHeartbeat}
                                  >
                                    <IconTrash className="h-4 w-4 text-destructive" />
                                  </Button>
                                </div>
                              ))
                            ) : (
                              <p className="text-sm text-muted-foreground text-center py-4">
                                No hay destinatarios configurados
                              </p>
                            )}
                          </div>
                        </>
                      ) : (
                        <p className="text-sm text-muted-foreground">Cargando...</p>
                      )}
                    </CardContent>
                  </Card>

                  {/* Quiet Hours & Channels */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <IconClock className="h-5 w-5" />
                        Horario y Canales
                      </CardTitle>
                      <CardDescription>
                        Configura horas silenciosas y canales de notificación
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      {heartbeatConfig ? (
                        <>
                          <div className="space-y-2">
                            <Label>Horas silenciosas (no molestar)</Label>
                            <div className="flex items-center gap-2">
                              <input
                                type="time"
                                className="flex h-9 rounded-md border border-input bg-transparent px-3 py-1 text-sm"
                                value={heartbeatConfig.quiet_hours_start}
                                onChange={(e) =>
                                  handleUpdateHeartbeatConfig({ quiet_hours_start: e.target.value })
                                }
                                disabled={isSavingHeartbeat}
                              />
                              <span className="text-muted-foreground">a</span>
                              <input
                                type="time"
                                className="flex h-9 rounded-md border border-input bg-transparent px-3 py-1 text-sm"
                                value={heartbeatConfig.quiet_hours_end}
                                onChange={(e) =>
                                  handleUpdateHeartbeatConfig({ quiet_hours_end: e.target.value })
                                }
                                disabled={isSavingHeartbeat}
                              />
                            </div>
                            <p className="text-xs text-muted-foreground">
                              No se enviarán notificaciones durante este horario
                            </p>
                          </div>
                          <div className="space-y-2">
                            <Label>Canales activos</Label>
                            <div className="flex flex-wrap gap-2">
                              {['in_app', 'email', 'slack', 'telegram'].map((channel) => {
                                const isActive = heartbeatConfig.channel_priority.includes(channel)
                                const icons: Record<string, any> = {
                                  in_app: IconBell,
                                  email: IconMail,
                                  slack: IconBrandSlack,
                                  telegram: IconBell,
                                }
                                const labels: Record<string, string> = {
                                  in_app: 'In-App',
                                  email: 'Email',
                                  slack: 'Slack',
                                  telegram: 'Telegram',
                                }
                                const Icon = icons[channel] || IconBell
                                return (
                                  <Badge
                                    key={channel}
                                    variant={isActive ? "default" : "outline"}
                                    className="cursor-pointer"
                                    onClick={() => {
                                      const newChannels = isActive
                                        ? heartbeatConfig.channel_priority.filter(c => c !== channel)
                                        : [...heartbeatConfig.channel_priority, channel]
                                      handleUpdateHeartbeatConfig({ channel_priority: newChannels })
                                    }}
                                  >
                                    <Icon className="h-3 w-3 mr-1" />
                                    {labels[channel]}
                                  </Badge>
                                )
                              })}
                            </div>
                          </div>
                          <div className="flex items-center justify-between pt-2">
                            <div className="space-y-0.5">
                              <Label>Agrupar baja prioridad</Label>
                              <p className="text-xs text-muted-foreground">
                                Agrupa insights de baja prioridad en digest diario
                              </p>
                            </div>
                            <Switch
                              checked={heartbeatConfig.batch_low_priority}
                              onCheckedChange={(checked) =>
                                handleUpdateHeartbeatConfig({ batch_low_priority: checked })
                              }
                              disabled={isSavingHeartbeat}
                            />
                          </div>
                        </>
                      ) : (
                        <p className="text-sm text-muted-foreground">Cargando...</p>
                      )}
                    </CardContent>
                  </Card>
                </div>
              </TabsContent>

              {/* Training Tab */}
              <TabsContent value="training" className="space-y-4">
                {/* Training Info Banner */}
                <Alert>
                  <IconCpu className="h-4 w-4" />
                  <AlertDescription>
                    <strong>Entrenamiento de Embeddings por Sector</strong> — Fine-tune del modelo de embeddings
                    para mejorar la comprensión semántica de consultas del sector activo. El modelo base
                    (all-MiniLM-L6-v2) funciona sin entrenamiento; el fine-tuning mejora la precisión.
                  </AlertDescription>
                </Alert>

                {/* Sector Status Cards */}
                <div className="grid gap-4 md:grid-cols-3">
                  {(trainingStatus?.sectors || []).map((sector) => (
                    <Card
                      key={sector.sector}
                      className={`cursor-pointer transition-colors ${
                        selectedTrainingSector === sector.sector
                          ? 'border-2 border-primary'
                          : 'hover:border-muted-foreground/30'
                      } ${trainingStatus?.active_sector === sector.sector ? 'bg-primary/5' : ''}`}
                      onClick={() => setSelectedTrainingSector(sector.sector)}
                    >
                      <CardHeader className="pb-3">
                        <CardTitle className="flex items-center justify-between text-base">
                          <span className="capitalize">{sector.sector}</span>
                          <div className="flex items-center gap-2">
                            {trainingStatus?.active_sector === sector.sector && (
                              <Badge variant="default" className="text-xs">Activo</Badge>
                            )}
                            {sector.has_trained_model ? (
                              <Badge variant="default" className="bg-green-500 text-xs">
                                <IconCheck className="h-3 w-3 mr-1" />
                                Entrenado
                              </Badge>
                            ) : (
                              <Badge variant="outline" className="text-xs">Base</Badge>
                            )}
                          </div>
                        </CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-2">
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-muted-foreground">Conceptos QA</span>
                          <span className="font-medium">{sector.qa_concepts_count}</span>
                        </div>
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-muted-foreground">Preguntas</span>
                          <span className="font-medium">{sector.qa_questions_count}</span>
                        </div>
                        {sector.has_trained_model && (
                          <div className="text-xs text-muted-foreground pt-1 truncate">
                            {sector.model_path}
                          </div>
                        )}
                      </CardContent>
                    </Card>
                  ))}
                </div>

                {/* Training Configuration */}
                <div className="grid gap-4 md:grid-cols-2">
                  {/* Training Options */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <IconRobot className="h-5 w-5" />
                        Configuración de Entrenamiento
                      </CardTitle>
                      <CardDescription>
                        Fine-tune del modelo de embeddings para el sector seleccionado
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div>
                        <Label className="text-sm font-medium">Sector seleccionado</Label>
                        <div className="mt-1 p-3 bg-muted rounded-lg">
                          <span className="capitalize font-medium text-primary">
                            {selectedTrainingSector || 'Ninguno seleccionado'}
                          </span>
                          {selectedTrainingSector && trainingStatus?.sectors && (
                            <p className="text-xs text-muted-foreground mt-1">
                              {trainingStatus.sectors.find(s => s.sector === selectedTrainingSector)?.qa_concepts_count || 0} conceptos,{' '}
                              {trainingStatus.sectors.find(s => s.sector === selectedTrainingSector)?.qa_questions_count || 0} preguntas
                            </p>
                          )}
                        </div>
                      </div>

                      <div>
                        <Label htmlFor="training-epochs" className="text-sm font-medium">Epochs</Label>
                        <p className="text-xs text-muted-foreground mb-1">
                          Más epochs = mayor precisión pero más tiempo
                        </p>
                        <div className="flex gap-2">
                          {[1, 3, 5, 10].map((n) => (
                            <Button
                              key={n}
                              variant={trainingEpochs === n ? "default" : "outline"}
                              size="sm"
                              onClick={() => setTrainingEpochs(n)}
                            >
                              {n}
                            </Button>
                          ))}
                        </div>
                      </div>

                      <div>
                        <Label htmlFor="hf-dataset" className="text-sm font-medium">
                          Dataset HuggingFace (opcional)
                        </Label>
                        <p className="text-xs text-muted-foreground mb-1">
                          Dataset adicional para ampliar el entrenamiento
                        </p>
                        <input
                          id="hf-dataset"
                          type="text"
                          className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                          placeholder="ej: dariolopez/justicio-rag-embedding-qa-tmp"
                          value={trainingHfDataset}
                          onChange={(e) => setTrainingHfDataset(e.target.value)}
                        />
                      </div>
                    </CardContent>
                    <CardFooter>
                      <Button
                        onClick={() => setShowTrainingDialog(true)}
                        disabled={!selectedTrainingSector || isStartingTraining || !!trainingStatus?.training_in_progress}
                        className="w-full"
                      >
                        {isStartingTraining ? (
                          <>
                            <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                            Iniciando...
                          </>
                        ) : trainingStatus?.training_in_progress ? (
                          <>
                            <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                            Entrenamiento en curso ({trainingStatus.training_in_progress})...
                          </>
                        ) : (
                          <>
                            <IconPlayerPlay className="mr-2 h-4 w-4" />
                            Iniciar Entrenamiento
                          </>
                        )}
                      </Button>
                    </CardFooter>
                  </Card>

                  {/* Training Progress / Info */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <IconActivity className="h-5 w-5" />
                        Estado del Entrenamiento
                      </CardTitle>
                      <CardDescription>
                        Progreso y resultados del último entrenamiento
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      {trainingStatus?.training_in_progress ? (
                        <div className="space-y-3">
                          <div className="flex items-center gap-2">
                            <IconLoader2 className="h-5 w-5 animate-spin text-primary" />
                            <span className="font-medium">
                              Entrenando: <span className="capitalize">{trainingStatus.training_in_progress}</span>
                            </span>
                          </div>
                          {trainingStatus.training_progress && (
                            <div className="rounded-lg bg-muted p-4 space-y-2">
                              <div className="flex items-center justify-between text-sm">
                                <span className="text-muted-foreground">Fase</span>
                                <Badge variant="outline">{trainingStatus.training_progress.stage}</Badge>
                              </div>
                              <p className="text-sm">{trainingStatus.training_progress.message}</p>
                              {trainingStatus.training_progress.total_examples && (
                                <div className="flex items-center justify-between text-sm">
                                  <span className="text-muted-foreground">Ejemplos</span>
                                  <span>{trainingStatus.training_progress.total_examples}</span>
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      ) : trainingProgress?.progress?.stage === 'completed' ? (
                        <div className="space-y-3">
                          <div className="flex items-center gap-2 text-green-600">
                            <IconCircleCheck className="h-5 w-5" />
                            <span className="font-medium">Entrenamiento completado</span>
                          </div>
                          <div className="rounded-lg bg-muted p-4 space-y-2">
                            <p className="text-sm">{trainingProgress.progress.message}</p>
                            {trainingProgress.progress.total_examples && (
                              <div className="flex items-center justify-between text-sm">
                                <span className="text-muted-foreground">Ejemplos totales</span>
                                <span>{trainingProgress.progress.total_examples}</span>
                              </div>
                            )}
                            {trainingProgress.progress.elapsed_seconds && (
                              <div className="flex items-center justify-between text-sm">
                                <span className="text-muted-foreground">Duración</span>
                                <span>{trainingProgress.progress.elapsed_seconds.toFixed(1)}s</span>
                              </div>
                            )}
                          </div>
                        </div>
                      ) : trainingProgress?.last_error ? (
                        <Alert variant="destructive">
                          <IconAlertCircle className="h-4 w-4" />
                          <AlertDescription>{trainingProgress.last_error}</AlertDescription>
                        </Alert>
                      ) : (
                        <div className="text-center py-8 text-muted-foreground">
                          <IconCpu className="h-12 w-12 mx-auto mb-3 opacity-30" />
                          <p className="text-sm">No hay entrenamientos recientes</p>
                          <p className="text-xs mt-1">
                            Selecciona un sector y haz clic en "Iniciar Entrenamiento"
                          </p>
                        </div>
                      )}

                      {/* How it works */}
                      <div className="rounded-lg border p-4 space-y-2">
                        <h4 className="text-sm font-medium">¿Cómo funciona?</h4>
                        <ul className="text-xs text-muted-foreground space-y-1">
                          <li>• Se carga el modelo base (all-MiniLM-L6-v2)</li>
                          <li>• Se entrena con los pares QA del sector + dataset opcional</li>
                          <li>• El modelo entrenado se guarda en disco</li>
                          <li>• Al reiniciar, Emma usa el modelo entrenado automáticamente</li>
                          <li>• Sin modelo entrenado, Emma usa el modelo base (funciona igualmente)</li>
                        </ul>
                      </div>
                    </CardContent>
                  </Card>
                </div>
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
                              Configura fuentes de datos externas (Alfresco, OneDrive, Google Drive, etc.)
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

                      <div className="flex items-center justify-between p-4 border rounded-lg">
                        <div className="flex items-center gap-4">
                          <IconSparkles className="h-8 w-8 text-violet-500" />
                          <div>
                            <h4 className="font-medium">Gestión de Prompts (Langfuse)</h4>
                            <p className="text-sm text-muted-foreground">
                              Edita y versiona los prompts de Emma
                            </p>
                          </div>
                        </div>
                        <Button variant="outline" asChild>
                          <a
                            href={process.env.NEXT_PUBLIC_LANGFUSE_URL || "http://localhost:3002"}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center gap-2"
                          >
                            Abrir
                            <IconExternalLink className="h-4 w-4" />
                          </a>
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
            <AlertDialogDescription asChild>
              <div>
                <p>Esta acción no se puede deshacer. Se eliminarán permanentemente:</p>
                <ul className="mt-2 list-disc list-inside text-sm text-muted-foreground">
                  <li>{formatNumber(systemStats?.documents.total)} documentos</li>
                  <li>{formatBytes(systemStats?.storage.total_bytes)} de archivos</li>
                  <li>Todos los datos vectoriales</li>
                </ul>
              </div>
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

      {/* Training Confirmation Dialog */}
      <AlertDialog open={showTrainingDialog} onOpenChange={setShowTrainingDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Iniciar entrenamiento de embeddings?</AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div>
                <p>Se entrenará un modelo de embeddings personalizado para el sector:</p>
                <div className="mt-2 p-3 bg-muted rounded-lg space-y-1">
                  <p className="font-medium capitalize">{selectedTrainingSector}</p>
                  <p className="text-sm">
                    {trainingStatus?.sectors?.find(s => s.sector === selectedTrainingSector)?.qa_concepts_count || 0} conceptos,{' '}
                    {trainingEpochs} epochs
                  </p>
                  {trainingHfDataset && (
                    <p className="text-sm">Dataset: {trainingHfDataset}</p>
                  )}
                </div>
                <p className="mt-2 text-sm text-amber-600">
                  ⚠️ El entrenamiento se ejecuta en segundo plano. El servicio seguirá funcionando normalmente.
                </p>
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={handleStartTraining}>
              <IconPlayerPlay className="mr-2 h-4 w-4" />
              Iniciar Entrenamiento
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Knowledge Extraction Confirmation Dialog */}
      <AlertDialog open={showKnowledgeExtractDialog} onOpenChange={setShowKnowledgeExtractDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Extraer entidades al Knowledge Graph?</AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div>
                <p>Se procesarán los documentos públicos (legislación) para extraer entidades:</p>
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
              </div>
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
