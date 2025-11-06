"use client"

import { useApiClient } from '../api-client'

// Types for Workflow services
export interface ContractData {
  contractId: string
  employeeName: string
  contractType: string
  expirationDate: string
  position: string
  performanceRating: string
  currentSalary?: string
}

export interface ExtractedElements {
  agents: Array<{
    name: string
    confidence: number
  }>
  tasks: Array<{
    description: string
    confidence: number
  }>
  conditions: Array<{
    condition: string
    confidence: number
  }>
  process_info: Array<{
    info: string
    confidence: number
  }>
}

export interface ValidatedBPMN {
  original_bpmn: string
  optimized_bpmn: string
  legal_compliance_points: string[]
  recommendations: string[]
  identified_risks: string[]
  emma_confidence: number
}

export interface ExecutionPlan {
  execution_steps: string[]
  timeline: {
    total_duration: string
  }
  stakeholders: Record<string, string>
  automated_actions: string[]
}

export interface BPMNGenerationResult {
  success: boolean
  message: string
  data?: {
    contract_id: string
    process_description: string
    extracted_elements: ExtractedElements
    generated_bpmn: string
    validated_bpmn: ValidatedBPMN
    execution_plan: ExecutionPlan
    created_at: string
  }
  performance_note?: string
  architecture_note?: string
}

export interface ProcessGenerationRequest {
  process_description: string
  tenant_id: string
  process_type: string
  context?: Record<string, any>
}

export interface ContractRenewalRequest {
  contract_id: string
  tenant_id: string
  user_id: string
  force_regenerate?: boolean
}

export interface WorkflowStats {
  totalProcesses: number
  activeProcesses: number
  completedToday: number
  avgCompletionTime: string
  successRate: number
  costSavings: string
}

export interface RecentProcess {
  id: string
  name: string
  type: string
  status: 'completed' | 'in_progress' | 'pending_review'
  completedAt?: string
  currentStep?: string
  progress?: number
  decision?: string
}

export interface ProcessTemplate {
  id: string
  name: string
  description: string
  category: string
  estimatedTime: string
  steps: number
  usage: number
  rating: number
  lastUpdated: string
  tags: string[]
  complexity: 'simple' | 'intermediate' | 'advanced'
}

export interface HealthStatus {
  status: 'healthy' | 'degraded' | 'unhealthy'
  service?: string
  details?: {
    service: string
    initialized: boolean
    timestamp: string
    ollama_service: string
    emma_ai_service: string
  }
  message?: string
}

