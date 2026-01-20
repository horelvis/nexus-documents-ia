'use client'

/**
 * Data Learning Page for Emma
 *
 * Admin page to manage the Data Learning System:
 * - View connector learning status
 * - Trigger learning jobs
 * - Manage folder patterns, property mappings, and indexing strategies
 */

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import {
  IconBrain,
  IconLoader2,
  IconSchool,
  IconChevronLeft,
  IconRefresh,
  IconPlayerPlay,
  IconCircleX,
  IconCircleCheck,
  IconAlertTriangle,
  IconFolders,
  IconFileCode,
  IconLink,
  IconAdjustmentsHorizontal,
  IconHistory,
  IconBulb,
} from '@tabler/icons-react'
import {
  SidebarProvider,
  SidebarInset,
  SidebarTrigger,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Button,
  Badge,
  Alert,
  AlertDescription,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Progress,
} from '@nexus/shared/ui'
import { useAuth } from '@/contexts/auth-context'
import { AppSidebar } from '@/components/layout/app-sidebar'
import {
  connectorService,
  connectorNames,
  Connector,
} from '@/lib/services/connector.service'
import {
  dataLearningService,
  ConnectorLearningStatus,
  DataLearningJob,
  jobTypeLabels,
  jobStatusLabels,
} from '@/lib/services/data-learning.service'
import { ContentModelView } from '@/components/data-learning/content-model-view'
import { FolderPatternsView } from '@/components/data-learning/folder-patterns-view'
import { PropertyMappingsView } from '@/components/data-learning/property-mappings-view'
import { IndexingStrategiesView } from '@/components/data-learning/indexing-strategies-view'
import { LearningJobsView } from '@/components/data-learning/learning-jobs-view'

function getStatusBadge(status: string) {
  const config: Record<string, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
    pending: { label: 'Pendiente', variant: 'outline' },
    running: { label: 'Ejecutando', variant: 'secondary' },
    completed: { label: 'Completado', variant: 'default' },
    failed: { label: 'Fallido', variant: 'destructive' },
    cancelled: { label: 'Cancelado', variant: 'outline' },
  }
  const { label, variant } = config[status] || config.pending
  return <Badge variant={variant}>{label}</Badge>
}

// ============================================================================
// Main Page Component
// ============================================================================

