"use client"

import { useState, useEffect } from "react"
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
import { RefreshCw, Activity, Loader2, AlertCircle, CheckCircle, Clock } from "lucide-react"
import { useWorkflowService } from "@/lib/workflow-service"

interface WorkflowMonitorProps {
  tenantId: string
  onWorkflowUpdate?: (workflow: any) => void
}

export function WorkflowMonitor({ tenantId, onWorkflowUpdate }: WorkflowMonitorProps) {
  const workflowService = useWorkflowService()
  const [isLoading, setIsLoading] = useState(true)
  const [instances, setInstances] = useState<any[]>([])
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)

  useEffect(() => {
    loadInstances()
  }, [])

  useEffect(() => {
    if (!autoRefresh) return

    const interval = setInterval(() => {
      loadInstances()
    }, 10000) // Refresh every 10 seconds

    return () => clearInterval(interval)
  }, [autoRefresh])

  const loadInstances = async () => {
    try {
      const response = await workflowService.getProcessInstances({ active_only: true })
      if (response.data?.instances) {
        setInstances(response.data.instances)
        setLastRefresh(new Date())
      }
    } catch (error) {
      console.error("Error loading instances:", error)
    } finally {
      setIsLoading(false)
    }
  }

  const getStatusIcon = (instance: any) => {
    if (instance.ended) {
      return <CheckCircle className="h-4 w-4 text-green-500" />
    }
    if (instance.suspended) {
      return <AlertCircle className="h-4 w-4 text-yellow-500" />
    }
    return <Activity className="h-4 w-4 text-blue-500 animate-pulse" />
  }

  const getStatusBadge = (instance: any) => {
    if (instance.ended) {
      return <Badge variant="secondary">Completado</Badge>
    }
    if (instance.suspended) {
      return <Badge variant="outline">Suspendido</Badge>
    }
    return <Badge className="bg-blue-100 text-blue-800">En Ejecución</Badge>
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle className="flex items-center gap-2">
            <Activity className="h-5 w-5" />
            Monitor de Procesos
          </CardTitle>
          <CardDescription>
            Seguimiento en tiempo real de instancias de workflow
          </CardDescription>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant={autoRefresh ? "default" : "outline"}
            size="sm"
            onClick={() => setAutoRefresh(!autoRefresh)}
          >
            {autoRefresh ? "Auto-refresh ON" : "Auto-refresh OFF"}
          </Button>
          <Button variant="outline" size="sm" onClick={loadInstances}>
            <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
            Actualizar
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {lastRefresh && (
          <div className="text-xs text-muted-foreground mb-4 flex items-center gap-1">
            <Clock className="h-3 w-3" />
            Última actualización: {lastRefresh.toLocaleTimeString()}
          </div>
        )}

        {isLoading && instances.length === 0 ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : instances.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            No hay procesos activos en este momento
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Estado</TableHead>
                <TableHead>ID</TableHead>
                <TableHead>Proceso</TableHead>
                <TableHead>Business Key</TableHead>
                <TableHead className="text-right">Acciones</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {instances.map((instance) => (
                <TableRow key={instance.id}>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      {getStatusIcon(instance)}
                      {getStatusBadge(instance)}
                    </div>
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {instance.id.substring(0, 8)}...
                  </TableCell>
                  <TableCell>
                    <code className="bg-muted px-1 py-0.5 rounded text-xs">
                      {instance.definition_key}
                    </code>
                  </TableCell>
                  <TableCell>
                    {instance.business_key || "-"}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button variant="ghost" size="sm">
                      Ver detalles
                    </Button>
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
