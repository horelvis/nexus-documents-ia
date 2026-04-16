"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Play, FileText, Clock, Loader2 } from "lucide-react"
import { useWorkflowService } from "@/lib/workflow-service"

interface WorkflowTemplatesProps {
  onStartWorkflow: (workflowType: string, inputData: any) => Promise<void>
}

export function WorkflowTemplates({ onStartWorkflow }: WorkflowTemplatesProps) {
  const workflowService = useWorkflowService()
  const [isLoading, setIsLoading] = useState(true)
  const [definitions, setDefinitions] = useState<any[]>([])

  useEffect(() => {
    loadDefinitions()
  }, [])

  const loadDefinitions = async () => {
    setIsLoading(true)
    try {
      const response = await workflowService.getProcessDefinitions({ latest_only: true })
      if (response.data?.definitions) {
        setDefinitions(response.data.definitions)
      }
    } catch (error) {
      console.error("Error loading definitions:", error)
    } finally {
      setIsLoading(false)
    }
  }

  const handleStartWorkflow = async (processKey: string) => {
    try {
      await onStartWorkflow(processKey, {})
    } catch (error) {
      console.error("Error starting workflow:", error)
    }
  }

  if (isLoading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    )
  }

  if (definitions.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Plantillas de Workflow</CardTitle>
          <CardDescription>
            Procesos predefinidos listos para usar
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="text-center py-8 text-muted-foreground">
            No hay procesos desplegados. Despliega un archivo BPMN para comenzar.
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Plantillas de Workflow</CardTitle>
          <CardDescription>
            Procesos BPMN desplegados y listos para ejecutar
          </CardDescription>
        </CardHeader>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {definitions.map((def) => (
          <Card key={def.key} className="hover:shadow-md transition-shadow">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg flex items-center gap-2">
                  <FileText className="h-5 w-5 text-blue-500" />
                  {def.name || def.key}
                </CardTitle>
                <Badge variant="secondary">v{def.version}</Badge>
              </div>
              {def.description && (
                <CardDescription>{def.description}</CardDescription>
              )}
            </CardHeader>
            <CardContent>
              <div className="flex items-center justify-between">
                <div className="text-sm text-muted-foreground">
                  <code className="bg-muted px-1 py-0.5 rounded">{def.key}</code>
                </div>
                <Button size="sm" onClick={() => handleStartWorkflow(def.key)}>
                  <Play className="h-4 w-4 mr-1" />
                  Iniciar
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Document Approval Template */}
      <Card className="border-blue-200 bg-blue-50/50">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg flex items-center gap-2">
              <FileText className="h-5 w-5 text-blue-600" />
              Aprobación de Documento
            </CardTitle>
            <Badge className="bg-blue-100 text-blue-800">Recomendado</Badge>
          </div>
          <CardDescription>
            Workflow completo para revisar, aprobar y firmar documentos
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4 text-sm text-muted-foreground">
              <div className="flex items-center gap-1">
                <Clock className="h-4 w-4" />
                ~2-5 días
              </div>
            </div>
            <Button
              size="sm"
              onClick={() => handleStartWorkflow("document-approval")}
            >
              <Play className="h-4 w-4 mr-1" />
              Iniciar
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
