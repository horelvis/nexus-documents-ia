"use client"

/**
 * Temporalio Microservice Client
 * Direct connection to the Temporalio microservice for AI-enhanced workflows
 */

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

class TemporalioService {
  private baseURL: string
  private apiKey: string

  constructor() {
    // Direct connection to Temporalio microservice
    this.baseURL = process.env.NEXT_PUBLIC_TEMPORALIO_SERVICE_URL || 'http://localhost:8010'
    this.apiKey = process.env.NEXT_PUBLIC_API_KEY || 'nxs_dev_GYCa7km7zmibtf54yzA9NwPMj4fAYFGt'
  }

  private async makeRequest<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.baseURL}${endpoint}`
    
    const response = await fetch(url, {
      ...options,
      headers: {
        'Authorization': `Bearer ${this.apiKey}`,
        'Content-Type': 'application/json',
        ...options.headers,
      },
    })

    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(`Temporalio API error ${response.status}: ${errorText}`)
    }

    return response.json()
  }

  async checkHealth(): Promise<TemporalioHealthStatus> {
    return this.makeRequest<TemporalioHealthStatus>('/health')
  }

  async getTemplates(): Promise<TemporalioTemplate[]> {
    return this.makeRequest<TemporalioTemplate[]>('/workflow-templates')
  }

  async getTemplate(templateId: string): Promise<TemporalioTemplate> {
    return this.makeRequest<TemporalioTemplate>(`/workflow-templates/${templateId}`)
  }

  async executeWorkflow(
    templateId: string, 
    tenantId: string, 
    inputData: Record<string, any>
  ): Promise<TemporalioExecution> {
    return this.makeRequest<TemporalioExecution>('/workflow-executions/start', {
      method: 'POST',
      body: JSON.stringify({
        template_id: templateId,
        tenant_id: tenantId,
        input_data: inputData,
      }),
    })
  }

  async getExecutionStatus(workflowId: string): Promise<TemporalioExecutionStatus> {
    return this.makeRequest<TemporalioExecutionStatus>(`/workflow-executions/${workflowId}`)
  }

  async cancelExecution(workflowId: string): Promise<{ message: string }> {
    return this.makeRequest<{ message: string }>(`/workflow-executions/${workflowId}/cancel`, {
      method: 'POST',
    })
  }

  async getExecutionHistory(workflowId: string): Promise<any> {
    return this.makeRequest(`/workflow-executions/${workflowId}/history`)
  }

  // Enhanced workflow helpers
  async getAIEnhancedTemplates(): Promise<TemporalioTemplate[]> {
    const templates = await this.getTemplates()
    return templates.filter(t => 
      t.name.toLowerCase().includes('inteligente') || 
      t.name.toLowerCase().includes('ai') ||
      t.agent_types_used?.length > 0
    )
  }

  async executeLegalAdvisoryWorkflow(
    tenantId: string, 
    clientName: string, 
    caseType: string, 
    description: string,
    priority: 'low' | 'medium' | 'high' | 'urgent' = 'medium'
  ): Promise<TemporalioExecution> {
    return this.executeWorkflow('ai-legal-advisory-template', tenantId, {
      client_name: clientName,
      case_type: caseType,
      description: description,
      priority: priority,
      case_value: priority === 'urgent' ? 'high' : 'medium'
    })
  }

  async executeDocumentProcessingWorkflow(
    tenantId: string,
    documentContent: string,
    documentType: 'contract' | 'legal_brief' | 'report' | 'correspondence' | 'other',
    analysisDepth: 'basic' | 'standard' | 'deep' = 'standard'
  ): Promise<TemporalioExecution> {
    return this.executeWorkflow('ai-document-processing-template', tenantId, {
      document_content: documentContent,
      document_type: documentType,
      analysis_depth: analysisDepth
    })
  }
}

// Export singleton instance
export const temporalioService = new TemporalioService()

// React hook for using Temporalio service
export function useTemporalioService() {
  return {
    checkHealth: () => temporalioService.checkHealth(),
    getTemplates: () => temporalioService.getTemplates(),
    getTemplate: (templateId: string) => temporalioService.getTemplate(templateId),
    executeWorkflow: (templateId: string, tenantId: string, inputData: any) => 
      temporalioService.executeWorkflow(templateId, tenantId, inputData),
    getExecutionStatus: (workflowId: string) => temporalioService.getExecutionStatus(workflowId),
    cancelExecution: (workflowId: string) => temporalioService.cancelExecution(workflowId),
    getExecutionHistory: (workflowId: string) => temporalioService.getExecutionHistory(workflowId),
    
    // Enhanced methods
    getAIEnhancedTemplates: () => temporalioService.getAIEnhancedTemplates(),
    executeLegalAdvisoryWorkflow: (
      tenantId: string, 
      clientName: string, 
      caseType: string, 
      description: string,
      priority?: 'low' | 'medium' | 'high' | 'urgent'
    ) => temporalioService.executeLegalAdvisoryWorkflow(tenantId, clientName, caseType, description, priority),
    executeDocumentProcessingWorkflow: (
      tenantId: string,
      documentContent: string,
      documentType: 'contract' | 'legal_brief' | 'report' | 'correspondence' | 'other',
      analysisDepth?: 'basic' | 'standard' | 'deep'
    ) => temporalioService.executeDocumentProcessingWorkflow(tenantId, documentContent, documentType, analysisDepth),
  }
}