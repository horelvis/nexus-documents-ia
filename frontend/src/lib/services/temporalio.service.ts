"use client"

/**
 * Temporalio Microservice Client
 * Direct connection to the Temporalio microservice for AI-enhanced workflows
 */

import { useApiClient } from "../api-client"
import type { ApiResponse } from "../api-client"

export interface TemporalioTemplate {
  id: string
  name: string
  description: string
  workflow_definition: {
    start_step: string
    steps: Array<{
      step_id: string
      step_name: string
      step_type: string
      activity_type?: string
      activity_config?: any
      next_steps?: any
    }>
  }
  tenant_id: string
  is_active: boolean
  created_at: string
  updated_at: string
  ai_enhanced?: boolean
  agent_types_used?: string[]
  estimated_duration?: string
  complexity_level?: string
}

export interface TemporalioExecution {
  success: boolean
  workflow_id: string
  template_id: string
  status: string
  message: string
  started_at: string
}

export interface TemporalioExecutionStatus {
  workflow_id: string
  template_id: string
  tenant_id: string
  status: 'running' | 'completed' | 'failed' | 'cancelled'
  result?: any
  error?: string
  created_at: string
  completed_at?: string
  progress?: any
}

export interface TemporalioHealthStatus {
  status: 'healthy' | 'unhealthy'
  service: string
  version: string
  temporalio_service: {
    status: string
    host: string
    namespace: string
    task_queue: string
  }
  workers: {
    status: string
    running_workers: Record<string, string>
    task_queue: string
    max_concurrent_activities: number
    max_concurrent_workflows: number
  }
}

export interface WorkflowSummary {
  total_workflows: number;
  active_workflows: number;
  completed_today: number;
  failed_workflows: number;
  avg_completion_time: string;
}

export interface AIWorkflowFieldOption {
  label: string
  value: string
}

export type AIWorkflowFieldType = 'text' | 'textarea' | 'select' | 'number'

export interface AIWorkflowField {
  name: string
  label: string
  type: AIWorkflowFieldType
  required?: boolean
  placeholder?: string
  helper_text?: string
  default_value?: string
  options?: AIWorkflowFieldOption[]
}

export interface AIWorkflowTemplateMeta {
  id: string
  name: string
  description: string
  template_id: string
  tags?: string[]
  estimated_duration?: string
  complexity?: string
  fields: AIWorkflowField[]
}

const TEMPORALIO_BASE = "/temporalio"

function ensureData<T>(response: ApiResponse<T>, fallbackMessage: string): T {
  if (response.error || !response.data) {
    throw new Error(response.error || fallbackMessage)
  }

  return response.data
}

export function useTemporalioService() {
  const apiClient = useApiClient()

  const get = async <T>(endpoint: string, errorMessage: string) => {
    const response = await apiClient.get<T>(endpoint)
    return ensureData(response, errorMessage)
  }

  const post = async <T>(endpoint: string, data?: any, errorMessage?: string) => {
    const response = await apiClient.post<T>(endpoint, data)
    return ensureData(response, errorMessage || "Temporalio request failed")
  }

  const checkHealth = () =>
    get<TemporalioHealthStatus>(`${TEMPORALIO_BASE}/health`, "No fue posible obtener la salud del servicio Temporalio")

  const getTemplates = () =>
    get<TemporalioTemplate[]>(
      `${TEMPORALIO_BASE}/workflow-templates`,
      "No fue posible cargar los workflows inteligentes"
    )

  const getTemplate = (templateId: string) =>
    get<TemporalioTemplate>(
      `${TEMPORALIO_BASE}/workflow-templates/${templateId}`,
      "No fue posible cargar el workflow solicitado"
    )

  const executeWorkflow = (
    templateId: string,
    tenantId: string,
    inputData: Record<string, any>
  ) =>
    post<TemporalioExecution>(
      `${TEMPORALIO_BASE}/workflow-executions/start`,
      {
        template_id: templateId,
        tenant_id: tenantId,
        input_data: inputData,
      },
      "No fue posible iniciar el workflow"
    )

  const getExecutionStatus = (workflowId: string) =>
    get<TemporalioExecutionStatus>(
      `${TEMPORALIO_BASE}/workflow-executions/${workflowId}`,
      "No fue posible obtener el estado del workflow"
    )

  const cancelExecution = (workflowId: string, reason?: string) =>
    post<{ message: string }>(
      `${TEMPORALIO_BASE}/workflow-executions/${workflowId}/cancel`,
      reason ? { reason } : undefined,
      "No fue posible cancelar el workflow"
    )

  const getExecutionHistory = (workflowId: string) =>
    get<any>(
      `${TEMPORALIO_BASE}/workflow-executions/${workflowId}/history`,
      "No fue posible obtener el historial del workflow"
    )

  const getAIEnhancedTemplates = async () => {
    const templates = await getTemplates()
    return templates.filter(
      (t) =>
        t.name.toLowerCase().includes("inteligente") ||
        t.name.toLowerCase().includes("ai") ||
        (t.agent_types_used?.length ?? 0) > 0
    )
  }

  const getAIWorkflowCatalog = () =>
    get<AIWorkflowTemplateMeta[]>(
      `${TEMPORALIO_BASE}/ai-workflows`,
      "No fue posible obtener los workflows AI disponibles"
    )

  const executeAIWorkflow = (workflowId: string, payload: Record<string, any>) =>
    post<TemporalioExecution>(
      `${TEMPORALIO_BASE}/ai-workflows/${workflowId}/execute`,
      { payload },
      "No fue posible ejecutar el workflow AI"
    )

  const getWorkflowSummary = () =>
    get<WorkflowSummary>(
      `${TEMPORALIO_BASE}/workflows/summary`,
      "No fue posible obtener el resumen de workflows"
    )

  return {
    checkHealth,
    getTemplates,
    getTemplate,
    executeWorkflow,
    getExecutionStatus,
    cancelExecution,
    getExecutionHistory,
    getAIEnhancedTemplates,
    getAIWorkflowCatalog,
    executeAIWorkflow,
    getWorkflowSummary,
  }
}
