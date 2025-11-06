"use client";

import { useState, useEffect, useRef } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  Activity,
  Wifi,
  WifiOff,
  RefreshCw,
  AlertTriangle,
  CheckCircle,
  Clock,
  Play,
  Square
} from "lucide-react";
import { useWorkflows } from "@/hooks/useWorkflows";

interface WorkflowMonitorProps {
  tenantId: string;
  onWorkflowUpdate?: (workflow: any) => void;
}

export function WorkflowMonitor({ tenantId, onWorkflowUpdate }: WorkflowMonitorProps) {
  const [isConnected, setIsConnected] = useState(false);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<"connecting" | "connected" | "disconnected" | "error">("connecting");
  const [activeWorkflows, setActiveWorkflows] = useState<any[]>([]);
  const [systemHealth, setSystemHealth] = useState<any>(null);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  const { refreshWorkflows } = useWorkflows(tenantId);

  useEffect(() => {
    // Start monitoring
    startMonitoring();

    return () => {
      stopMonitoring();
    };
  }, [tenantId]);

  const startMonitoring = () => {
    setConnectionStatus("connecting");

    // Initial load
    loadWorkflowData();

    // Set up polling every 10 seconds
    intervalRef.current = setInterval(() => {
      loadWorkflowData();
    }, 10000);
  };

  const stopMonitoring = () => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    setConnectionStatus("disconnected");
    setIsConnected(false);
  };

  const loadWorkflowData = async () => {
    try {
      const workflows = await refreshWorkflows();
      setActiveWorkflows(workflows.filter((w: any) => w.status === "running"));
      setLastUpdate(new Date());
      setConnectionStatus("connected");
      setIsConnected(true);

      // Check system health
      await checkSystemHealth();

      // Notify parent component
      if (onWorkflowUpdate && workflows.length > 0) {
        onWorkflowUpdate(workflows[0]);
      }
    } catch (error) {
      console.error("Error loading workflow data:", error);
      setConnectionStatus("error");
      setIsConnected(false);
    }
  };

  const checkSystemHealth = async () => {
    try {
      const baseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const response = await fetch(`${baseUrl}/api/v1/temporalio/health`);

      if (response.ok) {
        const health = await response.json();
        setSystemHealth(health);
      }
    } catch (error) {
      console.error("Error checking system health:", error);
      setSystemHealth(null);
    }
  };

  const getConnectionStatusColor = () => {
    switch (connectionStatus) {
      case "connected":
        return "text-green-600";
      case "connecting":
        return "text-yellow-600";
      case "error":
        return "text-red-600";
      default:
        return "text-gray-600";
    }
  };

  const getConnectionStatusIcon = () => {
    switch (connectionStatus) {
      case "connected":
        return <Wifi className="h-4 w-4" />;
      case "connecting":
        return <RefreshCw className="h-4 w-4 animate-spin" />;
      case "error":
        return <WifiOff className="h-4 w-4" />;
      default:
        return <AlertTriangle className="h-4 w-4" />;
    }
  };

  const formatLastUpdate = (date: Date | null) => {
    if (!date) return "Nunca";

    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const seconds = Math.floor(diff / 1000);

    if (seconds < 60) return `Hace ${seconds}s`;
    if (seconds < 3600) return `Hace ${Math.floor(seconds / 60)}m`;
    return `Hace ${Math.floor(seconds / 3600)}h`;
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-5 w-5" />
              Monitor de Workflows
            </CardTitle>
            <CardDescription>
              Monitoreo en tiempo real del estado de los workflows
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <div className={`flex items-center gap-1 text-sm ${getConnectionStatusColor()}`}>
              {getConnectionStatusIcon()}
              <span className="capitalize">{connectionStatus}</span>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={isConnected ? stopMonitoring : startMonitoring}
            >
              {isConnected ? "Detener" : "Iniciar"}
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-6">
        {/* Connection Status */}
        <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
          <div className="flex items-center gap-3">
            <div className={`w-3 h-3 rounded-full ${
              connectionStatus === "connected" ? "bg-green-500" :
              connectionStatus === "connecting" ? "bg-yellow-500" :
              "bg-red-500"
            }`} />
            <div>
              <div className="text-sm font-medium">
                {connectionStatus === "connected" ? "Conectado" :
                 connectionStatus === "connecting" ? "Conectando..." :
                 connectionStatus === "error" ? "Error de conexión" :
                 "Desconectado"}
              </div>
              <div className="text-xs text-muted-foreground">
                Última actualización: {formatLastUpdate(lastUpdate)}
              </div>
            </div>
          </div>
          {isConnected && (
            <Badge variant="secondary" className="text-xs">
              Auto-refresh cada 10s
            </Badge>
          )}
        </div>

        {/* System Health */}
        {systemHealth && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-3 bg-blue-50 rounded-lg">
              <div className="flex items-center gap-2 mb-1">
                <div className={`w-2 h-2 rounded-full ${
                  systemHealth.status === "healthy" ? "bg-green-500" : "bg-red-500"
                }`} />
                <span className="text-sm font-medium">API Core</span>
              </div>
              <div className="text-xs text-muted-foreground">
                {systemHealth.status === "healthy" ? "Operativo" : "Con problemas"}
              </div>
            </div>

            <div className="p-3 bg-green-50 rounded-lg">
              <div className="flex items-center gap-2 mb-1">
                <div className={`w-2 h-2 rounded-full ${
                  systemHealth.temporalio_service?.status === "healthy" ? "bg-green-500" : "bg-red-500"
                }`} />
                <span className="text-sm font-medium">TemporalIO Service</span>
              </div>
              <div className="text-xs text-muted-foreground">
                {systemHealth.temporalio_service?.status === "healthy" ? "Operativo" : "Con problemas"}
              </div>
            </div>

            <div className="p-3 bg-purple-50 rounded-lg">
              <div className="flex items-center gap-2 mb-1">
                <div className={`w-2 h-2 rounded-full ${
                  systemHealth.temporalio_service?.workers?.status === "healthy" ? "bg-green-500" : "bg-red-500"
                }`} />
                <span className="text-sm font-medium">Workers</span>
              </div>
              <div className="text-xs text-muted-foreground">
                {systemHealth.temporalio_service?.workers?.status === "healthy" ? "Activos" : "Inactivos"}
              </div>
            </div>
          </div>
        )}

        {/* Active Workflows */}
        <div className="space-y-3">
          <h3 className="text-lg font-semibold">Workflows Activos</h3>

          {activeWorkflows.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <Play className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>No hay workflows activos en este momento</p>
            </div>
          ) : (
            <div className="space-y-3">
              {activeWorkflows.map((workflow) => (
                <div key={workflow.workflow_id} className="p-4 border rounded-lg">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <Play className="h-5 w-5 text-blue-500" />
                      <div>
                        <h4 className="font-medium">
                          {workflow.workflow_type?.replace("_", " ").toUpperCase()}
                        </h4>
                        <p className="text-sm text-muted-foreground">
                          ID: {workflow.workflow_id}
                        </p>
                      </div>
                    </div>
                    <Badge variant="default">En ejecución</Badge>
                  </div>

                  <div className="space-y-2">
                    <div className="flex justify-between text-sm">
                      <span>Progreso estimado</span>
                      <span>50%</span>
                    </div>
                    <Progress value={50} className="h-2" />
                  </div>

                  <div className="flex justify-between items-center mt-3 text-xs text-muted-foreground">
                    <span>
                      Inicio: {new Date(workflow.created_at).toLocaleString("es-ES")}
                    </span>
                    <span className="flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      Actualizado: {formatLastUpdate(lastUpdate)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Performance Metrics */}
        {isConnected && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 pt-4 border-t">
            <div className="text-center">
              <div className="text-2xl font-bold text-blue-600">
                {activeWorkflows.length}
              </div>
              <div className="text-xs text-muted-foreground">Activos</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-green-600">
                {systemHealth?.status === "healthy" ? "✓" : "✗"}
              </div>
              <div className="text-xs text-muted-foreground">API Status</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-purple-600">
                {systemHealth?.temporalio_service?.status === "healthy" ? "✓" : "✗"}
              </div>
              <div className="text-xs text-muted-foreground">TemporalIO</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-orange-600">
                {formatLastUpdate(lastUpdate)}
              </div>
              <div className="text-xs text-muted-foreground">Última sync</div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}