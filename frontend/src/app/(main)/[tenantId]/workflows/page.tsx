"use client"

import { useState, useEffect, use } from "react"
import { useWorkflowsService } from "@/lib/services/workflows.service"
import Link from "next/link"
import { 
  IconGitBranch, 
  IconRobot, 
  IconTrendingUp, 
  IconBook,
  IconPlus,
  IconUsers,
  IconClockPlay,
  IconCircleCheck,
} from "@tabler/icons-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"

import { WorkflowStats, RecentProcess, ProcessTemplate } from "@/lib/services/workflows.service"

export default function WorkflowsPage({ params }: { params: Promise<{ tenantId: string }> }) {
  const resolvedParams = use(params)
  const workflowsService = useWorkflowsService()
  const [isLoading, setIsLoading] = useState(true)
  const [stats, setStats] = useState<WorkflowStats | null>(null)
  const [recentProcesses, setRecentProcesses] = useState<RecentProcess[]>([])
  const [processTemplates, setProcessTemplates] = useState<ProcessTemplate[]>([])

  const loadData = async () => {
    setIsLoading(true)
    try {
      const [statsData, processesData, templatesData] = await Promise.all([
        workflowsService.getWorkflowStats(),
        workflowsService.getRecentProcesses(),
        workflowsService.getProcessTemplates()
      ])
      
      setStats(statsData)
      setRecentProcesses(processesData)
      setProcessTemplates(templatesData.slice(0, 3)) // Show only first 3 templates
    } catch (error) {
      console.error('Error loading workflow data:', error)
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  const getStatusColor = (status: string) => {
    switch (status) {
      case "completed": return "text-green-600 bg-green-100"
      case "in_progress": return "text-blue-600 bg-blue-100"
      case "pending_review": return "text-yellow-600 bg-yellow-100"
      default: return "text-gray-600 bg-gray-100"
    }
  }

  const getStatusText = (status: string) => {
    switch (status) {
      case "completed": return "Completado"
      case "in_progress": return "En Proceso"
      case "pending_review": return "Pendiente Revisión"
      default: return "Desconocido"
    }
  }

  return (
    <div className="container mx-auto px-4 py-8 space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
            <IconGitBranch className="h-8 w-8 text-cyan-600" />
            WorkFlow AI
          </h1>
          <p className="text-muted-foreground mt-1">
            Automatiza y optimiza tus procesos laborales con IA especializada
          </p>
        </div>
        <div className="flex gap-3">
          <Button asChild variant="outline">
            <Link href={`/${resolvedParams.tenantId}/workflows/library`}>
              <IconBook className="h-4 w-4 mr-2" />
              Ver Plantillas
            </Link>
          </Button>
          <Button asChild>
            <Link href={`/${resolvedParams.tenantId}/workflows/builder`}>
              <IconPlus className="h-4 w-4 mr-2" />
              Crear Proceso
            </Link>
          </Button>
        </div>
      </div>

      {/* Stats Cards */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          {[1, 2, 3, 4].map((i) => (
            <Card key={i}>
              <CardContent className="p-6">
                <div className="animate-pulse space-y-2">
                  <div className="h-4 bg-gray-200 rounded"></div>
                  <div className="h-8 bg-gray-200 rounded"></div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Procesos Totales</CardTitle>
              <IconGitBranch className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
            <div className="text-2xl font-bold">{stats?.totalProcesses ?? 0}</div>
            <p className="text-xs text-muted-foreground">
              Configurados en el sistema
            </p>
          </CardContent>
        </Card>
        
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Procesos Activos</CardTitle>
            <IconClockPlay className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-blue-600">{stats?.activeProcesses ?? 0}</div>
            <p className="text-xs text-muted-foreground">
              En ejecución ahora
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Completados Hoy</CardTitle>
            <IconCircleCheck className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-600">{stats?.completedToday ?? 0}</div>
            <p className="text-xs text-muted-foreground">
              Procesos finalizados
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Tiempo Promedio</CardTitle>
            <IconTrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-purple-600">{stats?.avgCompletionTime ?? '-- días'}</div>
            <p className="text-xs text-muted-foreground">
              Tiempo de completación
            </p>
          </CardContent>
        </Card>
        </div>
      )}

      {/* Recent Processes */}
      <Card>
        <CardHeader>
          <CardTitle>Procesos Recientes</CardTitle>
          <CardDescription>
            Últimos procesos ejecutados en tu organización
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {isLoading ? (
              <div className="space-y-4">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="p-4 border rounded-lg">
                    <div className="animate-pulse space-y-2">
                      <div className="h-4 bg-gray-200 rounded w-3/4"></div>
                      <div className="h-3 bg-gray-200 rounded w-1/2"></div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <>
                {recentProcesses.map((process) => (
                  <div key={process.id} className="flex items-center justify-between p-4 border rounded-lg">
                    <div className="flex items-center space-x-4">
                      <div className="w-2 h-2 rounded-full bg-cyan-500" />
                      <div>
                        <p className="font-medium">{process.name}</p>
                        <div className="flex items-center gap-2 mt-1">
                          <Badge variant="secondary" className="text-xs">
                            {process.type}
                          </Badge>
                          <Badge className={`text-xs ${getStatusColor(process.status)}`}>
                            {getStatusText(process.status)}
                          </Badge>
                        </div>
                        {process.currentStep && (
                          <p className="text-sm text-muted-foreground mt-1">
                            {process.currentStep} ({process.progress}%)
                          </p>
                        )}
                      </div>
                    </div>
                    <div className="text-right">
                      {process.completedAt && (
                        <p className="text-sm text-muted-foreground">{process.completedAt}</p>
                      )}
                      {process.decision && (
                        <Badge className="bg-green-100 text-green-800">
                          {process.decision}
                        </Badge>
                      )}
                    </div>
                  </div>
                ))}
              </>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Process Templates */}
      <Card>
        <CardHeader>
          <CardTitle>Plantillas de Proceso</CardTitle>
          <CardDescription>
            Plantillas predefinidas para procesos laborales comunes
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {isLoading ? (
              <>  
                {[1, 2, 3].map((i) => (
                  <div key={i} className="border rounded-lg p-4">
                    <div className="animate-pulse space-y-3">
                      <div className="flex justify-between">
                        <div className="h-10 w-10 bg-gray-200 rounded-lg"></div>
                        <div className="h-6 w-16 bg-gray-200 rounded"></div>
                      </div>
                      <div className="h-5 bg-gray-200 rounded"></div>
                      <div className="h-12 bg-gray-200 rounded"></div>
                      <div className="h-8 bg-gray-200 rounded"></div>
                    </div>
                  </div>
                ))}
              </>
            ) : (
              <>
                {processTemplates.map((template) => {
                  const IconComponent = template.id === 'contract_renewal' ? IconUsers :
                                       template.id === 'contract_termination' ? IconClockPlay :
                                       IconCircleCheck
                  const color = template.id === 'contract_renewal' ? 'bg-blue-500' :
                               template.id === 'contract_termination' ? 'bg-red-500' :
                               'bg-green-500'
                  
                  return (
                    <div key={template.id} className="border rounded-lg p-4 hover:bg-accent transition-colors cursor-pointer">
                      <div className="flex items-start justify-between mb-3">
                        <div className={`w-10 h-10 rounded-lg ${color} flex items-center justify-center`}>
                          <IconComponent className="h-5 w-5 text-white" />
                        </div>
                        <Badge variant="secondary">{template.usage} usos</Badge>
                      </div>
                      
                      <h3 className="font-semibold mb-2">{template.name}</h3>
                      <p className="text-sm text-muted-foreground mb-4">
                        {template.description}
                      </p>
                      
                      <div className="flex items-center justify-between text-xs text-muted-foreground">
                        <span>⏱️ {template.estimatedTime}</span>
                        <span>📋 {template.steps} pasos</span>
                      </div>
                      
                      <Button 
                        size="sm" 
                        className="w-full mt-3"
                        asChild
                      >
                        <Link href={`/${resolvedParams.tenantId}/workflows/${template.id}`}>
                          Usar Plantilla
                        </Link>
                      </Button>
                    </div>
                  )
                })}
              </>
            )}
          </div>
        </CardContent>
      </Card>

      {/* CTA */}
      <Card className="bg-gradient-to-r from-cyan-50 to-blue-50 border-cyan-200">
        <CardContent className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-semibold mb-2">¿Necesitas un proceso personalizado?</h3>
              <p className="text-muted-foreground">
                Crea workflows específicos para tu organización usando nuestro Process Builder con IA
              </p>
            </div>
            <Button asChild size="lg" className="bg-cyan-600 hover:bg-cyan-700">
              <Link href={`/${resolvedParams.tenantId}/workflows/builder`}>
                <IconRobot className="h-4 w-4 mr-2" />
                Crear con IA
              </Link>
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}