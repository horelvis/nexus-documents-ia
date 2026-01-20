"use client"

import { useState, useEffect, use } from "react"
import { useRouter } from "next/navigation"
import { useWorkflowsService } from "@/lib/services/workflows.service"
import { 
  IconArrowLeft, 
  IconPlayerPlay, 
  IconUsers, 
  IconClock,
  IconSettings,
  IconRobot,
  IconFileText,
  IconAlertTriangle,
  IconCheck
} from "@tabler/icons-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import Link from "next/link"

interface WorkflowTemplate {
  id: string
  name: string
  description: string
  category: string
  workflow_definition: {
    steps: Array<{
      step_id: string
      step_name: string
      step_type: string
      description: string
    }>
  }
  input_schema: {
    fields: Array<{
      field_name: string
      field_type: string
      label: string
      required: boolean
      description?: string
      options?: string[]
    }>
  }
  estimated_duration_days: number
  tags: string[]
  complexity: string
}

export default function WorkflowTemplatePage({ params }: { params: Promise<{ tenantId: string, templateId: string }> }) {
  const resolvedParams = use(params)
  const router = useRouter()
  const workflowsService = useWorkflowsService()
  
  const [isLoading, setIsLoading] = useState(true)
  const [template, setTemplate] = useState<WorkflowTemplate | null>(null)
  const [formData, setFormData] = useState<Record<string, any>>({})
  const [isExecuting, setIsExecuting] = useState(false)

  const loadTemplate = async () => {
    setIsLoading(true)
    try {
      const templates = await workflowsService.getWorkflowTemplates()
      const found = templates.find(t => t.id === resolvedParams.templateId)
      
      if (!found) {
        router.push(`/${resolvedParams.tenantId}/workflows`)
        return
      }
      
      // Get full template details (this would be a separate API call in real implementation)
      setTemplate(found as any) // Type assertion for now
      
      // Initialize form data with empty values
      const initialData: Record<string, any> = {}
      found.input_schema?.fields?.forEach(field => {
        initialData[field.field_name] = ''
      })
      setFormData(initialData)
      
    } catch (error) {
      console.error('Error loading template:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const executeWorkflow = async () => {
    if (!template) return
    
    setIsExecuting(true)
    try {
      const result = await workflowsService.executeWorkflowTemplate(template.id, formData)
      
      // Redirect to execution monitoring page
      router.push(`/${resolvedParams.tenantId}/workflows/executions/${result.id}`)
    } catch (error) {
      console.error('Error executing workflow:', error)
    } finally {
      setIsExecuting(false)
    }
  }

  const handleInputChange = (fieldName: string, value: any) => {
    setFormData(prev => ({
      ...prev,
      [fieldName]: value
    }))
  }

  const isFormValid = () => {
    if (!template) return false
    
    const requiredFields = template.input_schema?.fields?.filter(f => f.required) || []
    return requiredFields.every(field => formData[field.field_name]?.toString().trim())
  }

  useEffect(() => {
    loadTemplate()
  }, [resolvedParams.templateId])

  if (isLoading) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="animate-pulse space-y-6">
          <div className="h-8 bg-gray-200 rounded w-1/3"></div>
          <div className="h-64 bg-gray-200 rounded"></div>
          <div className="h-32 bg-gray-200 rounded"></div>
        </div>
      </div>
    )
  }

  if (!template) {
    return (
      <div className="container mx-auto px-4 py-8">
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <IconAlertTriangle className="h-16 w-16 text-red-300 mb-4" />
            <p className="text-red-500 mb-2">Template no encontrado</p>
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

  const getComplexityColor = (complexity: string) => {
    switch (complexity) {
      case "simple": return "text-green-600 bg-green-100"
      case "intermediate": return "text-yellow-600 bg-yellow-100"
      case "advanced": return "text-red-600 bg-red-100"
      default: return "text-gray-600 bg-gray-100"
    }
  }

  const renderFormField = (field: any) => {
    const { field_name, field_type, label, required, description, options } = field
    
    switch (field_type) {
      case 'select':
        return (
          <div key={field_name} className="space-y-2">
            <Label htmlFor={field_name}>
              {label} {required && <span className="text-red-500">*</span>}
            </Label>
            <Select 
              value={formData[field_name]} 
              onValueChange={(value) => handleInputChange(field_name, value)}
            >
              <SelectTrigger>
                <SelectValue placeholder={`Seleccionar ${label.toLowerCase()}`} />
              </SelectTrigger>
              <SelectContent>
                {options?.map((option: string) => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {description && (
              <p className="text-sm text-muted-foreground">{description}</p>
            )}
          </div>
        )
      
      case 'textarea':
        return (
          <div key={field_name} className="space-y-2">
            <Label htmlFor={field_name}>
              {label} {required && <span className="text-red-500">*</span>}
            </Label>
            <Textarea 
              id={field_name}
              placeholder={description || `Ingresa ${label.toLowerCase()}`}
              value={formData[field_name]}
              onChange={(e) => handleInputChange(field_name, e.target.value)}
              rows={4}
            />
            {description && (
              <p className="text-sm text-muted-foreground">{description}</p>
            )}
          </div>
        )
      
      default:
        return (
          <div key={field_name} className="space-y-2">
            <Label htmlFor={field_name}>
              {label} {required && <span className="text-red-500">*</span>}
            </Label>
            <Input 
              id={field_name}
              type={field_type === 'number' ? 'number' : 'text'}
              placeholder={description || `Ingresa ${label.toLowerCase()}`}
              value={formData[field_name]}
              onChange={(e) => handleInputChange(field_name, e.target.value)}
            />
            {description && (
              <p className="text-sm text-muted-foreground">{description}</p>
            )}
          </div>
        )
    }
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
          <h1 className="text-3xl font-bold tracking-tight">{template.name}</h1>
          <p className="text-muted-foreground mt-1">{template.description}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Form */}
        <div className="lg:col-span-2 space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Configuración del Proceso</CardTitle>
              <CardDescription>
                Completa la información requerida para ejecutar este workflow
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {template.input_schema?.fields?.map(field => renderFormField(field))}
            </CardContent>
          </Card>

          {/* Execute Button */}
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-semibold mb-1">¿Listo para ejecutar?</h3>
                  <p className="text-sm text-muted-foreground">
                    El proceso se ejecutará automáticamente con Emma AI
                  </p>
                </div>
                <Button 
                  size="lg" 
                  onClick={executeWorkflow}
                  disabled={!isFormValid() || isExecuting}
                  className="min-w-32"
                >
                  {isExecuting ? (
                    <>
                      <IconSettings className="h-4 w-4 mr-2 animate-spin" />
                      Ejecutando...
                    </>
                  ) : (
                    <>
                      <IconPlayerPlay className="h-4 w-4 mr-2" />
                      Ejecutar
                    </>
                  )}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* Template Info */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Información</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Complejidad</span>
                <Badge className={getComplexityColor(template.complexity)}>
                  {template.complexity === "simple" ? "Simple" : 
                   template.complexity === "intermediate" ? "Intermedio" : "Avanzado"}
                </Badge>
              </div>
              
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Duración estimada</span>
                <span className="text-sm font-medium">{template.estimated_duration_days} días</span>
              </div>
              
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Pasos</span>
                <span className="text-sm font-medium">{template.workflow_definition?.steps?.length || 0}</span>
              </div>
              
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Categoría</span>
                <Badge variant="secondary">{template.category}</Badge>
              </div>

              {template.tags?.length > 0 && (
                <div className="space-y-2">
                  <span className="text-sm text-muted-foreground">Tags</span>
                  <div className="flex flex-wrap gap-1">
                    {template.tags.map(tag => (
                      <Badge key={tag} variant="outline" className="text-xs">
                        {tag}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Process Steps */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Pasos del Proceso</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {template.workflow_definition?.steps?.map((step, index) => (
                  <div key={step.step_id} className="flex items-start gap-3">
                    <div className="w-6 h-6 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center text-xs font-medium flex-shrink-0 mt-0.5">
                      {index + 1}
                    </div>
                    <div className="flex-1 min-w-0">
                      <h4 className="text-sm font-medium">{step.step_name}</h4>
                      {step.description && (
                        <p className="text-xs text-muted-foreground mt-1">{step.description}</p>
                      )}
                      <Badge variant="outline" className="text-xs mt-1">
                        {step.step_type}
                      </Badge>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* AI Features */}
          <Card className="bg-gradient-to-br from-blue-50 to-cyan-50 border-blue-200">
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <IconRobot className="h-5 w-5 text-blue-600" />
                Emma AI
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="flex items-center gap-2 text-sm">
                <IconCheck className="h-4 w-4 text-green-600" />
                <span>Análisis legal automático</span>
              </div>
              <div className="flex items-center gap-2 text-sm">
                <IconCheck className="h-4 w-4 text-green-600" />
                <span>Generación de documentos</span>
              </div>
              <div className="flex items-center gap-2 text-sm">
                <IconCheck className="h-4 w-4 text-green-600" />
                <span>Recomendaciones inteligentes</span>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}