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
import { useWorkflows } from "@/hooks/use-workflows";
import { useTranslation } from "@/lib/i18n/hooks";

export default function WorkflowsPage() {
  const params = useParams();
  const tenantId = params.tenantId as string;
  const [activeTab, setActiveTab] = useState("dashboard");
  const [showNewWorkflow, setShowNewWorkflow] = useState(false);
  const { t } = useTranslation();

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

  useEffect(() => {
    const interval = setInterval(() => {
      refreshWorkflows();
    }, 30000);

    return () => clearInterval(interval);
  }, [refreshWorkflows]);

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
      console.error(t('workflowsPage.toast.startWorkflowError'), error);
    }
  };

  const handleCancelWorkflow = async (workflowId: string) => {
    try {
      await cancelWorkflow(workflowId);
      refreshWorkflows();
    } catch (error) {
      console.error(t('workflowsPage.toast.cancelWorkflowError'), error);
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
        <span className="ml-1 capitalize">{t(`workflowsPage.status.${status?.toLowerCase()}`)}</span>
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
            {t('workflowsPage.title')}
          </h1>
          <p className="text-muted-foreground">
            {t('workflowsPage.subtitle')}
          </p>
        </div>
        <Button onClick={() => setShowNewWorkflow(true)}>
          <Plus className="h-4 w-4 mr-2" />
          {t('workflowsPage.newWorkflowButton')}
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
              <CardTitle className="text-sm font-medium">{t('workflowsPage.stats.totalWorkflows.title')}</CardTitle>
              <GitBranch className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.total_workflows}</div>
              <p className="text-xs text-muted-foreground">
                {t('workflowsPage.stats.totalWorkflows.description')}
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">{t('workflowsPage.stats.activeWorkflows.title')}</CardTitle>
              <Play className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-blue-600">{stats.active_workflows}</div>
              <p className="text-xs text-muted-foreground">
                {t('workflowsPage.stats.activeWorkflows.description')}
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">{t('workflowsPage.stats.completedToday.title')}</CardTitle>
              <CheckCircle className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-green-600">{stats.completed_today}</div>
              <p className="text-xs text-muted-foreground">
                {t('workflowsPage.stats.completedToday.description')}
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">{t('workflowsPage.stats.failedWorkflows.title')}</CardTitle>
              <XCircle className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-red-600">{stats.failed_workflows}</div>
              <p className="text-xs text-muted-foreground">
                {t('workflowsPage.stats.failedWorkflows.description')}
              </p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Main Content */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="dashboard">{t('workflowsPage.tabs.dashboard')}</TabsTrigger>
          <TabsTrigger value="monitor">{t('workflowsPage.tabs.monitor')}</TabsTrigger>
          <TabsTrigger value="templates">{t('workflowsPage.tabs.templates')}</TabsTrigger>
          <TabsTrigger value="history">{t('workflowsPage.tabs.history')}</TabsTrigger>
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
              console.log(t('workflowsPage.toast.workflowUpdated'), workflow);
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
              <CardTitle>{t('workflowsPage.historyCard.title')}</CardTitle>
              <CardDescription>
                {t('workflowsPage.historyCard.description')}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="text-center py-8 text-muted-foreground">
                {t('workflowsPage.historyCard.emptyMessage')}
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