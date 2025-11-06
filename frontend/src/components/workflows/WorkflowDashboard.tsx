"use client";

import { useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  RefreshCw,
  Play,
  Square,
  Eye,
  Clock,
  CheckCircle,
  XCircle,
  AlertCircle,
  MoreHorizontal
} from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Workflow } from "@/hooks/useWorkflows";

interface WorkflowDashboardProps {
  workflows: Workflow[];
  isLoading: boolean;
  onCancelWorkflow: (workflowId: string) => Promise<void>;
  onRefresh: () => Promise<void>;
  getStatusBadge: (status: string) => React.ReactNode;
}

export function WorkflowDashboard({
  workflows,
  isLoading,
  onCancelWorkflow,
  onRefresh,
  getStatusBadge,
}: WorkflowDashboardProps) {
  const [refreshing, setRefreshing] = useState(false);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await onRefresh();
    } finally {
      setRefreshing(false);
    }
  };

  const handleCancel = async (workflowId: string) => {
    if (confirm("¿Estás seguro de que quieres cancelar este workflow?")) {
      try {
        await onCancelWorkflow(workflowId);
      } catch (error) {
        console.error("Error cancelling workflow:", error);
      }
    }
  };

  const getWorkflowTypeName = (type: string) => {
    switch (type) {
      case "contract_renewal":
        return "Renovación de Contrato";
      case "employee_onboarding":
        return "Incorporación de Empleado";
      default:
        return type;
    }
  };

  const getProgressFromStatus = (status: string) => {
    switch (status?.toLowerCase()) {
      case "running":
        return 50; // Estimated progress for running workflows
      case "completed":
        return 100;
      case "failed":
      case "cancelled":
        return 0;
      default:
        return 0;
    }
  };

  const formatDate = (dateString: string) => {
    try {
      return new Date(dateString).toLocaleString("es-ES", {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return dateString;
    }
  };

  if (isLoading && workflows.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Workflows Activos</CardTitle>
          <CardDescription>Cargando workflows...</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="p-4 border rounded-lg">
                <div className="animate-pulse space-y-2">
                  <div className="h-4 bg-gray-200 rounded w-3/4"></div>
                  <div className="h-3 bg-gray-200 rounded w-1/2"></div>
                  <div className="h-2 bg-gray-200 rounded"></div>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header with refresh button */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Workflows Activos</h2>
          <p className="text-muted-foreground">
            Monitorea el estado de tus procesos automatizados
          </p>
        </div>
        <Button
          variant="outline"
          onClick={handleRefresh}
          disabled={refreshing}
        >
          <RefreshCw className={`h-4 w-4 mr-2 ${refreshing ? "animate-spin" : ""}`} />
          Actualizar
        </Button>
      </div>

      {/* Workflows List */}
      {workflows.length === 0 ? (
        <Card>
          <CardContent className="pt-6">
            <div className="text-center py-8">
              <div className="mx-auto w-12 h-12 bg-gray-100 rounded-full flex items-center justify-center mb-4">
                <Play className="h-6 w-6 text-gray-400" />
              </div>
              <h3 className="text-lg font-medium text-gray-900 mb-2">
                No hay workflows activos
              </h3>
              <p className="text-gray-500 mb-4">
                Inicia un nuevo workflow para comenzar a automatizar tus procesos
              </p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4">
          {workflows.map((workflow) => (
            <Card key={workflow.workflow_id} className="hover:shadow-md transition-shadow">
              <CardContent className="p-6">
                <div className="flex items-start justify-between">
                  <div className="flex-1 space-y-3">
                    {/* Header */}
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-3">
                        <h3 className="font-semibold text-lg">
                          {getWorkflowTypeName(workflow.workflow_type)}
                        </h3>
                        {getStatusBadge(workflow.status)}
                      </div>

                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="sm">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem>
                            <Eye className="h-4 w-4 mr-2" />
                            Ver Detalles
                          </DropdownMenuItem>
                          {workflow.status === "running" && (
                            <DropdownMenuItem
                              onClick={() => handleCancel(workflow.workflow_id)}
                              className="text-red-600"
                            >
                              <Square className="h-4 w-4 mr-2" />
                              Cancelar
                            </DropdownMenuItem>
                          )}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>

                    {/* Workflow ID */}
                    <div className="text-sm text-muted-foreground">
                      ID: {workflow.workflow_id}
                    </div>

                    {/* Progress */}
                    {workflow.status === "running" && (
                      <div className="space-y-2">
                        <div className="flex justify-between text-sm">
                          <span>Progreso</span>
                          <span>{getProgressFromStatus(workflow.status)}%</span>
                        </div>
                        <Progress value={getProgressFromStatus(workflow.status)} className="h-2" />
                      </div>
                    )}

                    {/* Timestamps */}
                    <div className="flex items-center space-x-4 text-sm text-muted-foreground">
                      <div className="flex items-center space-x-1">
                        <Clock className="h-4 w-4" />
                        <span>Inicio: {formatDate(workflow.created_at)}</span>
                      </div>
                      {workflow.completed_at && (
                        <div className="flex items-center space-x-1">
                          <CheckCircle className="h-4 w-4" />
                          <span>Fin: {formatDate(workflow.completed_at)}</span>
                        </div>
                      )}
                    </div>

                    {/* Error Display */}
                    {workflow.error && (
                      <div className="p-3 bg-red-50 border border-red-200 rounded-md">
                        <div className="flex items-center space-x-2">
                          <AlertCircle className="h-4 w-4 text-red-500" />
                          <span className="text-sm text-red-700">{workflow.error}</span>
                        </div>
                      </div>
                    )}

                    {/* Result Summary */}
                    {workflow.result && workflow.status === "completed" && (
                      <div className="p-3 bg-green-50 border border-green-200 rounded-md">
                        <div className="flex items-center space-x-2">
                          <CheckCircle className="h-4 w-4 text-green-500" />
                          <span className="text-sm text-green-700">
                            Workflow completado exitosamente
                          </span>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Stats Summary */}
      {workflows.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Resumen</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="text-center">
                <div className="text-2xl font-bold text-blue-600">
                  {workflows.filter(w => w.status === "running").length}
                </div>
                <div className="text-sm text-muted-foreground">En Ejecución</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-green-600">
                  {workflows.filter(w => w.status === "completed").length}
                </div>
                <div className="text-sm text-muted-foreground">Completados</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-red-600">
                  {workflows.filter(w => w.status === "failed").length}
                </div>
                <div className="text-sm text-muted-foreground">Fallidos</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-gray-600">
                  {workflows.filter(w => w.status === "cancelled").length}
                </div>
                <div className="text-sm text-muted-foreground">Cancelados</div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}