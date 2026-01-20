"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { X, Play, Loader2 } from "lucide-react"
import { useWorkflowService } from "@/lib/workflow-service"

interface WorkflowFormProps {
  tenantId: string
  onSubmit: (workflowType: string, inputData: any) => Promise<void>
  onCancel: () => void
}

export function WorkflowForm({ tenantId, onSubmit, onCancel }: WorkflowFormProps) {
  const workflowService = useWorkflowService()
  const [isLoading, setIsLoading] = useState(false)
  const [definitions, setDefinitions] = useState<any[]>([])
  const [selectedProcess, setSelectedProcess] = useState("")
  const [businessKey, setBusinessKey] = useState("")
  const [variables, setVariables] = useState("{}")

  useEffect(() => {
    loadDefinitions()
  }, [])

  const loadDefinitions = async () => {
    try {
      const response = await workflowService.getProcessDefinitions({ latest_only: true })
      if (response.data?.definitions) {
        setDefinitions(response.data.definitions)
      }
    } catch (error) {
      console.error("Error loading definitions:", error)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedProcess) return

    setIsLoading(true)
    try {
      let parsedVariables = {}
      try {
        parsedVariables = JSON.parse(variables)
      } catch (e) {
        console.warn("Invalid JSON for variables, using empty object")
      }

      await onSubmit(selectedProcess, {
        business_key: businessKey || undefined,
        ...parsedVariables
      })
    } catch (error) {
      console.error("Error starting workflow:", error)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <Card className="w-full max-w-lg">
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>Iniciar Nuevo Workflow</CardTitle>
            <CardDescription>
              Selecciona un proceso y configura los parámetros iniciales
            </CardDescription>
          </div>
          <Button variant="ghost" size="sm" onClick={onCancel}>
            <X className="h-4 w-4" />
          </Button>
        </CardHeader>
        <form onSubmit={handleSubmit}>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="process">Proceso</Label>
              <Select value={selectedProcess} onValueChange={setSelectedProcess}>
                <SelectTrigger>
                  <SelectValue placeholder="Selecciona un proceso" />
                </SelectTrigger>
                <SelectContent>
                  {definitions.map((def) => (
                    <SelectItem key={def.key} value={def.key}>
                      {def.name || def.key}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="businessKey">Business Key (opcional)</Label>
              <Input
                id="businessKey"
                value={businessKey}
                onChange={(e) => setBusinessKey(e.target.value)}
                placeholder="ej: doc-12345"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="variables">Variables (JSON)</Label>
              <Textarea
                id="variables"
                value={variables}
                onChange={(e) => setVariables(e.target.value)}
                placeholder='{"key": "value"}'
                className="font-mono text-sm"
                rows={4}
              />
            </div>
          </CardContent>
          <CardFooter className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onCancel}>
              Cancelar
            </Button>
            <Button type="submit" disabled={!selectedProcess || isLoading}>
              {isLoading ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Iniciando...
                </>
              ) : (
                <>
                  <Play className="h-4 w-4 mr-2" />
                  Iniciar Proceso
                </>
              )}
            </Button>
          </CardFooter>
        </form>
      </Card>
    </div>
  )
}
