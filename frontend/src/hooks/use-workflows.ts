"use client"

import { useState, useCallback, useEffect } from 'react'
import { useWorkflowService, ProcessInstance, WorkflowTask, ProcessDefinition } from '@/lib/workflow-service'

export interface WorkflowStats {
  total_workflows: number
  active_workflows: number
  completed_today: number
  failed_workflows: number
}

export interface WorkflowExecution {
  id: string
  workflow_type: string
  status: string
  started_at: string
  completed_at?: string
  input_data?: Record<string, any>
  output_data?: Record<string, any>
  error?: string
}

export function useWorkflows() {
  const workflowService = useWorkflowService()

  const [workflows, setWorkflows] = useState<WorkflowExecution[]>([])
  const [tasks, setTasks] = useState<WorkflowTask[]>([])
  const [definitions, setDefinitions] = useState<ProcessDefinition[]>([])
  const [stats, setStats] = useState<WorkflowStats | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Transform ProcessInstance to WorkflowExecution for backwards compatibility
  const transformInstance = (instance: ProcessInstance): WorkflowExecution => ({
    id: instance.id,
    workflow_type: instance.definition_key || 'unknown',
    status: instance.ended ? 'completed' : instance.suspended ? 'suspended' : 'running',
    started_at: new Date().toISOString(), // Camunda doesn't return this directly
    input_data: instance.variables,
  })

  // Refresh workflows (process instances)
  const refreshWorkflows = useCallback(async () => {
    setIsLoading(true)
    setError(null)

    try {
      const response = await workflowService.getProcessInstances({ active_only: false })

      if (response.error) {
        setError(response.error)
      } else if (response.data) {
        const transformed = response.data.instances.map(transformInstance)
        setWorkflows(transformed)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load workflows')
    } finally {
      setIsLoading(false)
    }
  }, [workflowService])

  // Get workflow stats
  const getWorkflowStats = useCallback(async () => {
    try {
      // Get active instances
      const activeResponse = await workflowService.getProcessInstances({ active_only: true })
      const allResponse = await workflowService.getProcessInstances({ active_only: false })

      const activeCount = activeResponse.data?.total || 0
      const totalCount = allResponse.data?.total || 0

      // Calculate completed today (approximate)
      const completedToday = allResponse.data?.instances.filter(
        i => i.ended && new Date(i.variables?.completed_at || '').toDateString() === new Date().toDateString()
      ).length || 0

      // Get failed from variables (approximate)
      const failed = allResponse.data?.instances.filter(
        i => i.variables?.error || i.variables?.failed
      ).length || 0

      setStats({
        total_workflows: totalCount,
        active_workflows: activeCount,
        completed_today: completedToday,
        failed_workflows: failed,
      })
    } catch (err) {
      console.error('Failed to get workflow stats:', err)
    }
  }, [workflowService])

  // Start a new workflow
  const startWorkflow = useCallback(async (workflowType: string, inputData: Record<string, any>) => {
    setIsLoading(true)
    setError(null)

    try {
      const response = await workflowService.startProcess({
        process_key: workflowType,
        variables: inputData,
        business_key: inputData.business_key,
      })

      if (response.error) {
        throw new Error(response.error)
      }

      return response.data
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to start workflow'
      setError(message)
      throw err
    } finally {
      setIsLoading(false)
    }
  }, [workflowService])

  // Cancel a workflow
  const cancelWorkflow = useCallback(async (workflowId: string) => {
    setIsLoading(true)
    setError(null)

    try {
      const response = await workflowService.cancelProcessInstance(workflowId)

      if (response.error) {
        throw new Error(response.error)
      }

      // Remove from local state
      setWorkflows(prev => prev.filter(w => w.id !== workflowId))
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to cancel workflow'
      setError(message)
      throw err
    } finally {
      setIsLoading(false)
    }
  }, [workflowService])

  // Get workflow status
  const getWorkflowStatus = useCallback(async (workflowId: string) => {
    try {
      const response = await workflowService.getProcessInstance(workflowId)

      if (response.error) {
        throw new Error(response.error)
      }

      return response.data ? transformInstance(response.data) : null
    } catch (err) {
      console.error('Failed to get workflow status:', err)
      return null
    }
  }, [workflowService])

  // Get my tasks
  const refreshTasks = useCallback(async () => {
    try {
      const response = await workflowService.getMyTasks()

      if (response.data) {
        setTasks(response.data.tasks)
      }
    } catch (err) {
      console.error('Failed to refresh tasks:', err)
    }
  }, [workflowService])

  // Get available tasks (unassigned)
  const getAvailableTasks = useCallback(async () => {
    try {
      const response = await workflowService.getAvailableTasks()
      return response.data?.tasks || []
    } catch (err) {
      console.error('Failed to get available tasks:', err)
      return []
    }
  }, [workflowService])

  // Complete a task
  const completeTask = useCallback(async (taskId: string, variables?: Record<string, any>) => {
    try {
      const response = await workflowService.completeTask(taskId, variables)

      if (response.error) {
        throw new Error(response.error)
      }

      // Refresh tasks
      await refreshTasks()
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to complete task'
      setError(message)
      throw err
    }
  }, [workflowService, refreshTasks])

  // Claim a task
  const claimTask = useCallback(async (taskId: string) => {
    try {
      const response = await workflowService.claimTask(taskId)

      if (response.error) {
        throw new Error(response.error)
      }

      await refreshTasks()
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to claim task'
      setError(message)
      throw err
    }
  }, [workflowService, refreshTasks])

  // Get process definitions
  const refreshDefinitions = useCallback(async () => {
    try {
      const response = await workflowService.getProcessDefinitions({ latest_only: true })

      if (response.data) {
        setDefinitions(response.data.definitions)
      }
    } catch (err) {
      console.error('Failed to refresh definitions:', err)
    }
  }, [workflowService])

  // Start document approval workflow
  const startDocumentApproval = useCallback(async (
    documentId: string,
    approverId: string,
    options?: {
      requireSignature?: boolean
      signers?: Array<{ name: string; email: string; role?: string }>
      message?: string
    }
  ) => {
    try {
      const response = await workflowService.startDocumentApproval({
        document_id: documentId,
        approver_id: approverId,
        require_signature: options?.requireSignature || false,
        signers: options?.signers,
        message: options?.message,
      })

      if (response.error) {
        throw new Error(response.error)
      }

      return response.data
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to start approval workflow'
      setError(message)
      throw err
    }
  }, [workflowService])

  // Submit approval decision
  const submitApprovalDecision = useCallback(async (
    taskId: string,
    approved: boolean,
    options?: {
      reason?: string
      signers?: Array<{ name: string; email: string; role?: string }>
    }
  ) => {
    try {
      const response = await workflowService.submitApprovalDecision(taskId, {
        approved,
        reason: options?.reason,
        signers: options?.signers,
      })

      if (response.error) {
        throw new Error(response.error)
      }

      await refreshTasks()
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to submit decision'
      setError(message)
      throw err
    }
  }, [workflowService, refreshTasks])

  return {
    // State
    workflows,
    tasks,
    definitions,
    stats,
    isLoading,
    error,

    // Workflow operations
    startWorkflow,
    cancelWorkflow,
    getWorkflowStatus,
    refreshWorkflows,
    getWorkflowStats,

    // Task operations
    refreshTasks,
    getAvailableTasks,
    completeTask,
    claimTask,

    // Definition operations
    refreshDefinitions,

    // Document approval shortcuts
    startDocumentApproval,
    submitApprovalDecision,
  }
}
