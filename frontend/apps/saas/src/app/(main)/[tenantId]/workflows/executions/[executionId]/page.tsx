"use client"

import { useState, useEffect, use } from "react"
import { useWorkflowsService } from "@/lib/services/workflows.service"
import { 
  IconArrowLeft, 
  IconRefresh,
  IconClock,
  IconCircleCheck,
  IconAlertCircle,
  IconUsers,
  IconRobot,
  IconFileText,
  IconActivity,
  IconDownload,
  IconEye
} from "@tabler/icons-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { Separator } from "@/components/ui/separator"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Alert, AlertDescription } from "@/components/ui/alert"
import Link from "next/link"

interface WorkflowExecution {
  id: string
  template_name: string
  template_id: string
  status: string
  progress_percentage: number
  current_step?: string
  started_at: string
  completed_at?: string
  output_data?: any
  execution_log?: Array<{
    step: string
    timestamp: string
    current_step?: string
    state: string
    data: any
  }>
}

export default function WorkflowExecutionPage({ params }: { params: Promise<{ tenantId: string, executionId: string }> }) {
  const resolvedParams = use(params)
  const workflowsService = useWorkflowsService()
  
  const [execution, setExecution] = useState<WorkflowExecution | null>(null)
  const [logs, setLogs] = useState<any>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)

  const loadExecution = async () => {
    try {
      const [executionData, logsData] = await Promise.all([
        workflowsService.getWorkflowExecution(resolvedParams.executionId),
        workflowsService.getWorkflowExecutionLogs(resolvedParams.executionId)
      ])
      
      setExecution(executionData)
      setLogs(logsData)
    } catch (error) {
      console.error('Error loading execution:', error)
    }
  }

  const refreshExecution = async () => {
    setIsRefreshing(true)
    await loadExecution()
    setIsRefreshing(false)
  }

  useEffect(() => {
    const loadData = async () => {
      setIsLoading(true)
      await loadExecution()
      setIsLoading(false)
    }
    
    loadData()
    
    // Auto-refresh if execution is running
    const interval = setInterval(async () => {
      if (execution?.status === 'running' || execution?.status === 'pending') {
        await loadExecution()
      }
    }, 5000) // Refresh every 5 seconds
    
    return () => clearInterval(interval)
  }, [resolvedParams.executionId])

  const getStatusColor = (status: string) => {
    switch (status) {
      case "completed": return "text-green-600 bg-green-100"
      case "running": return "text-blue-600 bg-blue-100"
      case "pending": return "text-yellow-600 bg-yellow-100" 
      case "failed": return "text-red-600 bg-red-100"
      default: return "text-gray-600 bg-gray-100"
    }
  }

  const getStatusText = (status: string) => {
    switch (status) {
      case "completed": return "Completado"
      case "running": return "En Ejecución"
      case "pending": return "Pendiente"
      case "failed": return "Fallido"
      default: return "Desconocido"
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "completed": return <IconCircleCheck className="h-5 w-5 text-green-600" />
      case "running": return <IconActivity className="h-5 w-5 text-blue-600 animate-pulse" />
      case "pending": return <IconClock className="h-5 w-5 text-yellow-600" />
      case "failed": return <IconAlertCircle className="h-5 w-5 text-red-600" />
      default: return <IconActivity className="h-5 w-5 text-gray-600" />
    }
  }

  const formatTimestamp = (timestamp: string) => {
    return new Date(timestamp).toLocaleString('es-ES', {
      year: 'numeric',
      month: 'short', 
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  const getDuration = () => {
    if (!execution?.started_at) return null
    
    const start = new Date(execution.started_at)
    const end = execution.completed_at ? new Date(execution.completed_at) : new Date()
    const diffMs = end.getTime() - start.getTime()
    
    const days = Math.floor(diffMs / (1000 * 60 * 60 * 24))
    const hours = Math.floor((diffMs % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60))
    const minutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60))
    
    if (days > 0) return `${days}d ${hours}h ${minutes}m`
    if (hours > 0) return `${hours}h ${minutes}m`
    return `${minutes}m`
  }

  if (isLoading) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="animate-pulse space-y-6">
          <div className="h-8 bg-gray-200 rounded w-1/3"></div>
          <div className="h-48 bg-gray-200 rounded"></div>
          <div className="h-64 bg-gray-200 rounded"></div>
        </div>
      </div>
    )
  }

  if (!execution) {
    return (
      <div className="container mx-auto px-4 py-8">
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <IconAlertCircle className="h-16 w-16 text-red-300 mb-4" />
            <p className="text-red-500 mb-2">Ejecución no encontrada</p>
            <Button asChild variant="outline">
              <Link href={`/${resolvedParams.tenantId}/workflows`}>
                Volver a Workflows
              </Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="container mx-auto px-4 py-8 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="sm" asChild>
          <Link href={`/${resolvedParams.tenantId}/workflows`}>
            <IconArrowLeft className="h-4 w-4" />
          </Link>
        </Button>
        <div className="flex-1">
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
            {getStatusIcon(execution.status)}
            {execution.template_name}
          </h1>
          <p className="text-muted-foreground mt-1">
            ID: {execution.id.substring(0, 8)}...
          </p>
        </div>
        <Button 
          variant="outline" 
          onClick={refreshExecution}
          disabled={isRefreshing}
        >
          <IconRefresh className={`h-4 w-4 mr-2 ${isRefreshing ? 'animate-spin' : ''}`} />
          Actualizar
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Content */}
        <div className="lg:col-span-2 space-y-6">
          {/* Status Overview */}
          <Card>
            <CardHeader>
              <CardTitle>Estado del Proceso</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <Badge className={getStatusColor(execution.status)} variant="secondary">
                  {getStatusText(execution.status)}
                </Badge>
                <span className="text-sm text-muted-foreground">
                  {execution.progress_percentage}% completado
                </span>
              </div>
              
              <Progress value={execution.progress_percentage} className="h-2" />
              
              {execution.current_step && (
                <div className="text-sm">
                  <span className="text-muted-foreground">Paso actual: </span>
                  <span className="font-medium">{execution.current_step}</span>
                </div>
              )}
              
              <div className="grid grid-cols-2 gap-4 pt-2">
                <div>
                  <p className="text-sm text-muted-foreground">Iniciado</p>
                  <p className="font-medium">{formatTimestamp(execution.started_at)}</p>
                </div>
                {execution.completed_at && (
                  <div>
                    <p className="text-sm text-muted-foreground">Completado</p>
                    <p className="font-medium">{formatTimestamp(execution.completed_at)}</p>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Emma AI Results */}
          {execution.output_data && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <IconRobot className="h-5 w-5 text-blue-600" />
                  Resultados de Emma AI
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {Object.entries(execution.output_data).map(([stepId, stepResult]: [string, any]) => (
                    <div key={stepId} className="border rounded-lg p-4">
                      <h4 className="font-medium mb-2 capitalize">{stepId.replace(/_/g, ' ')}</h4>
                      
                      {stepResult.analysis_result && (
                        <div className="space-y-2">
                          <h5 className="text-sm font-medium text-muted-foreground">Análisis Legal</h5>
                          <div className="grid grid-cols-2 gap-4 text-sm">
                            <div>
                              <span className="text-muted-foreground">Confianza:</span>
                              <span className="ml-2 font-medium">{stepResult.analysis_result.overall_confidence}</span>
                            </div>
                            <div>
                              <span className="text-muted-foreground">Riesgo:</span>
                              <span className="ml-2 font-medium">{stepResult.analysis_result.risk_level}</span>
                            </div>
                            <div>
                              <span className="text-muted-foreground">Complejidad:</span>
                              <span className="ml-2 font-medium">{stepResult.analysis_result.complexity_level}</span>
                            </div>
                            <div>
                              <span className="text-muted-foreground">Plazo:</span>
                              <span className="ml-2 font-medium">{stepResult.analysis_result.estimated_timeline}</span>
                            </div>
                          </div>
                        </div>
                      )}
                      
                      {stepResult.generated_document && (
                        <div className="space-y-2 mt-3">
                          <h5 className="text-sm font-medium text-muted-foreground">Documento Generado</h5>
                          <div className="flex items-center justify-between p-2 bg-gray-50 rounded">
                            <div className="flex items-center gap-2">
                              <IconFileText className="h-4 w-4 text-blue-600" />
                              <span className="text-sm font-medium">{stepResult.generated_document.title}</span>
                            </div>
                            <div className="flex gap-2">
                              <Button size="sm" variant="outline">
                                <IconEye className="h-3 w-3 mr-1" />
                                Ver
                              </Button>
                              <Button size="sm" variant="outline">
                                <IconDownload className="h-3 w-3 mr-1" />
                                Descargar
                              </Button>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Execution Log */}
          <Card>
            <CardHeader>
              <CardTitle>Log de Ejecución</CardTitle>
              <CardDescription>
                Historial detallado de la ejecución del workflow
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-96">
                <div className="space-y-4">
                  {logs?.execution_log?.map((entry: any, index: number) => (
                    <div key={index} className="flex gap-4 pb-4 border-b last:border-b-0">
                      <div className="w-2 h-2 rounded-full bg-blue-500 mt-2 flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between mb-1">
                          <h4 className="text-sm font-medium">{entry.step}</h4>
                          <span className="text-xs text-muted-foreground">
                            {formatTimestamp(entry.timestamp)}
                          </span>
                        </div>
                        {entry.current_step && (
                          <p className="text-sm text-muted-foreground mb-1">
                            Paso: {entry.current_step}
                          </p>
                        )}
                        <Badge variant="outline" className="text-xs">
                          {entry.state}
                        </Badge>
                        {entry.data?.success && (
                          <p className="text-sm text-green-600 mt-1">
                            ✅ {entry.data.message}
                          </p>
                        )}
                        {entry.data?.error && (
                          <p className="text-sm text-red-600 mt-1">
                            ❌ {entry.data.error}
                          </p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </ScrollArea>
            </CardContent>
          </Card>
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* Summary */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Resumen</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Estado</span>
                <Badge className={getStatusColor(execution.status)}>
                  {getStatusText(execution.status)}
                </Badge>
              </div>
              
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Progreso</span>
                <span className="text-sm font-medium">{execution.progress_percentage}%</span>
              </div>
              
              {getDuration() && (
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Duración</span>
                  <span className="text-sm font-medium">{getDuration()}</span>
                </div>
              )}
              
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Template</span>
                <Button variant="link" size="sm" className="p-0 h-auto" asChild>
                  <Link href={`/${resolvedParams.tenantId}/workflows/${execution.template_id}`}>
                    Ver Template
                  </Link>
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Actions */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Acciones</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <Button variant="outline" className="w-full" onClick={refreshExecution}>
                <IconRefresh className="h-4 w-4 mr-2" />
                Actualizar Estado
              </Button>
              
              {execution.status === 'completed' && (
                <>
                  <Button variant="outline" className="w-full">
                    <IconDownload className="h-4 w-4 mr-2" />
                    Descargar Resultados
                  </Button>
                  <Button variant="outline" className="w-full">
                    <IconUsers className="h-4 w-4 mr-2" />
                    Compartir
                  </Button>
                </>
              )}
            </CardContent>
          </Card>

          {/* Status Alert */}
          {execution.status === 'failed' && (
            <Alert className="border-red-200">
              <IconAlertCircle className="h-4 w-4" />
              <AlertDescription>
                La ejecución ha fallado. Revisa el log para más detalles.
              </AlertDescription>
            </Alert>
          )}

          {execution.status === 'running' && (
            <Alert className="border-blue-200">
              <IconActivity className="h-4 w-4" />
              <AlertDescription>
                El proceso se está ejecutando. Se actualizará automáticamente.
              </AlertDescription>
            </Alert>
          )}
        </div>
      </div>
    </div>
  )
}