/**
 * Temporal.io Service Stub
 *
 * This service is deprecated as Temporal.io has been removed from the project.
 * It's kept as a stub for backward compatibility with existing pages.
 * The project is migrating to Camunda for workflow orchestration.
 */

import { useMemo } from 'react'

export interface AIWorkflowTemplateField {
  name: string
  type: 'string' | 'number' | 'boolean' | 'select' | 'textarea'
  label: string
  required: boolean
  default?: string
  default_value?: string
  options?: string[] | { value: string; label: string }[]
  placeholder?: string
  helper_text?: string
}

export interface AIWorkflowTemplateMeta {
  id: string
  name: string
  description: string
  category: string
  fields: AIWorkflowTemplateField[]
  complexity_level?: string
  estimated_duration?: string
  workflow_definition?: string | { steps?: { id: string; name: string }[] }
  agent_types_used?: string[]
  tenant_id?: string
}

export interface TemporalioExecution {
  workflow_id: string
  run_id: string
  status: string
  template_id?: string
}

export interface TemporalioExecutionStatus {
  status: 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED' | 'TERMINATED' | 'running' | 'completed' | 'failed'
  result?: Record<string, unknown>
  error?: string
  created_at?: string
  completed_at?: string
}

export class TemporalioService {
  async getAIWorkflowTemplates(): Promise<{ data: AIWorkflowTemplateMeta[] | null; error: string | null }> {
    return {
      data: [],
      error: 'Temporal.io has been removed. Use Camunda workflows instead.'
    }
  }

  async getAIWorkflowCatalog(): Promise<AIWorkflowTemplateMeta[]> {
    console.warn('Temporal.io has been removed. Use Camunda workflows instead.')
    return []
  }

  async executeAIWorkflow(
    _templateId: string,
    _inputs: Record<string, unknown>
  ): Promise<{ data: TemporalioExecution | null; error: string | null }> {
    return {
      data: null,
      error: 'Temporal.io has been removed. Use Camunda workflows instead.'
    }
  }

  async getExecutionStatus(
    _workflowId: string,
    _runId?: string
  ): Promise<TemporalioExecutionStatus> {
    console.warn('Temporal.io has been removed. Use Camunda workflows instead.')
    return {
      status: 'FAILED',
      error: 'Temporal.io has been removed. Use Camunda workflows instead.'
    }
  }
}

export function useTemporalioService() {
  return useMemo(() => new TemporalioService(), [])
}