export function useWorkflowsService() {
  const apiClient = useApiClient()

  // Health check
  const checkHealth = async (): Promise<HealthStatus> => {
    return apiClient.get<HealthStatus>('/bpmn-ai/health')
  }

  // Demo contract renewal (with fast/full mode)
  const demoContractRenewal = async (fastMode: boolean = true): Promise<BPMNGenerationResult> => {
    const params = new URLSearchParams({ fast: fastMode.toString() })
    return apiClient.post<BPMNGenerationResult>(`/bpmn-ai/demo/contract-renewal?${params}`)
  }

  // Generate BPMN from description
  const generateBPMN = async (request: ProcessGenerationRequest): Promise<BPMNGenerationResult> => {
    return apiClient.post<BPMNGenerationResult>('/bpmn-ai/generate-bpmn', request)
  }

  // Generate contract renewal process
  const generateContractRenewal = async (
    contractId: string, 
    request: ContractRenewalRequest
  ): Promise<BPMNGenerationResult> => {
    return apiClient.post<BPMNGenerationResult>(`/bpmn-ai/contracts/${contractId}/renewal`, request)
  }

  // Execute contract renewal process
  const executeContractRenewal = async (
    contractId: string,
    tenantId: string,
    userId: string
  ): Promise<{ success: boolean; message: string; status: string }> => {
    const params = new URLSearchParams({ 
      tenant_id: tenantId, 
      user_id: userId 
    })
    return apiClient.post(`/bpmn-ai/contracts/${contractId}/execute?${params}`)
  }

  // Get contract BPMN
  const getContractBPMN = async (
    contractId: string,
    tenantId: string
  ): Promise<BPMNGenerationResult> => {
    const params = new URLSearchParams({ tenant_id: tenantId })
    return apiClient.get<BPMNGenerationResult>(`/bpmn-ai/contracts/${contractId}/bpmn?${params}`)
  }

  // Workflow Templates API
  const getWorkflowTemplates = async (): Promise<ProcessTemplate[]> => {
    const response = await apiClient.get<any[]>('/workflow-templates')
    return response.map(template => ({
      id: template.id,
      name: template.name,
      description: template.description,
      category: template.category || 'general',
      estimatedTime: `${template.estimated_duration_days || 7} días`,
      steps: template.workflow_definition?.steps?.length || 0,
      usage: template.usage_count || 0,
      rating: 4.5, // Mock rating for now
      lastUpdated: new Date(template.updated_at || template.created_at).toLocaleDateString(),
      tags: template.tags || [],
      complexity: template.complexity || 'intermediate'
    }))
  }

  const getWorkflowStats = async (): Promise<WorkflowStats> => {
    try {
      const [templates, executions] = await Promise.all([
        apiClient.get<any[]>('/workflow-templates'),
        apiClient.get<any[]>('/workflow-executions')
      ])
      
      const activeProcesses = executions.filter(e => e.status === 'running' || e.status === 'pending').length
      const completedToday = executions.filter(e => {
        const today = new Date().toDateString()
        return e.status === 'completed' && new Date(e.completed_at).toDateString() === today
      }).length
      
      const completedExecutions = executions.filter(e => e.status === 'completed' && e.completed_at)
      const avgDays = completedExecutions.length > 0 
        ? completedExecutions.reduce((acc, exec) => {
            const days = Math.ceil((new Date(exec.completed_at).getTime() - new Date(exec.created_at).getTime()) / (1000 * 60 * 60 * 24))
            return acc + days
          }, 0) / completedExecutions.length
        : 0
      
      return {
        totalProcesses: templates.length,
        activeProcesses,
        completedToday,
        avgCompletionTime: `${avgDays.toFixed(1)} días`,
        successRate: 94.2, // Mock for now
        costSavings: "€12,450" // Mock for now
      }
    } catch (error) {
      console.error('Error fetching workflow stats:', error)
      // Fallback to mock data
      return {
        totalProcesses: 0,
        activeProcesses: 0,
        completedToday: 0,
        avgCompletionTime: "-- días",
        successRate: 0,
        costSavings: "€0"
      }
    }
  }

  const getRecentProcesses = async (): Promise<RecentProcess[]> => {
    try {
      const executions = await apiClient.get<any[]>('/workflow-executions')
      
      return executions
        .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
        .slice(0, 10) // Last 10 executions
        .map(exec => {
          const getRelativeTime = (date: string) => {
            const now = new Date()
            const past = new Date(date)
            const diffMs = now.getTime() - past.getTime()
            const diffHours = Math.floor(diffMs / (1000 * 60 * 60))
            const diffDays = Math.floor(diffHours / 24)
            
            if (diffHours < 1) return "Hace menos de 1 hora"
            if (diffHours < 24) return `Hace ${diffHours} horas`
            return `Hace ${diffDays} días`
          }
          
          const statusMap = {
            'completed': 'completed',
            'running': 'in_progress', 
            'pending': 'pending_review',
            'failed': 'pending_review'
          }
          
          return {
            id: exec.id,
            name: exec.template_name || 'Proceso Sin Nombre',
            type: exec.template_category || 'General',
            status: statusMap[exec.status as keyof typeof statusMap] || 'pending_review',
            completedAt: exec.completed_at ? getRelativeTime(exec.completed_at) : undefined,
            currentStep: exec.current_step,
            progress: exec.progress_percentage || 0,
            decision: exec.final_status === 'completed' ? 'COMPLETADO' : undefined
          }
        })
    } catch (error) {
      console.error('Error fetching recent processes:', error)
      return []
    }
  }

  const getProcessTemplates = async (): Promise<ProcessTemplate[]> => {
    // Use the real API call
    return getWorkflowTemplates()
  }
  
  // Workflow Executions API
  const executeWorkflowTemplate = async (templateId: string, inputData: any): Promise<any> => {
    return apiClient.post('/workflow-executions', {
      template_id: templateId,
      input_data: inputData,
      context: {
        executed_from: 'frontend'
      }
    })
  }
  
  const getWorkflowExecution = async (executionId: string): Promise<any> => {
    return apiClient.get(`/workflow-executions/${executionId}`)
  }
  
  const getWorkflowExecutionLogs = async (executionId: string): Promise<any> => {
    return apiClient.get(`/workflow-executions/${executionId}/logs`)
  }

  return {
    // BPMN AI methods (legacy)
    checkHealth,
    demoContractRenewal,
    generateBPMN,
    generateContractRenewal,
    executeContractRenewal,
    getContractBPMN,
    
    // Workflow Templates & Executions API
    getWorkflowTemplates,
    getWorkflowStats,
    getRecentProcesses,
    getProcessTemplates,
    executeWorkflowTemplate,
    getWorkflowExecution,
    getWorkflowExecutionLogs,
  }
}