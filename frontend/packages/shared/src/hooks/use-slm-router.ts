"use client"

import { useState, useCallback, useRef } from "react"
import type {
  SLMStreamEvent,
  SLMThinkingStep,
  SLMPlanReady,
  SLMExecutionComplete,
  SLMStreamEventType
} from "../emma/types"

// =============================================================================
// Types
// =============================================================================

export interface SLMRouterState {
  /** Current thinking steps */
  thinkingSteps: SLMThinkingStep[]
  /** Whether the router is currently thinking (generating plan) */
  isThinking: boolean
  /** The generated plan (when ready) */
  planReady: SLMPlanReady | null
  /** Whether execution is in progress */
  isExecuting: boolean
  /** The execution result */
  executionResult: SLMExecutionComplete | null
  /** Any error that occurred */
  error: string | null
  /** Whether the entire process is complete */
  isComplete: boolean
}

export interface UseSLMRouterOptions {
  /** Function to get the access token */
  getAccessToken: () => string | null
  /** Base API URL */
  apiBaseUrl: string
  /** Streaming API URL (direct to backend, bypassing proxy) */
  streamingApiUrl?: string
}

export interface UseSLMRouterReturn extends SLMRouterState {
  /** Query the SLM Router with streaming chain-of-thought */
  queryWithReasoning: (
    query: string,
    tenantId: string,
    sessionId: string
  ) => Promise<SLMExecutionComplete | null>
  /** Reset the state */
  reset: () => void
}

// =============================================================================
// Initial State
// =============================================================================

const initialState: SLMRouterState = {
  thinkingSteps: [],
  isThinking: false,
  planReady: null,
  isExecuting: false,
  executionResult: null,
  error: null,
  isComplete: false
}

// =============================================================================
// Hook Implementation
// =============================================================================

/**
 * Hook for using the SLM Router with visible chain-of-thought reasoning.
 *
 * This hook manages the state of the SLM Router streaming process,
 * providing real-time updates as the router reasons about the query.
 *
 * @example
 * ```tsx
 * const {
 *   thinkingSteps,
 *   isThinking,
 *   planReady,
 *   queryWithReasoning
 * } = useSLMRouter({
 *   getAccessToken: () => sessionStorage.getItem('token'),
 *   apiBaseUrl: '/api/v1'
 * })
 *
 * // Query with visible reasoning
 * const result = await queryWithReasoning(query, tenantId, sessionId)
 * ```
 */
export function useSLMRouter(options: UseSLMRouterOptions): UseSLMRouterReturn {
  const { getAccessToken, apiBaseUrl, streamingApiUrl } = options

  const [state, setState] = useState<SLMRouterState>(initialState)

  // Use ref to track if component is mounted
  const isMountedRef = useRef(true)

  /**
   * Query the SLM Router with streaming chain-of-thought reasoning.
   *
   * Returns the execution result when complete, or null if there was an error.
   */
  const queryWithReasoning = useCallback(async (
    query: string,
    tenantId: string,
    sessionId: string
  ): Promise<SLMExecutionComplete | null> => {
    // Reset state at start
    setState({
      ...initialState,
      isThinking: true
    })

    let executionResult: SLMExecutionComplete | null = null
    const baseUrl = streamingApiUrl || apiBaseUrl
    const streamUrl = `${baseUrl}/weaviate/slm/route/stream`

    try {
      const token = getAccessToken()

      const response = await fetch(streamUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token || ''}`
        },
        body: JSON.stringify({
          query,
          tenant_id: tenantId,
          session_id: sessionId
        })
      })

      if (!response.ok) {
        let errorDetail = ''
        try {
          const errorBody = await response.json()
          errorDetail = errorBody?.detail || errorBody?.message || ''
        } catch {
          // Response body not JSON
        }
        throw new Error(errorDetail || `SLM Router stream failed: ${response.status}`)
      }

      const reader = response.body?.getReader()
      if (!reader) {
        throw new Error('No response body')
      }

      const decoder = new TextDecoder()
      let buffer = ''
      let currentEvent: string | null = null
      let currentData: string | null = null

      const processEvent = (event: SLMStreamEvent) => {
        if (!isMountedRef.current) return

        switch (event.event) {
          case 'thinking_start':
            setState(prev => ({
              ...prev,
              isThinking: true,
              error: null
            }))
            break

          case 'thinking_step':
            if (event.data.step && event.data.type && event.data.content) {
              const newStep: SLMThinkingStep = {
                step: event.data.step,
                type: event.data.type,
                content: event.data.content,
                entities: event.data.entities || [],
                confidence: event.data.confidence || 1.0
              }
              setState(prev => ({
                ...prev,
                thinkingSteps: [...prev.thinkingSteps, newStep]
              }))
            }
            break

          case 'plan_ready':
            if (event.data.route && event.data.confidence !== undefined) {
              const plan: SLMPlanReady = {
                route: event.data.route as SLMPlanReady['route'],
                confidence: event.data.confidence,
                entities_count: event.data.entities_count || 0,
                reasoning: event.data.reasoning
              }
              setState(prev => ({
                ...prev,
                isThinking: false,
                planReady: plan
              }))
            }
            break

          case 'execution_start':
            setState(prev => ({
              ...prev,
              isExecuting: true
            }))
            break

          case 'execution_complete':
            executionResult = {
              success: event.data.success ?? false,
              context_for_llm: event.data.context_for_llm,
              graph_result: event.data.graph_result,
              graph_row_count: event.data.graph_row_count,
              vector_result_count: event.data.vector_result_count,
              time_ms: event.data.time_ms || 0,
              error: event.data.error,
              clarification_question: event.data.clarification_question,
              clarification_options: event.data.clarification_options
            }
            setState(prev => ({
              ...prev,
              isExecuting: false,
              executionResult,
              isComplete: true
            }))
            break

          case 'error':
            setState(prev => ({
              ...prev,
              isThinking: false,
              isExecuting: false,
              error: event.data.error || 'Unknown error',
              isComplete: true
            }))
            break
        }
      }

      const processLines = (lines: string[]) => {
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            currentData = line.slice(6)
          } else if (line === '' && currentEvent && currentData) {
            try {
              const parsedData = JSON.parse(currentData)
              processEvent({
                event: currentEvent as SLMStreamEventType,
                data: parsedData
              })
            } catch (e) {
              console.warn('Failed to parse SLM SSE data:', currentData)
            }
            currentEvent = null
            currentData = null
          }
        }
      }

      while (true) {
        const { done, value } = await reader.read()

        if (value) {
          buffer += decoder.decode(value, { stream: !done })
        }

        const lines = buffer.split('\n')
        buffer = done ? '' : (lines.pop() || '')

        processLines(lines)

        if (done) {
          if (buffer) {
            processLines([buffer, ''])
          }
          break
        }
      }

      reader.releaseLock()
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error'
      setState(prev => ({
        ...prev,
        isThinking: false,
        isExecuting: false,
        error: errorMessage,
        isComplete: true
      }))
      return null
    }

    return executionResult
  }, [getAccessToken, apiBaseUrl, streamingApiUrl])

  /**
   * Reset the hook state.
   */
  const reset = useCallback(() => {
    setState(initialState)
  }, [])

  return {
    ...state,
    queryWithReasoning,
    reset
  }
}

export default useSLMRouter
