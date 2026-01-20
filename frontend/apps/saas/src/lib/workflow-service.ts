"use client"

import { useCallback, useMemo } from 'react'
import { useApiClient } from './api-client'

// ============ Types ============

export interface ProcessDefinition {
  id: string
  key: string
  name?: string
  description?: string
  version: number
  version_tag?: string
  category?: string
  deployment_id: string
  tenant_id?: string
  suspended: boolean
}

export interface ProcessInstance {
  id: string
  definition_id: string
  definition_key?: string
  business_key?: string
  tenant_id?: string
  ended: boolean
  suspended: boolean
  variables?: Record<string, any>
}

export interface WorkflowTask {
  id: string
  name: string
  assignee?: string
  created?: string
  due?: string
  follow_up?: string
  description?: string
  execution_id: string
  owner?: string
  parent_task_id?: string
  priority: number
  process_definition_id: string
  process_instance_id: string
  task_definition_key: string
  form_key?: string
  tenant_id?: string
  suspended: boolean
  variables?: Record<string, any>
}

export interface SignerInfo {
  name: string
  email: string
  role?: string
  order?: number
}

export interface StartDocumentApprovalRequest {
  document_id: string
  approver_id: string
  signers?: SignerInfo[]
  message?: string
  require_signature?: boolean
}

export interface ApprovalDecisionRequest {
  approved: boolean
  reason?: string
  signers?: SignerInfo[]
}

export interface Deployment {
  id: string
  name: string
  deployment_time?: string
  source?: string
  tenant_id?: string
}

export interface WorkflowHealth {
  status: string
  camunda_url: string
  engine_name?: string
  version?: string
  workers_running: number
  active_topics: string[]
}

// ============ Service Hook ============

