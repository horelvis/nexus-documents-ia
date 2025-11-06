"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import {
  RefreshCw,
  Play,
  Square,
  Eye,
  Clock,
  CheckCircle,
  XCircle,
  AlertCircle,
  FileText,
  User,
  MessageSquare,
  Settings
} from "lucide-react";
import { useWorkflows } from "@/hooks/useWorkflows";

interface WorkflowStatusProps {
  workflowId: string;
  onClose: () => void;
}

export function WorkflowStatus({ workflowId, onClose }: WorkflowStatusProps) {
  const [workflow, setWorkflow] = useState<any>(null);
  const [executionLog, setExecutionLog] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const { getWorkflowStatus, queryWorkflow } = useWorkflows("");

  useEffect(() => {
    loadWorkflowData();
  }, [workflowId]);

  const loadWorkflowData = async () => {
    setIsLoading(true);
    try {
      const status = await getWorkflowStatus(workflowId);
      setWorkflow(status);

      // Try to get execution log if available
      try {
        const log = await queryWorkflow(workflowId, "get_execution_log");
        setExecutionLog(log || []);
      } catch (error) {
        console.log("Execution log not available");
      }
    } catch (error) {
      console.error("Error loading workflow data:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await loadWorkflowData();
    } finally {
      setRefreshing(false);
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status?.toLowerCase()) {
      case "running":
        return <Play className="h-5 w-5 text-blue-500" />;
      case "completed":
        return <CheckCircle className="h-5 w-5 text-green-500" />;
      case "failed":
        return <XCircle className="h-5 w-5 text-red-500" />;
      case "cancelled":
        return <Square className="h-5 w-5 text-gray-500" />;
      default:
        return <Clock className="h-5 w-5 text-yellow-500" />;
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
        second: "2-digit",
      });
    } catch {
      return dateString;
    }
  };

  const getStepIcon = (stepName: string) => {
    if (stepName.includes("document") || stepName.includes("generate")) {
      return <FileText className="h-4 w-4" />;
    }
    if (stepName.includes("notification") || stepName.includes("notify")) {
      return <MessageSquare className="h-4 w-4" />;
    }
    if (stepName.includes("analysis") || stepName.includes("evaluate")) {
      return <User className="h-4 w-4" />;
    }
    return <Settings className="h-4 w-4" />;
  };

  if (isLoading) {
    return (
      <Card className="w-full max-w-4xl">
        <CardContent className="p-6">
          <div className="animate-pulse space-y-4">
            <div className="h-6 bg-gray-200 rounded w-1/3"></div>
            <div className="h-4 bg-gray-200 rounded w-1/2"></div>
            <div className="h-32 bg-gray-200 rounded"></div>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (!workflow) {
    return (
      <Card className="w-full max-w-4xl">
        <CardContent className="p-6">
          <div className="text-center py-8">
            <AlertCircle className="h-12 w-12 text-red-500 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-gray-900 mb-2">
              Workflow no encontrado
            </h3>
            <p className="text-gray-500 mb-4">
              No se pudo cargar la información del workflow {workflowId}
            </p>
            <Button onClick={onClose}>Cerrar</Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="w-full max-w-4xl">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="flex items-center space-x-2">
              {getStatusIcon(workflow.status)}
              <div>
                <CardTitle className="text-xl">
                  Workflow {workflow.workflow_type?.replace("_", " ").toUpperCase()}
                </CardTitle>
                <CardDescription>
                  ID: {workflow.workflow_id}
                </CardDescription>
              </div>
            </div>
          </div>
          <div className="flex items-center space-x-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleRefresh}
              disabled={refreshing}
            >
              <RefreshCw className={`h-4 w-4 mr-2 ${refreshing ? "animate-spin" : ""}`} />
              Actualizar
            </Button>
            <Button variant="outline" size="sm" onClick={onClose}>
              Cerrar
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-6">
        {/* Status Overview */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="space-y-2">
            <div className="text-sm font-medium text-muted-foreground">Estado</div>
            <Badge
              variant={
                workflow.status === "running" ? "default" :
                workflow.status === "completed" ? "secondary" :
                workflow.status === "failed" ? "destructive" : "outline"
              }
              className="text-sm px-3 py-1"
            >
              {workflow.status?.toUpperCase()}
            </Badge>
          </div>

          <div className="space-y-2">
            <div className="text-sm font-medium text-muted-foreground">Progreso</div>
            <div className="space-y-1">
              <Progress value={getProgressFromStatus(workflow.status)} className="h-2" />
              <div className="text-xs text-muted-foreground">
                {getProgressFromStatus(workflow.status)}% completado
              </div>
            </div>
          </div>

          <div className="space-y-2">
            <div className="text-sm font-medium text-muted-foreground">Inicio</div>
            <div className="text-sm">
              {formatDate(workflow.created_at)}
            </div>
          </div>
        </div>

        <Separator />

        {/* Execution Log */}
        {executionLog.length > 0 && (
          <div className="space-y-4">
            <h3 className="text-lg font-semibold">Log de Ejecución</h3>
            <div className="space-y-3 max-h-96 overflow-y-auto">
              {executionLog.map((entry, index) => (
                <div key={index} className="flex items-start space-x-3 p-3 bg-gray-50 rounded-lg">
                  <div className="flex-shrink-0 mt-0.5">
                    {getStepIcon(entry.step)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-medium text-gray-900">
                        {entry.step.replace("_", " ").toUpperCase()}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {formatDate(entry.timestamp)}
                      </p>
                    </div>
                    <p className="text-sm text-muted-foreground mt-1">
                      Estado: {entry.state}
                    </p>
                    {entry.data && typeof entry.data === "object" && (
                      <details className="mt-2">
                        <summary className="text-xs text-blue-600 cursor-pointer hover:text-blue-800">
                          Ver datos
                        </summary>
                        <pre className="text-xs bg-gray-100 p-2 mt-1 rounded overflow-x-auto">
                          {JSON.stringify(entry.data, null, 2)}
                        </pre>
                      </details>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Result */}
        {workflow.result && (
          <>
            <Separator />
            <div className="space-y-4">
              <h3 className="text-lg font-semibold">Resultado</h3>
              <div className="p-4 bg-green-50 border border-green-200 rounded-lg">
                <div className="flex items-center space-x-2 mb-2">
                  <CheckCircle className="h-5 w-5 text-green-500" />
                  <span className="font-medium text-green-800">Workflow Completado</span>
                </div>
                <pre className="text-sm text-green-700 whitespace-pre-wrap">
                  {JSON.stringify(workflow.result, null, 2)}
                </pre>
              </div>
            </div>
          </>
        )}

        {/* Error */}
        {workflow.error && (
          <>
            <Separator />
            <div className="space-y-4">
              <h3 className="text-lg font-semibold">Error</h3>
              <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
                <div className="flex items-center space-x-2 mb-2">
                  <XCircle className="h-5 w-5 text-red-500" />
                  <span className="font-medium text-red-800">Error en Workflow</span>
                </div>
                <p className="text-sm text-red-700">{workflow.error}</p>
              </div>
            </div>
          </>
        )}

        {/* Actions */}
        <div className="flex justify-end space-x-3 pt-4 border-t">
          <Button variant="outline" onClick={onClose}>
            Cerrar
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}