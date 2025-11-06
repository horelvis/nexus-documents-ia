"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { useParams } from "next/navigation"
import { useTemporalioService } from "@/lib/services/temporalio.service"
import { 
  IconArrowLeft, 
  IconRobot,
  IconBrain,
  IconFileText,
  IconUsers,
  IconClock,
  IconCheck,
  IconAlertTriangle,
  IconPlayerPlay,
  IconRefresh
} from "@tabler/icons-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Alert, AlertDescription } from "@/components/ui/alert"

import type { TemporalioTemplate, TemporalioExecution, TemporalioExecutionStatus } from "@/lib/services/temporalio.service"

export default function AIAgentsWorkflowsPage() {
  const router = useRouter()
  const params = useParams()
  const tenantId = params.tenantId as string
  const temporalioService = useTemporalioService()

  const [templates, setTemplates] = useState<TemporalioTemplate[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isExecuting, setIsExecuting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedTemplate, setSelectedTemplate] = useState<TemporalioTemplate | null>(null)
  const [execution, setExecution] = useState<TemporalioExecution | null>(null)
  const [executionStatus, setExecutionStatus] = useState<TemporalioExecutionStatus | null>(null)

  // Form data for legal advisory workflow
  const [legalForm, setLegalForm] = useState({
    clientName: '',
    caseType: 'Laboral',
    description: '',
    priority: 'medium'
  })

  // Form data for document processing workflow  
  const [documentForm, setDocumentForm] = useState({
    documentContent: '',
    documentType: 'contract',
    analysisDepth: 'standard'
  })

  useEffect(() => {
    loadTemplates()
  }, [])

  useEffect(() => {
    if (execution) {
      // Poll execution status
      const interval = setInterval(async () => {
        try {
          const status = await temporalioService.getExecutionStatus(execution.workflow_id)
          setExecutionStatus(status)
          
          if (status.status === 'completed' || status.status === 'failed') {
            clearInterval(interval)
          }
        } catch (error) {
          console.error('Error polling execution status:', error)
        }
      }, 2000)

      return () => clearInterval(interval)
    }
  }, [execution])

  const loadTemplates = async () => {
    setIsLoading(true)
    setError(null)

    try {
      const allTemplates = await temporalioService.getTemplates()
      // Filter for AI-enhanced templates
      const aiTemplates = allTemplates.filter(t => 
        t.name.toLowerCase().includes('inteligente') || 
        t.name.toLowerCase().includes('ai') ||
        t.id.includes('ai-')
      )
      setTemplates(aiTemplates)
    } catch (err) {
      setError(`Error loading templates: ${err.message}`)
    } finally {
      setIsLoading(false)
    }
  }

  const executeTemplate = async (templateId: string, inputData: any) => {
    setIsExecuting(true)
    setError(null)
    setExecution(null)
    setExecutionStatus(null)

    try {
      const result = await temporalioService.executeWorkflow(templateId, tenantId, inputData)
      setExecution(result)
    } catch (err) {
      setError(`Error executing workflow: ${err.message}`)
    } finally {
      setIsExecuting(false)
    }
  }

  const executeLegalAdvisory = async () => {
    await executeTemplate('ai-legal-advisory-template', legalForm)
  }

  const executeDocumentProcessing = async () => {
    await executeTemplate('ai-document-processing-template', documentForm)
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'running': return 'bg-blue-500'
      case 'completed': return 'bg-green-500'
      case 'failed': return 'bg-red-500'
      case 'cancelled': return 'bg-gray-500'
      default: return 'bg-yellow-500'
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'running': return <IconClock className="h-4 w-4" />
      case 'completed': return <IconCheck className="h-4 w-4" />
      case 'failed': return <IconAlertTriangle className="h-4 w-4" />
      default: return <IconClock className="h-4 w-4" />
    }
  }

  if (isLoading) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="flex items-center justify-center min-h-96">
          <div className="flex items-center space-x-2">
            <IconRefresh className="h-6 w-6 animate-spin" />
            <span>Cargando workflows con agentes AI...</span>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center space-x-4">
          <Button variant="ghost" onClick={() => router.back()}>
            <IconArrowLeft className="h-4 w-4 mr-2" />
            Volver
          </Button>
          <div>
            <h1 className="text-2xl font-bold flex items-center">
              <IconRobot className="h-6 w-6 mr-2 text-purple-600" />
              Workflows con Agentes AI
            </h1>
            <p className="text-gray-600">
              Workflows inteligentes potenciados por Emma AI y agentes especializados
            </p>
          </div>
        </div>
        <Button onClick={loadTemplates} variant="outline">
          <IconRefresh className="h-4 w-4 mr-2" />
          Actualizar
        </Button>
      </div>

      {/* Error Display */}
      {error && (
        <Alert className="mb-6 border-red-200 bg-red-50">
          <IconAlertTriangle className="h-4 w-4" />
          <AlertDescription className="text-red-800">
            {error}
          </AlertDescription>
        </Alert>
      )}

      {/* Templates Overview */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
        {templates.map((template) => (
          <Card key={template.id} className="hover:shadow-lg transition-shadow">
            <CardHeader>
              <CardTitle className="flex items-center text-lg">
                <IconBrain className="h-5 w-5 mr-2 text-purple-600" />
                {template.name}
              </CardTitle>
              <CardDescription>{template.description}</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-gray-600">Complejidad:</span>
                  <Badge variant={template.complexity_level === 'advanced' ? 'default' : 'secondary'}>
                    {template.complexity_level || 'Medium'}
                  </Badge>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-gray-600">Duración:</span>
                  <span>{template.estimated_duration || '15-45 min'}</span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-gray-600">Pasos:</span>
                  <span>{template.workflow_definition?.steps?.length || 0}</span>
                </div>
                {template.agent_types_used && template.agent_types_used.length > 0 && (
                  <div className="mt-3">
                    <span className="text-xs text-gray-600 block mb-1">Agentes AI utilizados:</span>
                    <div className="flex flex-wrap gap-1">
                      {template.agent_types_used.slice(0, 2).map((agent, idx) => (
                        <Badge key={idx} variant="outline" className="text-xs">
                          {agent.replace('_', ' ').replace('agent', '').trim()}
                        </Badge>
                      ))}
                      {template.agent_types_used.length > 2 && (
                        <Badge variant="outline" className="text-xs">
                          +{template.agent_types_used.length - 2}
                        </Badge>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Execution Forms */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Legal Advisory Form */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center">
              <IconUsers className="h-5 w-5 mr-2" />
              Asesoría Legal Inteligente
            </CardTitle>
            <CardDescription>
              Ejecutar consulta legal con análisis AI multi-agente
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <Label htmlFor="clientName">Nombre del Cliente</Label>
              <Input
                id="clientName"
                value={legalForm.clientName}
                onChange={(e) => setLegalForm({...legalForm, clientName: e.target.value})}
                placeholder="Ej: María García"
              />
            </div>
            <div>
              <Label htmlFor="caseType">Tipo de Caso</Label>
              <Select value={legalForm.caseType} onValueChange={(value) => setLegalForm({...legalForm, caseType: value})}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Laboral">Laboral</SelectItem>
                  <SelectItem value="Civil">Civil</SelectItem>
                  <SelectItem value="Penal">Penal</SelectItem>
                  <SelectItem value="Comercial">Comercial</SelectItem>
                  <SelectItem value="Familiar">Familiar</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="priority">Prioridad</Label>
              <Select value={legalForm.priority} onValueChange={(value) => setLegalForm({...legalForm, priority: value})}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="low">Baja</SelectItem>
                  <SelectItem value="medium">Media</SelectItem>
                  <SelectItem value="high">Alta</SelectItem>
                  <SelectItem value="urgent">Urgente</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="description">Descripción del Caso</Label>
              <Textarea
                id="description"
                value={legalForm.description}
                onChange={(e) => setLegalForm({...legalForm, description: e.target.value})}
                placeholder="Describe detalladamente el caso legal..."
                rows={4}
              />
            </div>
            <Button 
              onClick={executeLegalAdvisory} 
              disabled={isExecuting || !legalForm.clientName || !legalForm.description}
              className="w-full"
            >
              {isExecuting ? (
                <>
                  <IconRefresh className="h-4 w-4 mr-2 animate-spin" />
                  Ejecutando...
                </>
              ) : (
                <>
                  <IconPlayerPlay className="h-4 w-4 mr-2" />
                  Ejecutar Asesoría Legal
                </>
              )}
            </Button>
          </CardContent>
        </Card>

        {/* Document Processing Form */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center">
              <IconFileText className="h-5 w-5 mr-2" />
              Procesamiento Inteligente de Documentos
            </CardTitle>
            <CardDescription>
              Analizar documentos con agentes AI especializados
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <Label htmlFor="documentType">Tipo de Documento</Label>
              <Select value={documentForm.documentType} onValueChange={(value) => setDocumentForm({...documentForm, documentType: value})}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="contract">Contrato</SelectItem>
                  <SelectItem value="legal_brief">Documento Legal</SelectItem>
                  <SelectItem value="report">Informe</SelectItem>
                  <SelectItem value="correspondence">Correspondencia</SelectItem>
                  <SelectItem value="other">Otro</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="analysisDepth">Profundidad del Análisis</Label>
              <Select value={documentForm.analysisDepth} onValueChange={(value) => setDocumentForm({...documentForm, analysisDepth: value})}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="basic">Básico</SelectItem>
                  <SelectItem value="standard">Estándar</SelectItem>
                  <SelectItem value="deep">Profundo</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="documentContent">Contenido del Documento</Label>
              <Textarea
                id="documentContent"
                value={documentForm.documentContent}
                onChange={(e) => setDocumentForm({...documentForm, documentContent: e.target.value})}
                placeholder="Pega aquí el contenido del documento a analizar..."
                rows={6}
              />
            </div>
            <Button 
              onClick={executeDocumentProcessing} 
              disabled={isExecuting || !documentForm.documentContent}
              className="w-full"
            >
              {isExecuting ? (
                <>
                  <IconRefresh className="h-4 w-4 mr-2 animate-spin" />
                  Procesando...
                </>
              ) : (
                <>
                  <IconPlayerPlay className="h-4 w-4 mr-2" />
                  Procesar Documento
                </>
              )}
            </Button>
          </CardContent>
        </Card>
      </div>

      {/* Execution Status */}
      {execution && (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle className="flex items-center">
              <IconRobot className="h-5 w-5 mr-2" />
              Estado de Ejecución del Workflow
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="font-medium">Workflow ID:</span>
                <code className="text-sm bg-gray-100 px-2 py-1 rounded">{execution.workflow_id}</code>
              </div>
              <div className="flex items-center justify-between">
                <span className="font-medium">Template:</span>
                <span>{execution.template_id}</span>
              </div>
              {executionStatus && (
                <>
                  <div className="flex items-center justify-between">
                    <span className="font-medium">Estado:</span>
                    <div className="flex items-center space-x-2">
                      {getStatusIcon(executionStatus.status)}
                      <Badge className={`text-white ${getStatusColor(executionStatus.status)}`}>
                        {executionStatus.status.toUpperCase()}
                      </Badge>
                    </div>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="font-medium">Iniciado:</span>
                    <span className="text-sm text-gray-600">
                      {new Date(executionStatus.created_at).toLocaleString()}
                    </span>
                  </div>
                  {executionStatus.completed_at && (
                    <div className="flex items-center justify-between">
                      <span className="font-medium">Completado:</span>
                      <span className="text-sm text-gray-600">
                        {new Date(executionStatus.completed_at).toLocaleString()}
                      </span>
                    </div>
                  )}
                  {executionStatus.error && (
                    <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded">
                      <p className="text-red-800 text-sm">{executionStatus.error}</p>
                    </div>
                  )}
                  {executionStatus.result && (
                    <div className="mt-4 p-3 bg-green-50 border border-green-200 rounded">
                      <h4 className="font-medium text-green-800 mb-2">Resultado del Workflow:</h4>
                      <pre className="text-sm text-green-700 whitespace-pre-wrap">
                        {JSON.stringify(executionStatus.result, null, 2)}
                      </pre>
                    </div>
                  )}
                </>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {templates.length === 0 && !isLoading && (
        <div className="text-center py-12">
          <IconRobot className="h-16 w-16 mx-auto text-gray-400 mb-4" />
          <h3 className="text-lg font-semibold text-gray-600 mb-2">
            No hay workflows AI disponibles
          </h3>
          <p className="text-gray-500">
            Los workflows con agentes AI no están disponibles en este momento.
          </p>
        </div>
      )}
    </div>
  )
}