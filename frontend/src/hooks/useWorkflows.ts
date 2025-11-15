import { useState, useCallback } from "react";
import { useToast } from "@/hooks/use-toast";
import { useApiClient } from "@/lib/api-client";

export interface Workflow {
  workflow_id: string;
  workflow_type: string;
  status: string;
  created_at: string;
  completed_at?: string;
  result?: any;
  error?: string;
  input_data?: any;
}

export interface WorkflowTemplate {
  id: string;
  name: string;
  description: string;
  workflow_type: string;
  estimated_time: string;
  steps: number;
  usage: number;
  input_schema: any;
}

export interface WorkflowStats {
  total_workflows: number;
  active_workflows: number;
  completed_today: number;
  failed_workflows: number;
  avg_completion_time: string;
}

export function useWorkflows(tenantId: string) {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [templates, setTemplates] = useState<WorkflowTemplate[]>([]);
  const [stats, setStats] = useState<WorkflowStats | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { toast } = useToast();
  const apiClient = useApiClient();

  const apiCall = useCallback(
    async <T,>(method: "GET" | "POST", endpoint: string, body?: any): Promise<T> => {
      const response =
        method === "GET"
          ? await apiClient.get<T>(endpoint)
          : await apiClient.post<T>(endpoint, body);

      if (response.error) {
        throw new Error(response.error);
      }

      return response.data as T;
    },
    [apiClient]
  );

  const refreshWorkflows = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const data = await apiCall<Workflow[] | { workflows: Workflow[] }>("GET", `/temporalio/workflows`);
      const workflowList = Array.isArray(data) ? data : data?.workflows || [];
      setWorkflows(workflowList);
      return workflowList;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Error loading workflows";
      setError(errorMessage);
      toast({
        title: "Error",
        description: errorMessage,
        variant: "destructive",
      });
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, [apiCall, toast]);

  const startWorkflow = useCallback(async (workflowType: string, inputData: any) => {
    setIsLoading(true);
    setError(null);

    try {
      let endpoint = "";
      let payload = {};

      // Map workflow types to specific endpoints
      switch (workflowType) {
        case "contract_renewal":
          endpoint = "/temporalio/contract-renewal";
          payload = {
            contract_id: inputData.contract_id,
            tenant_id: tenantId,
            user_id: inputData.user_id,
            employee_name: inputData.employee_name,
            contract_type: inputData.contract_type,
            expiration_date: inputData.expiration_date,
            position: inputData.position,
            performance_rating: inputData.performance_rating,
            current_salary: inputData.current_salary,
            force_regenerate: inputData.force_regenerate || false,
          };
          break;

        case "employee_onboarding":
          endpoint = "/temporalio/employee-onboarding";
          payload = {
            employee_id: inputData.employee_id,
            tenant_id: tenantId,
            hr_user_id: inputData.hr_user_id,
            employee_name: inputData.employee_name,
            position: inputData.position,
            department: inputData.department,
            start_date: inputData.start_date,
            manager_id: inputData.manager_id,
            contract_type: inputData.contract_type,
            salary: inputData.salary,
            work_location: inputData.work_location,
            equipment_needs: inputData.equipment_needs || [],
          };
          break;

        default:
          throw new Error(`Unknown workflow type: ${workflowType}`);
      }

      const result = await apiCall("POST", endpoint, payload);

      toast({
        title: "Workflow Iniciado",
        description: `Workflow ${workflowType} iniciado exitosamente`,
      });

      // Refresh workflows list
      await refreshWorkflows();

      return result;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Error starting workflow";
      setError(errorMessage);
      toast({
        title: "Error",
        description: errorMessage,
        variant: "destructive",
      });
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, [apiCall, tenantId, toast, refreshWorkflows]);

  const getWorkflowStatus = useCallback(async (workflowId: string) => {
    try {
      const result = await apiCall("GET", `/temporalio/workflow/${workflowId}/status`);
      return result;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Error getting workflow status";
      toast({
        title: "Error",
        description: errorMessage,
        variant: "destructive",
      });
      throw err;
    }
  }, [apiCall, toast]);

  const cancelWorkflow = useCallback(async (workflowId: string, reason?: string) => {
    try {
      const result = await apiCall("POST", `/temporalio/workflow/${workflowId}/cancel`, { reason });

      toast({
        title: "Workflow Cancelado",
        description: `Workflow ${workflowId} cancelado exitosamente`,
      });

      return result;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Error cancelling workflow";
      toast({
        title: "Error",
        description: errorMessage,
        variant: "destructive",
      });
      throw err;
    }
  }, [apiCall, toast]);

  const queryWorkflow = useCallback(async (workflowId: string, queryType: string, queryArgs?: any) => {
    try {
      const result = await apiCall("POST", `/temporalio/workflow/${workflowId}/query`, {
        query_type: queryType,
        query_args: queryArgs,
      });

      return result;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Error querying workflow";
      toast({
        title: "Error",
        description: errorMessage,
        variant: "destructive",
      });
      throw err;
    }
  }, [apiCall, toast]);

  const getWorkflowTemplates = useCallback(async () => {
    try {
      // For now, return hardcoded templates based on available workflows
      const availableTemplates: WorkflowTemplate[] = [
        {
          id: "contract_renewal",
          name: "Renovación de Contrato",
          description: "Proceso automatizado para renovación de contratos laborales con análisis de Emma AI",
          workflow_type: "contract_renewal",
          estimated_time: "5-10 min",
          steps: 7,
          usage: 0,
          input_schema: {
            contract_id: "string",
            employee_name: "string",
            contract_type: "string",
            expiration_date: "string",
            position: "string",
            performance_rating: "string?",
            current_salary: "string?",
          },
        },
        {
          id: "employee_onboarding",
          name: "Incorporación de Empleado",
          description: "Proceso completo de onboarding con generación de documentos y setup de sistemas",
          workflow_type: "employee_onboarding",
          estimated_time: "15-30 min",
          steps: 8,
          usage: 0,
          input_schema: {
            employee_id: "string",
            employee_name: "string",
            position: "string",
            department: "string",
            start_date: "string",
            manager_id: "string",
            contract_type: "string",
            salary: "string",
            work_location: "string",
            equipment_needs: "array?",
          },
        },
      ];

      setTemplates(availableTemplates);
      return availableTemplates;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Error loading templates";
      setError(errorMessage);
      throw err;
    }
  }, []);

  const getWorkflowStats = useCallback(async () => {
    try {
      // Calculate stats from current workflows
      const allWorkflows = workflows.length > 0 ? workflows : await refreshWorkflows();

      const stats: WorkflowStats = {
        total_workflows: allWorkflows.length,
        active_workflows: allWorkflows.filter(w => w.status === "running").length,
        completed_today: allWorkflows.filter(w => {
          if (!w.completed_at) return false;
          const completedDate = new Date(w.completed_at);
          const today = new Date();
          return completedDate.toDateString() === today.toDateString() && w.status === "completed";
        }).length,
        failed_workflows: allWorkflows.filter(w => w.status === "failed").length,
        avg_completion_time: "--", // TODO: Calculate from actual data
      };

      setStats(stats);
      return stats;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Error loading stats";
      setError(errorMessage);
      throw err;
    }
  }, [workflows, refreshWorkflows]);

  return {
    workflows,
    templates,
    stats,
    isLoading,
    error,
    refreshWorkflows,
    startWorkflow,
    getWorkflowStatus,
    cancelWorkflow,
    queryWorkflow,
    getWorkflowTemplates,
    getWorkflowStats,
  };
}
