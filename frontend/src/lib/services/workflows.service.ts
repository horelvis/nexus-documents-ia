"use client"

import { useApiClient } from "../api-client"
import { useCallback, useMemo } from "react"

export interface WorkflowTemplate {
  id: string
  name: string
  description: string
  category: string
  workflow_definition?: {
    steps: Array<{
      step_id: string
      step_name: string
      step_type: string
      description: string
    }>
  }
  input_schema?: {
    fields: Array<{
      field_name: string
      field_type: string
      label: string
      required: boolean
      description?: string
      options?: string[]
    }>
  }
  estimated_duration_days?: number
  tags?: string[]
  complexity?: string
}

export interface BPMNGenerationResult {
  success: boolean
  message?: string
  data?: {
    process_description?: string
    bpmn_generation?: {
      generated_bpmn?: string
      extracted_elements?: {
        agents?: Array<{ name: string; confidence: number }>
        tasks?: Array<{ description: string; confidence: number }>
        conditions?: Array<{ condition: string; confidence: number }>
        process_info?: Array<{ info: string; confidence: number }>
      }
      validated_bpmn?: {
        emma_confidence?: number
        legal_compliance_points?: string[]
        recommendations?: string[]
        identified_risks?: string[]
      }
      execution_plan?: {
        execution_steps?: string[]
        stakeholders?: Record<string, string>
        timeline?: { total_duration?: string }
        automated_actions?: string[]
      }
    }
    validated_bpmn?: boolean
    execution_plan?: any
  }
  performance_note?: string
  architecture_note?: string
}

export function useWorkflowsService() {
  const apiClient = useApiClient()

  const getWorkflowTemplates = useCallback(async (): Promise<WorkflowTemplate[]> => {
    try {
      const response = await apiClient.get<{ definitions: WorkflowTemplate[] }>("/workflows/definitions")
      return response.data?.definitions || []
    } catch (error) {
      console.error("Error fetching workflow templates:", error)
      return []
    }
  }, [apiClient])

  const executeWorkflowTemplate = useCallback(async (
    templateId: string,
    formData: Record<string, any>
  ): Promise<{ id: string }> => {
    try {
      const response = await apiClient.post<{ id: string }>("/workflows/instances", {
        process_key: templateId,
        variables: formData
      })
      return response.data || { id: "" }
    } catch (error) {
      console.error("Error executing workflow:", error)
      throw error
    }
  }, [apiClient])

  const generateBPMN = useCallback(async (params: {
    process_description: string
    process_type: string
    context?: {
      duration?: string
      automation_level?: string
      stakeholders?: string[]
      additional_context?: string
    }
  }): Promise<BPMNGenerationResult> => {
    // This would call an AI service to generate BPMN
    // For now, return a placeholder
    return {
      success: false,
      message: "BPMN generation not yet implemented - use Camunda workflows"
    }
  }, [])

  const demoContractRenewal = useCallback(async (fullDemo: boolean = false): Promise<BPMNGenerationResult> => {
    // Demo placeholder
    return {
      success: false,
      message: "Demo not yet implemented - use Camunda workflows"
    }
  }, [])

  return useMemo(() => ({
    getWorkflowTemplates,
    executeWorkflowTemplate,
    generateBPMN,
    demoContractRenewal
  }), [getWorkflowTemplates, executeWorkflowTemplate, generateBPMN, demoContractRenewal])
}
