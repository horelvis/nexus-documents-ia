"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { useTemporalioService } from "@/lib/services/temporalio.service"
import {
  IconArrowLeft,
  IconRobot,
  IconBrain,
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

import type {
  AIWorkflowTemplateMeta,
  TemporalioExecution,
  TemporalioExecutionStatus
} from "@/lib/services/temporalio.service"

export default function AIAgentsWorkflowsPage() {
  const router = useRouter()
  const temporalioService = useTemporalioService()

  const [templates, setTemplates] = useState<AIWorkflowTemplateMeta[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isExecuting, setIsExecuting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedTemplate, setSelectedTemplate] = useState<AIWorkflowTemplateMeta | null>(null)
  const [execution, setExecution] = useState<TemporalioExecution | null>(null)
  const [executionStatus, setExecutionStatus] = useState<TemporalioExecutionStatus | null>(null)
  const [formValues, setFormValues] = useState<Record<string, string>>({})
  const [inputError, setInputError] = useState<string | null>(null)

  const buildInitialValues = (template: AIWorkflowTemplateMeta | null) => {
    if (!template) {
      return {}
    }
    return template.fields.reduce<Record<string, string>>((acc, field) => {
      acc[field.name] = field.default_value ?? ""
      return acc
    }, {})
  }

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
      const catalog = await temporalioService.getAIWorkflowCatalog()
      setTemplates(catalog)

      const previousId = selectedTemplate?.id
      const nextSelection = catalog.find(t => t.id === previousId) || catalog[0] || null
      setSelectedTemplate(nextSelection || null)

      if (!previousId || nextSelection?.id !== previousId) {
        setFormValues(buildInitialValues(nextSelection || null))
        setInputError(null)
      }
    } catch (err: any) {
      setError(`Error cargando workflows: ${err?.message || err}`)
      setTemplates([])
      setSelectedTemplate(null)
      setFormValues({})
    } finally {
      setIsLoading(false)
    }
  }

  const executeTemplate = async (templateId: string, inputData: Record<string, any>) => {
    setIsExecuting(true)
    setError(null)
    setExecution(null)
    setExecutionStatus(null)

    try {
      const result = await temporalioService.executeAIWorkflow(templateId, inputData)
      setExecution(result)
    } catch (err: any) {
      setError(`Error ejecutando workflow: ${err?.message || err}`)
    } finally {
      setIsExecuting(false)
    }
  }

  const handleExecuteSelectedTemplate = async () => {
    if (!selectedTemplate) {
      setError("Selecciona un workflow para ejecutarlo")
      return
    }

    setInputError(null)
    const missing = selectedTemplate.fields
      .filter(field => field.required !== false)
      .filter(field => {
        const value = formValues[field.name]
        return !value || value.trim() === ""
      })

    if (missing.length > 0) {
      setInputError(`Faltan campos obligatorios: ${missing.map(f => f.label).join(", ")}`)
      return
    }

    await executeTemplate(selectedTemplate.id, formValues)
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
        {templates.map((template) => {
          const isSelected = selectedTemplate?.id === template.id
          return (
            <Card
              key={template.id}
              className={`cursor-pointer transition-all ${
                isSelected ? 'border-purple-500 shadow-lg ring-2 ring-purple-200' : 'hover:shadow-lg'
              }`}
              onClick={() => {
                setSelectedTemplate(template)
                setFormValues(buildInitialValues(template))
                setInputError(null)
              }}
            >
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
          )
        })}
      </div>

      {/* Selected Template */}
      {selectedTemplate ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center">
                <IconBrain className="h-5 w-5 mr-2 text-purple-600" />
                {selectedTemplate.name}
              </CardTitle>
              <CardDescription>
                {selectedTemplate.description || 'Workflow inteligente listo para instanciar'}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="text-sm text-gray-600 space-y-1">
                <p><span className="font-semibold">ID:</span> {selectedTemplate.id}</p>
                <p><span className="font-semibold">Tenant:</span> {selectedTemplate.tenant_id}</p>
                <p><span className="font-semibold">Pasos:</span> {selectedTemplate.workflow_definition?.steps?.length || 0}</p>
              </div>
              <div>
                <Label>Estructura del workflow</Label>
                <pre className="mt-2 max-h-64 overflow-auto rounded border bg-gray-50 p-3 text-xs text-gray-800">
                  {JSON.stringify(selectedTemplate.workflow_definition, null, 2)}
                </pre>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center">
                <IconRobot className="h-5 w-5 mr-2" />
                Instanciar workflow
              </CardTitle>
              <CardDescription>
                Completa los campos requeridos. Enviaremos los valores al backend para generar el payload correcto.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {selectedTemplate.fields.map((field) => {
                const value = formValues[field.name] ?? ""
                const isRequired = field.required !== false

                const renderFieldControl = () => {
                  if (field.type === "textarea") {
                    return (
                      <Textarea
                        value={value}
                        onChange={(e) => {
                          setFormValues(prev => ({ ...prev, [field.name]: e.target.value }))
                          if (inputError) setInputError(null)
                        }}
                        rows={4}
                        placeholder={field.placeholder}
                      />
                    )
                  }

                  if (field.type === "select" && field.options) {
                    return (
                      <Select
                        value={value || field.default_value || ""}
                        onValueChange={(val) => {
                          setFormValues(prev => ({ ...prev, [field.name]: val }))
                          if (inputError) setInputError(null)
                        }}
                      >
                        <SelectTrigger>
                          <SelectValue placeholder={field.placeholder || "Selecciona una opción"} />
                        </SelectTrigger>
                        <SelectContent>
                          {field.options.map(option => (
                            <SelectItem key={option.value} value={option.value}>
                              {option.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )
                  }

                  return (
                    <Input
                      type={field.type === "number" ? "number" : "text"}
                      value={value}
                      placeholder={field.placeholder}
                      onChange={(e) => {
                        setFormValues(prev => ({ ...prev, [field.name]: e.target.value }))
                        if (inputError) setInputError(null)
                      }}
                    />
                  )
                }

                return (
                  <div key={field.name} className="space-y-1">
                    <Label>
                      {field.label}
                      {isRequired && <span className="text-red-500 ml-1">*</span>}
                    </Label>
                    {renderFieldControl()}
                    {field.helper_text && (
                      <p className="text-xs text-gray-500">{field.helper_text}</p>
                    )}
                  </div>
                )
              })}

              {inputError && (
                <p className="text-sm text-red-600">{inputError}</p>
              )}

              <Button
                onClick={handleExecuteSelectedTemplate}
                disabled={isExecuting}
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
                    Ejecutar workflow
                  </>
                )}
              </Button>
            </CardContent>
          </Card>
        </div>
      ) : (
        <div className="text-center py-12 border border-dashed rounded-lg text-gray-500 mb-6">
          Selecciona un workflow AI de la lista para visualizar su detalle y ejecutarlo.
        </div>
      )}

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