export function useWorkflowService() {
  const apiClient = useApiClient()

  // ============ Health ============

  const getHealth = useCallback(async () => {
    return apiClient.get<WorkflowHealth>('/workflows/health')
  }, [apiClient])

  // ============ Deployments ============

  const getDeployments = useCallback(async (params?: {
    name?: string
    skip?: number
    limit?: number
  }) => {
    const queryParams = new URLSearchParams()
    if (params?.name) queryParams.set('name', params.name)
    if (params?.skip) queryParams.set('skip', params.skip.toString())
    if (params?.limit) queryParams.set('limit', params.limit.toString())

    const query = queryParams.toString()
    return apiClient.get<{ deployments: Deployment[]; total: number }>(
      `/workflows/deployments${query ? `?${query}` : ''}`
    )
  }, [apiClient])

  const deployProcess = useCallback(async (data: {
    name: string
    bpmn_xml: string
    source?: string
  }) => {
    return apiClient.post<Deployment>('/workflows/deployments', data)
  }, [apiClient])

  const deleteDeployment = useCallback(async (deploymentId: string, cascade = true) => {
    return apiClient.delete(`/workflows/deployments/${deploymentId}?cascade=${cascade}`)
  }, [apiClient])

  // ============ Process Definitions ============

  const getProcessDefinitions = useCallback(async (params?: {
    key?: string
    latest_only?: boolean
  }) => {
    const queryParams = new URLSearchParams()
    if (params?.key) queryParams.set('key', params.key)
    if (params?.latest_only !== undefined) queryParams.set('latest_only', params.latest_only.toString())

    const query = queryParams.toString()
    return apiClient.get<{ definitions: ProcessDefinition[]; total: number }>(
      `/workflows/definitions${query ? `?${query}` : ''}`
    )
  }, [apiClient])

  const getProcessDefinitionXml = useCallback(async (key: string) => {
    return apiClient.get<{ bpmn20_xml: string }>(`/workflows/definitions/${key}/xml`)
  }, [apiClient])

  // ============ Process Instances ============

  const startProcess = useCallback(async (data: {
    process_key: string
    business_key?: string
    variables?: Record<string, any>
  }) => {
    return apiClient.post<ProcessInstance>('/workflows/instances', data)
  }, [apiClient])

  const getProcessInstances = useCallback(async (params?: {
    process_key?: string
    business_key?: string
    active_only?: boolean
    skip?: number
    limit?: number
  }) => {
    const queryParams = new URLSearchParams()
    if (params?.process_key) queryParams.set('process_key', params.process_key)
    if (params?.business_key) queryParams.set('business_key', params.business_key)
    if (params?.active_only !== undefined) queryParams.set('active_only', params.active_only.toString())
    if (params?.skip) queryParams.set('skip', params.skip.toString())
    if (params?.limit) queryParams.set('limit', params.limit.toString())

    const query = queryParams.toString()
    return apiClient.get<{ instances: ProcessInstance[]; total: number }>(
      `/workflows/instances${query ? `?${query}` : ''}`
    )
  }, [apiClient])

  const getProcessInstance = useCallback(async (instanceId: string) => {
    return apiClient.get<ProcessInstance>(`/workflows/instances/${instanceId}`)
  }, [apiClient])

  const cancelProcessInstance = useCallback(async (instanceId: string) => {
    return apiClient.delete(`/workflows/instances/${instanceId}`)
  }, [apiClient])

  // ============ Tasks ============

  const getMyTasks = useCallback(async (params?: {
    process_key?: string
    process_instance_id?: string
    skip?: number
    limit?: number
  }) => {
    const queryParams = new URLSearchParams()
    queryParams.set('assigned_to_me', 'true')
    if (params?.process_key) queryParams.set('process_key', params.process_key)
    if (params?.process_instance_id) queryParams.set('process_instance_id', params.process_instance_id)
    if (params?.skip) queryParams.set('skip', params.skip.toString())
    if (params?.limit) queryParams.set('limit', params.limit.toString())

    return apiClient.get<{ tasks: WorkflowTask[]; total: number }>(
      `/workflows/tasks?${queryParams.toString()}`
    )
  }, [apiClient])

  const getAvailableTasks = useCallback(async (params?: {
    process_key?: string
    skip?: number
    limit?: number
  }) => {
    const queryParams = new URLSearchParams()
    queryParams.set('assigned_to_me', 'false')
    queryParams.set('include_unassigned', 'true')
    if (params?.process_key) queryParams.set('process_key', params.process_key)
    if (params?.skip) queryParams.set('skip', params.skip.toString())
    if (params?.limit) queryParams.set('limit', params.limit.toString())

    return apiClient.get<{ tasks: WorkflowTask[]; total: number }>(
      `/workflows/tasks?${queryParams.toString()}`
    )
  }, [apiClient])

  const getTask = useCallback(async (taskId: string) => {
    return apiClient.get<WorkflowTask>(`/workflows/tasks/${taskId}`)
  }, [apiClient])

  const completeTask = useCallback(async (taskId: string, variables?: Record<string, any>) => {
    return apiClient.post(`/workflows/tasks/${taskId}/complete`, { variables: variables || {} })
  }, [apiClient])

  const claimTask = useCallback(async (taskId: string) => {
    return apiClient.post(`/workflows/tasks/${taskId}/claim`)
  }, [apiClient])

  const unclaimTask = useCallback(async (taskId: string) => {
    return apiClient.post(`/workflows/tasks/${taskId}/unclaim`)
  }, [apiClient])

  const assignTask = useCallback(async (taskId: string, userId: string) => {
    return apiClient.post(`/workflows/tasks/${taskId}/assign`, { user_id: userId })
  }, [apiClient])

  // ============ Document Approval Workflow ============

  const startDocumentApproval = useCallback(async (data: StartDocumentApprovalRequest) => {
    return apiClient.post<ProcessInstance>('/workflows/document-approval', data)
  }, [apiClient])

  const submitApprovalDecision = useCallback(async (taskId: string, decision: ApprovalDecisionRequest) => {
    return apiClient.post(`/workflows/tasks/${taskId}/approve`, decision)
  }, [apiClient])

  // ============ Messages ============

  const correlateMessage = useCallback(async (data: {
    message_name: string
    business_key?: string
    process_variables?: Record<string, any>
    correlation_keys?: Record<string, any>
  }) => {
    return apiClient.post('/workflows/messages', data)
  }, [apiClient])

  return useMemo(() => ({
    // Health
    getHealth,
    // Deployments
    getDeployments,
    deployProcess,
    deleteDeployment,
    // Definitions
    getProcessDefinitions,
    getProcessDefinitionXml,
    // Instances
    startProcess,
    getProcessInstances,
    getProcessInstance,
    cancelProcessInstance,
    // Tasks
    getMyTasks,
    getAvailableTasks,
    getTask,
    completeTask,
    claimTask,
    unclaimTask,
    assignTask,
    // Document Approval
    startDocumentApproval,
    submitApprovalDecision,
    // Messages
    correlateMessage,
  }), [
    getHealth,
    getDeployments,
    deployProcess,
    deleteDeployment,
    getProcessDefinitions,
    getProcessDefinitionXml,
    startProcess,
    getProcessInstances,
    getProcessInstance,
    cancelProcessInstance,
    getMyTasks,
    getAvailableTasks,
    getTask,
    completeTask,
    claimTask,
    unclaimTask,
    assignTask,
    startDocumentApproval,
    submitApprovalDecision,
    correlateMessage,
  ])
}
