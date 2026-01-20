"use client"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { RefreshCw, XCircle, Eye, Loader2 } from "lucide-react"

interface WorkflowExecution {
  id: string
  workflow_type: string
  status: string
  started_at: string
  completed_at?: string
  input_data?: Record<string, any>
  output_data?: Record<string, any>
  error?: string
}

interface WorkflowDashboardProps {
  workflows: WorkflowExecution[]
  isLoading: boolean
  onCancelWorkflow: (workflowId: string) => void
  onRefresh: () => void
  getStatusBadge: (status: string) => React.ReactNode
}

export function WorkflowDashboard({
  workflows,
  isLoading,
  onCancelWorkflow,
  onRefresh,
  getStatusBadge
}: WorkflowDashboardProps) {
  const formatDate = (dateStr?: string) => {
    if (!dateStr) return "-"
    return new Date(dateStr).toLocaleString()
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

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle>Workflows Activos</CardTitle>
          <CardDescription>
            Procesos de trabajo en ejecución
          </CardDescription>
        </div>
        <Button variant="outline" size="sm" onClick={onRefresh}>
          <RefreshCw className="h-4 w-4 mr-2" />
          Actualizar
        </Button>
      </CardHeader>
      <CardContent>
        {workflows.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            No hay workflows activos
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID</TableHead>
                <TableHead>Tipo</TableHead>
                <TableHead>Estado</TableHead>
                <TableHead>Iniciado</TableHead>
                <TableHead className="text-right">Acciones</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {workflows.map((workflow) => (
                <TableRow key={workflow.id}>
                  <TableCell className="font-mono text-xs">
                    {workflow.id.substring(0, 8)}...
                  </TableCell>
                  <TableCell>{workflow.workflow_type}</TableCell>
                  <TableCell>{getStatusBadge(workflow.status)}</TableCell>
                  <TableCell>{formatDate(workflow.started_at)}</TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-2">
                      <Button variant="ghost" size="sm">
                        <Eye className="h-4 w-4" />
                      </Button>
                      {workflow.status === "running" && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => onCancelWorkflow(workflow.id)}
                        >
                          <XCircle className="h-4 w-4 text-red-500" />
                        </Button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}
