"use client";

import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Plus, Play, Pause, Square, Eye, Clock, CheckCircle, XCircle, AlertCircle, GitBranch, TrendingUp, Book } from "lucide-react";
import { WorkflowDashboard } from "@/components/workflows/WorkflowDashboard";
import { WorkflowForm } from "@/components/workflows/WorkflowForm";
import { WorkflowTemplates } from "@/components/workflows/WorkflowTemplates";
import { WorkflowMonitor } from "@/components/workflows/WorkflowMonitor";
import { useWorkflows } from "@/hooks/useWorkflows";

export default function WorkflowsPage() {
  const params = useParams();
  const tenantId = params.tenantId as string;
  const [activeTab, setActiveTab] = useState("dashboard");
  const [showNewWorkflow, setShowNewWorkflow] = useState(false);

  const {
    workflows,
    isLoading,
    error,
    startWorkflow,
    cancelWorkflow,
    getWorkflowStatus,
    refreshWorkflows,
    getWorkflowStats,
    stats
  } = useWorkflows(tenantId);

  // Auto-refresh workflows every 30 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      refreshWorkflows();
    }, 30000);

    return () => clearInterval(interval);
  }, [refreshWorkflows]);

  // Load initial data
  useEffect(() => {
    refreshWorkflows();
    getWorkflowStats();
  }, [refreshWorkflows, getWorkflowStats]);

  const handleStartWorkflow = async (workflowType: string, inputData: any) => {
    try {
      await startWorkflow(workflowType, inputData);
      setShowNewWorkflow(false);
      refreshWorkflows();
    } catch (error) {
      console.error("Error starting workflow:", error);
    }
  };

  const handleCancelWorkflow = async (workflowId: string) => {
    try {
      await cancelWorkflow(workflowId);
      refreshWorkflows();
    } catch (error) {
      console.error("Error cancelling workflow:", error);
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status?.toLowerCase()) {
      case "running":
        return <Play className="h-4 w-4 text-blue-500" />;
      case "completed":
        return <CheckCircle className="h-4 w-4 text-green-500" />;
      case "failed":
        return <XCircle className="h-4 w-4 text-red-500" />;
      case "cancelled":
        return <Square className="h-4 w-4 text-gray-500" />;
      default:
        return <Clock className="h-4 w-4 text-yellow-500" />;
    }
  };

  const getStatusBadge = (status: string) => {
    const variants: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
      running: "default",
      completed: "secondary",
      failed: "destructive",
      cancelled: "outline",
    };

    return (
      <Badge variant={variants[status?.toLowerCase()] || "outline"}>
        {getStatusIcon(status)}
        <span className="ml-1 capitalize">{status || "Unknown"}</span>
      </Badge>
    );
  };

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <GitBranch className="h-8 w-8 text-blue-600" />
            Workflows con TemporalIO
          </h1>
          <p className="text-muted-foreground">
            Gestiona procesos automatizados durables con TemporalIO
          </p>
        </div>
        <Button onClick={() => setShowNewWorkflow(true)}>
          <Plus className="h-4 w-4 mr-2" />
          Nuevo Workflow
        </Button>
      </div>

      {/* Error Display */}
      {error && (
        <Card className="border-red-200 bg-red-50">
          <CardContent className="pt-6">
            <div className="flex items-center space-x-2">
              <AlertCircle className="h-5 w-5 text-red-500" />
              <span className="text-red-700">{error}</span>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Total Workflows</CardTitle>
              <GitBranch className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.total_workflows}</div>
              <p className="text-xs text-muted-foreground">
                Workflows en el sistema
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Activos</CardTitle>
              <Play className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-blue-600">{stats.active_workflows}</div>
              <p className="text-xs text-muted-foreground">
                En ejecución
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Completados Hoy</CardTitle>
              <CheckCircle className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-green-600">{stats.completed_today}</div>
              <p className="text-xs text-muted-foreground">
                Finalizados hoy
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Fallidos</CardTitle>
              <XCircle className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-red-600">{stats.failed_workflows}</div>
              <p className="text-xs text-muted-foreground">
                Con errores
              </p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Main Content */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="dashboard">Dashboard</TabsTrigger>
          <TabsTrigger value="monitor">Monitor</TabsTrigger>
          <TabsTrigger value="templates">Plantillas</TabsTrigger>
          <TabsTrigger value="history">Historial</TabsTrigger>
        </TabsList>

        <TabsContent value="dashboard" className="space-y-6">
          <WorkflowDashboard
            workflows={workflows}
            isLoading={isLoading}
            onCancelWorkflow={handleCancelWorkflow}
            onRefresh={refreshWorkflows}
            getStatusBadge={getStatusBadge}
          />
        </TabsContent>

        <TabsContent value="monitor" className="space-y-6">
          <WorkflowMonitor
            tenantId={tenantId}
            onWorkflowUpdate={(workflow) => {
              // Handle real-time workflow updates
              console.log("Workflow updated:", workflow);
              refreshWorkflows();
            }}
          />
        </TabsContent>

        <TabsContent value="templates" className="space-y-6">
          <WorkflowTemplates
            tenantId={tenantId}
            onStartWorkflow={handleStartWorkflow}
          />
        </TabsContent>

        <TabsContent value="history" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Historial de Workflows</CardTitle>
              <CardDescription>
                Workflows completados y cancelados
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="text-center py-8 text-muted-foreground">
                Historial próximamente disponible
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* New Workflow Modal */}
      {showNewWorkflow && (
        <WorkflowForm
          tenantId={tenantId}
          onSubmit={handleStartWorkflow}
          onCancel={() => setShowNewWorkflow(false)}
        />
      )}
    </div>
  );
}