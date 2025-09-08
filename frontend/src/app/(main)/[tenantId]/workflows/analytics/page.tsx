"use client"

import { useState, use } from "react"
import { 
  IconChartBar, 
  IconTrendingUp,
  IconUsers,
  IconClockPlay,
  IconCircleCheck,
  IconAlertTriangle,
  IconCalendar,
  IconDownload,
  IconEye,
  IconRefresh
} from "@tabler/icons-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Progress } from "@/components/ui/progress"
import { Alert, AlertDescription } from "@/components/ui/alert"

export default function WorkflowAnalyticsPage({ params }: { params: Promise<{ tenantId: string }> }) {
  const resolvedParams = use(params)
  const [timeRange, setTimeRange] = useState("last_30_days")
  const [selectedProcess, setSelectedProcess] = useState("all")

  const kpiData = {
    totalProcesses: 156,
    activeProcesses: 23,
    completedProcesses: 133,
    avgCompletionTime: "8.5 días",
    successRate: 94.2,
    costSavings: "€12,450"
  }

  const processMetrics = [
    {
      name: "Renovación de Contratos",
      executions: 45,
      avgTime: "12.3 días",
      successRate: 89,
      trend: "+5%",
      status: "healthy"
    },
    {
      name: "Onboarding Empleados", 
      executions: 32,
      avgTime: "6.8 días",
      successRate: 97,
      trend: "+12%",
      status: "excellent"
    },
    {
      name: "Solicitudes Permisos",
      executions: 89,
      avgTime: "2.1 días", 
      successRate: 98,
      trend: "+3%",
      status: "excellent"
    },
    {
      name: "Evaluaciones Desempeño",
      executions: 18,
      avgTime: "21.5 días",
      successRate: 83,
      trend: "-8%",
      status: "attention"
    }
  ]

  const bottlenecks = [
    {
      process: "Renovación de Contratos",
      step: "Evaluación Manager",
      avgDelay: "3.2 días",
      frequency: "78%",
      impact: "high"
    },
    {
      process: "Evaluaciones Desempeño",
      step: "Feedback 360°",
      avgDelay: "5.1 días", 
      frequency: "65%",
      impact: "medium"
    },
    {
      process: "Proceso Disciplinario",
      step: "Revisión Legal",
      avgDelay: "7.8 días",
      frequency: "45%",
      impact: "high"
    }
  ]

  const getStatusColor = (status: string) => {
    switch (status) {
      case "excellent": return "text-green-600 bg-green-100"
      case "healthy": return "text-blue-600 bg-blue-100"
      case "attention": return "text-yellow-600 bg-yellow-100"
      case "critical": return "text-red-600 bg-red-100"
      default: return "text-gray-600 bg-gray-100"
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "excellent": return <IconCircleCheck className="h-4 w-4" />
      case "healthy": return <IconTrendingUp className="h-4 w-4" />
      case "attention": return <IconAlertTriangle className="h-4 w-4" />
      case "critical": return <IconAlertTriangle className="h-4 w-4" />
      default: return <IconClockPlay className="h-4 w-4" />
    }
  }

  const getImpactColor = (impact: string) => {
    switch (impact) {
      case "high": return "text-red-600"
      case "medium": return "text-yellow-600"
      case "low": return "text-green-600"
      default: return "text-gray-600"
    }
  }

  return (
    <div className="container mx-auto px-4 py-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
            <IconChartBar className="h-8 w-8 text-purple-600" />
            Analytics de Workflows
          </h1>
          <p className="text-muted-foreground mt-1">
            Métricas y análisis de rendimiento de tus procesos automatizados
          </p>
        </div>
        <div className="flex gap-3">
          <Select value={timeRange} onValueChange={setTimeRange}>
            <SelectTrigger className="w-[180px]">
              <IconCalendar className="h-4 w-4 mr-2" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="last_7_days">Últimos 7 días</SelectItem>
              <SelectItem value="last_30_days">Últimos 30 días</SelectItem>
              <SelectItem value="last_90_days">Últimos 90 días</SelectItem>
              <SelectItem value="last_year">Último año</SelectItem>
            </SelectContent>
          </Select>
          
          <Button variant="outline">
            <IconDownload className="h-4 w-4 mr-2" />
            Exportar
          </Button>
          
          <Button>
            <IconRefresh className="h-4 w-4 mr-2" />
            Actualizar
          </Button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Procesos Totales</CardTitle>
            <IconChartBar className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{kpiData.totalProcesses}</div>
            <p className="text-xs text-green-600">+8% vs mes anterior</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">En Progreso</CardTitle>
            <IconClockPlay className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-blue-600">{kpiData.activeProcesses}</div>
            <p className="text-xs text-muted-foreground">Procesos activos</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Completados</CardTitle>
            <IconCircleCheck className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-600">{kpiData.completedProcesses}</div>
            <p className="text-xs text-green-600">+15% vs mes anterior</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Tiempo Promedio</CardTitle>
            <IconTrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-purple-600">{kpiData.avgCompletionTime}</div>
            <p className="text-xs text-green-600">-12% vs mes anterior</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Tasa de Éxito</CardTitle>
            <IconCircleCheck className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-600">{kpiData.successRate}%</div>
            <p className="text-xs text-green-600">+2.1% vs mes anterior</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Ahorro Costos</CardTitle>
            <IconTrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-600">{kpiData.costSavings}</div>
            <p className="text-xs text-green-600">Por automatización</p>
          </CardContent>
        </Card>
      </div>

      {/* Process Performance */}
      <Card>
        <CardHeader>
          <CardTitle>Rendimiento por Proceso</CardTitle>
          <CardDescription>
            Métricas detalladas de cada tipo de proceso en el período seleccionado
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {processMetrics.map((process, index) => (
              <div key={index} className="flex items-center justify-between p-4 border rounded-lg">
                <div className="flex items-center space-x-4">
                  <div className="flex items-center gap-2">
                    {getStatusIcon(process.status)}
                    <div>
                      <p className="font-medium">{process.name}</p>
                      <div className="flex items-center gap-4 mt-1 text-sm text-muted-foreground">
                        <span>{process.executions} ejecuciones</span>
                        <span>⏱️ {process.avgTime}</span>
                        <span>✅ {process.successRate}%</span>
                      </div>
                    </div>
                  </div>
                </div>
                
                <div className="flex items-center space-x-4">
                  <Badge className={getStatusColor(process.status)}>
                    {process.status === "excellent" ? "Excelente" :
                     process.status === "healthy" ? "Saludable" :
                     process.status === "attention" ? "Atención" : "Crítico"}
                  </Badge>
                  
                  <div className="text-right">
                    <div className={`text-sm font-medium ${
                      process.trend.startsWith('+') ? 'text-green-600' : 'text-red-600'
                    }`}>
                      {process.trend}
                    </div>
                    <div className="text-xs text-muted-foreground">vs período anterior</div>
                  </div>
                  
                  <Button size="sm" variant="ghost">
                    <IconEye className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Bottlenecks */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <IconAlertTriangle className="h-5 w-5 text-yellow-600" />
            Cuellos de Botella Identificados
          </CardTitle>
          <CardDescription>
            Pasos que están causando retrasos en tus procesos
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {bottlenecks.map((bottleneck, index) => (
              <div key={index} className="flex items-center justify-between p-4 border rounded-lg">
                <div className="flex items-center space-x-4">
                  <div className={`w-3 h-3 rounded-full ${getImpactColor(bottleneck.impact).replace('text-', 'bg-')}`} />
                  <div>
                    <p className="font-medium">{bottleneck.process}</p>
                    <p className="text-sm text-muted-foreground">Paso: {bottleneck.step}</p>
                  </div>
                </div>
                
                <div className="flex items-center space-x-6 text-sm">
                  <div className="text-center">
                    <div className="font-medium text-red-600">{bottleneck.avgDelay}</div>
                    <div className="text-muted-foreground">Retraso promedio</div>
                  </div>
                  
                  <div className="text-center">
                    <div className="font-medium">{bottleneck.frequency}</div>
                    <div className="text-muted-foreground">Frecuencia</div>
                  </div>
                  
                  <Badge className={`${getImpactColor(bottleneck.impact)} bg-transparent`}>
                    {bottleneck.impact === "high" ? "Alto Impacto" :
                     bottleneck.impact === "medium" ? "Medio Impacto" : "Bajo Impacto"}
                  </Badge>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Process Efficiency Trends */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Tendencias de Eficiencia</CardTitle>
            <CardDescription>Evolución de métricas clave en el tiempo</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div>
                <div className="flex justify-between items-center mb-2">
                  <span className="text-sm">Tiempo Medio de Completación</span>
                  <span className="text-sm text-green-600">-12%</span>
                </div>
                <Progress value={75} className="h-2" />
              </div>
              
              <div>
                <div className="flex justify-between items-center mb-2">
                  <span className="text-sm">Tasa de Automatización</span>
                  <span className="text-sm text-green-600">+18%</span>
                </div>
                <Progress value={82} className="h-2" />
              </div>
              
              <div>
                <div className="flex justify-between items-center mb-2">
                  <span className="text-sm">Satisfacción Usuario</span>
                  <span className="text-sm text-green-600">+5%</span>
                </div>
                <Progress value={91} className="h-2" />
              </div>
              
              <div>
                <div className="flex justify-between items-center mb-2">
                  <span className="text-sm">Cumplimiento Legal</span>
                  <span className="text-sm text-green-600">+3%</span>
                </div>
                <Progress value={96} className="h-2" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Insights de IA</CardTitle>
            <CardDescription>Recomendaciones basadas en análisis de datos</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Alert>
              <IconTrendingUp className="h-4 w-4" />
              <AlertDescription>
                <strong>Optimización detectada:</strong> El proceso de "Evaluación de Desempeño" 
                podría reducir 30% el tiempo implementando recordatorios automáticos.
              </AlertDescription>
            </Alert>
            
            <Alert>
              <IconUsers className="h-4 w-4" />
              <AlertDescription>
                <strong>Patrón identificado:</strong> Los procesos iniciados los lunes 
                tienen 15% mayor probabilidad de completarse a tiempo.
              </AlertDescription>
            </Alert>
            
            <Alert>
              <IconCircleCheck className="h-4 w-4" />
              <AlertDescription>
                <strong>Éxito notable:</strong> La automatización de "Solicitudes de Permisos" 
                ha reducido el tiempo de gestión en 68%.
              </AlertDescription>
            </Alert>
          </CardContent>
        </Card>
      </div>

      {/* Enterprise Features CTA */}
      <Card className="bg-gradient-to-r from-purple-50 to-blue-50 border-purple-200">
        <CardContent className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-semibold mb-2">Desbloquea Analytics Avanzados</h3>
              <p className="text-muted-foreground">
                Obtén insights más profundos con análisis predictivo, machine learning 
                y reportes personalizables en WorkIA Enterprise.
              </p>
            </div>
            <Button size="lg" className="bg-purple-600 hover:bg-purple-700">
              <IconTrendingUp className="h-4 w-4 mr-2" />
              Upgrade a Enterprise
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}