export default function DataLearningPage() {
  const { isLoaded, isAuthenticated } = useAuth()
  const router = useRouter()

  // UI State
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Data State
  const [connectors, setConnectors] = useState<Connector[]>([])
  const [selectedConnectorId, setSelectedConnectorId] = useState<string | null>(null)
  const [learningStatus, setLearningStatus] = useState<ConnectorLearningStatus | null>(null)
  const [isLoadingStatus, setIsLoadingStatus] = useState(false)

  // Action State
  const [isTriggering, setIsTriggering] = useState(false)

  // Load connectors on mount
  const loadConnectors = async () => {
    setIsLoading(true)
    setError(null)

    try {
      const result = await connectorService.getConnectors()
      if (result.data) {
        setConnectors(result.data.items)
        // Auto-select first connector if available
        if (result.data.items.length > 0 && !selectedConnectorId) {
          setSelectedConnectorId(result.data.items[0].id)
        }
      } else if (result.error) {
        setError(result.error)
      }
    } catch (err: any) {
      setError(err.message || 'Error al cargar conectores')
    } finally {
      setIsLoading(false)
    }
  }

  // Load learning status when connector is selected
  const loadLearningStatus = async () => {
    if (!selectedConnectorId) return

    setIsLoadingStatus(true)
    setError(null)

    try {
      const result = await dataLearningService.getLearningStatus(selectedConnectorId)
      if (result.data) {
        setLearningStatus(result.data)
      } else if (result.error) {
        setError(result.error)
      }
    } catch (err: any) {
      setError(err.message || 'Error al cargar estado de aprendizaje')
    } finally {
      setIsLoadingStatus(false)
    }
  }

  // Trigger full learning
  const handleTriggerLearning = async () => {
    if (!selectedConnectorId) return

    setIsTriggering(true)
    setError(null)

    try {
      const result = await dataLearningService.triggerLearning(selectedConnectorId, {
        job_type: 'full_learning',
      })
      if (result.data) {
        // Reload status to show new job
        await loadLearningStatus()
      } else if (result.error) {
        setError(result.error)
      }
    } catch (err: any) {
      setError(err.message || 'Error al iniciar aprendizaje')
    } finally {
      setIsTriggering(false)
    }
  }

  useEffect(() => {
    if (isLoaded && isAuthenticated) {
      loadConnectors()
    }
  }, [isLoaded, isAuthenticated])

  useEffect(() => {
    if (selectedConnectorId) {
      loadLearningStatus()
    }
  }, [selectedConnectorId])

  useEffect(() => {
    if (isLoaded && !isAuthenticated) {
      router.push('/auth/sign-in')
    }
  }, [isLoaded, isAuthenticated, router])

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

  const selectedConnector = connectors.find(c => c.id === selectedConnectorId)

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
          <IconSchool className="h-4 w-4 text-muted-foreground" />
          <span className="text-muted-foreground">Data Learning</span>
        </header>

        {/* Main Content */}
        <main className="flex-1 overflow-auto p-6">
          <div className="max-w-6xl mx-auto space-y-6">
            {/* Title & Connector Selector */}
            <div className="flex items-start justify-between gap-4">
              <div>
                <h1 className="text-2xl font-bold">Sistema de Aprendizaje de Datos</h1>
                <p className="text-muted-foreground">
                  Permite a Emma aprender la naturaleza de los datos de tus conectores
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Select
                  value={selectedConnectorId || ''}
                  onValueChange={setSelectedConnectorId}
                >
                  <SelectTrigger className="w-[240px]">
                    <SelectValue placeholder="Selecciona un conector" />
                  </SelectTrigger>
                  <SelectContent>
                    {connectors.map((connector) => (
                      <SelectItem key={connector.id} value={connector.id}>
                        {connector.name} ({connectorNames[connector.connector_type]})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button
                  variant="outline"
                  onClick={() => {
                    loadConnectors()
                    if (selectedConnectorId) loadLearningStatus()
                  }}
                  disabled={isLoading || isLoadingStatus}
                >
                  <IconRefresh className={`h-4 w-4 ${(isLoading || isLoadingStatus) ? 'animate-spin' : ''}`} />
                </Button>
              </div>
            </div>

            {/* Error Alert */}
            {error && (
              <Alert variant="destructive">
                <IconCircleX className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            {/* No Connectors State */}
            {!isLoading && connectors.length === 0 && (
              <Card>
                <CardContent className="py-12">
                  <div className="text-center">
                    <IconSchool className="h-12 w-12 mx-auto mb-4 text-muted-foreground opacity-50" />
                    <p className="text-muted-foreground mb-4">No hay conectores configurados</p>
                    <Button asChild>
                      <Link href="/connectors/new">Crear Conector</Link>
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Loading State */}
            {(isLoading || isLoadingStatus) && connectors.length > 0 && (
              <div className="flex items-center justify-center py-12">
                <IconLoader2 className="h-8 w-8 animate-spin text-primary" />
              </div>
            )}

            {/* Learning Status Content */}
            {!isLoading && !isLoadingStatus && selectedConnector && learningStatus && (
              <>
                {/* Status Overview */}
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                  <Card>
                    <CardHeader className="pb-2">
                      <CardDescription>Modelo de Contenido</CardDescription>
                      <CardTitle className="text-2xl flex items-center gap-2">
                        {learningStatus.has_content_model ? (
                          <>
                            <IconCircleCheck className="h-5 w-5 text-green-500" />
                            Descubierto
                          </>
                        ) : (
                          <>
                            <IconAlertTriangle className="h-5 w-5 text-yellow-500" />
                            Pendiente
                          </>
                        )}
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      {learningStatus.content_model_summary && (
                        <p className="text-xs text-muted-foreground">
                          {learningStatus.content_model_summary.total_types} tipos,{' '}
                          {learningStatus.content_model_summary.total_aspects} aspectos
                        </p>
                      )}
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader className="pb-2">
                      <CardDescription>Patrones de Carpeta</CardDescription>
                      <CardTitle className="text-2xl">
                        {learningStatus.folder_patterns_count}
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <p className="text-xs text-muted-foreground">
                        {learningStatus.verified_patterns_count} verificados
                      </p>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader className="pb-2">
                      <CardDescription>Mapeos de Propiedades</CardDescription>
                      <CardTitle className="text-2xl">
                        {learningStatus.property_mappings_count}
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <p className="text-xs text-muted-foreground">
                        {learningStatus.custom_mappings_count} personalizados
                      </p>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader className="pb-2">
                      <CardDescription>Estrategias de Indexación</CardDescription>
                      <CardTitle className="text-2xl">
                        {learningStatus.indexing_strategies_count}
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <p className="text-xs text-muted-foreground">
                        {learningStatus.active_strategies_count} activas
                      </p>
                    </CardContent>
                  </Card>
                </div>

                {/* Recommendations */}
                {learningStatus.recommendations.length > 0 && (
                  <Alert>
                    <IconBulb className="h-4 w-4" />
                    <AlertDescription>
                      <strong>Recomendaciones:</strong>
                      <ul className="mt-2 list-disc list-inside space-y-1">
                        {learningStatus.recommendations.map((rec, idx) => (
                          <li key={idx}>{rec}</li>
                        ))}
                      </ul>
                    </AlertDescription>
                  </Alert>
                )}

                {/* Latest Job Status */}
                {learningStatus.latest_job && (
                  <Card>
                    <CardHeader>
                      <div className="flex items-center justify-between">
                        <div>
                          <CardTitle className="text-lg">Último Job de Aprendizaje</CardTitle>
                          <CardDescription>
                            {jobTypeLabels[learningStatus.latest_job.job_type]}
                          </CardDescription>
                        </div>
                        {getStatusBadge(learningStatus.latest_job.status)}
                      </div>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-4">
                        {learningStatus.latest_job.status === 'running' && (
                          <div className="space-y-2">
                            <div className="flex items-center justify-between text-sm">
                              <span>{learningStatus.latest_job.current_phase || 'Procesando...'}</span>
                              <span>{learningStatus.latest_job.progress_percent}%</span>
                            </div>
                            <Progress value={learningStatus.latest_job.progress_percent} />
                          </div>
                        )}
                        {learningStatus.latest_job.status === 'completed' && learningStatus.latest_job.results_summary && (
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                            {Object.entries(learningStatus.latest_job.results_summary).map(([key, value]) => (
                              <div key={key}>
                                <span className="text-muted-foreground">{key}:</span>{' '}
                                <span className="font-medium">{String(value)}</span>
                              </div>
                            ))}
                          </div>
                        )}
                        {learningStatus.latest_job.status === 'failed' && learningStatus.latest_job.status_message && (
                          <Alert variant="destructive">
                            <AlertDescription>{learningStatus.latest_job.status_message}</AlertDescription>
                          </Alert>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                )}

                {/* Action Button */}
                <div className="flex justify-end">
                  <Button
                    onClick={handleTriggerLearning}
                    disabled={isTriggering || (learningStatus.latest_job?.status === 'running')}
                  >
                    {isTriggering ? (
                      <IconLoader2 className="h-4 w-4 mr-2 animate-spin" />
                    ) : (
                      <IconPlayerPlay className="h-4 w-4 mr-2" />
                    )}
                    Iniciar Aprendizaje Completo
                  </Button>
                </div>

                {/* Detailed Tabs */}
                <Tabs defaultValue="content-model" className="space-y-4">
                  <TabsList className="grid w-full grid-cols-5">
                    <TabsTrigger value="content-model" className="flex items-center gap-1">
                      <IconFileCode className="h-4 w-4" />
                      <span className="hidden sm:inline">Modelo</span>
                    </TabsTrigger>
                    <TabsTrigger value="folder-patterns" className="flex items-center gap-1">
                      <IconFolders className="h-4 w-4" />
                      <span className="hidden sm:inline">Carpetas</span>
                    </TabsTrigger>
                    <TabsTrigger value="property-mappings" className="flex items-center gap-1">
                      <IconAdjustmentsHorizontal className="h-4 w-4" />
                      <span className="hidden sm:inline">Propiedades</span>
                    </TabsTrigger>
                    <TabsTrigger value="indexing-strategies" className="flex items-center gap-1">
                      <IconLink className="h-4 w-4" />
                      <span className="hidden sm:inline">Estrategias</span>
                    </TabsTrigger>
                    <TabsTrigger value="jobs" className="flex items-center gap-1">
                      <IconHistory className="h-4 w-4" />
                      <span className="hidden sm:inline">Jobs</span>
                    </TabsTrigger>
                  </TabsList>

                  <TabsContent value="content-model">
                    <ContentModelView connectorId={selectedConnectorId!} />
                  </TabsContent>

                  <TabsContent value="folder-patterns">
                    <FolderPatternsView connectorId={selectedConnectorId!} onUpdate={loadLearningStatus} />
                  </TabsContent>

                  <TabsContent value="property-mappings">
                    <PropertyMappingsView connectorId={selectedConnectorId!} onUpdate={loadLearningStatus} />
                  </TabsContent>

                  <TabsContent value="indexing-strategies">
                    <IndexingStrategiesView connectorId={selectedConnectorId!} onUpdate={loadLearningStatus} />
                  </TabsContent>

                  <TabsContent value="jobs">
                    <LearningJobsView connectorId={selectedConnectorId!} />
                  </TabsContent>
                </Tabs>
              </>
            )}
          </div>
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}
