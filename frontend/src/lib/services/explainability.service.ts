"use client"

/**
 * Explainability Service
 *
 * Types and API client for the Explainability UI.
 * Consumes endpoints from emma-agent-service (port 8009)
 * proxied through /api/v1/emma/explainability/...
 */

// --- Types ---

export interface ExplainabilityNode {
  id: string
  type: 'entity' | 'document' | 'claim' | 'law' | 'contradiction'
  label: string
  properties: {
    domain?: string
    semantic_type?: string
    confidence?: number
    excerpt?: string
    boe_id?: string
    source_document_id?: string
    [key: string]: unknown
  }
}

export interface ExplainabilityEdge {
  id: string
  source: string
  target: string
  type: string
  properties: { confidence?: number; [key: string]: unknown }
}

export interface ExplainabilityGraphResponse {
  nodes: ExplainabilityNode[]
  edges: ExplainabilityEdge[]
  stats: {
    total_entities: number
    total_documents: number
    total_claims: number
    total_laws: number
    total_contradictions: number
  }
}

export interface ReasoningTimelineStep {
  index: number
  type: 'thinking' | 'search' | 'observation' | 'tool_call' | 'tool_result' | 'reflection' | 'answer' | 'error'
  content: string
  detail?: string
  source?: string
  timestamp_ms: number
  duration_ms?: number
  confidence?: number
  related_node_ids?: string[]
}

export interface ReasoningTraceResponse {
  message_id: string
  thread_id: string
  timeline: ReasoningTimelineStep[]
  evidence_graph: { nodes: ExplainabilityNode[]; edges: ExplainabilityEdge[] }
  total_execution_ms: number
  tools_used: string[]
  sources_cited: number
}

// --- API Client ---

import { apiClient } from "@/lib/api-client"

export const explainabilityApi = {
  /** GET /emma/explainability/graph — Full explainability graph */
  async getExplainabilityGraph() {
    return apiClient.get<ExplainabilityGraphResponse>(
      `/emma/explainability/graph`
    )
  },

  /** GET /emma/explainability/trace/{threadId}/{messageIndex} — Reasoning trace for a message */
  async getReasoningTrace(threadId: string, messageIndex: number) {
    return apiClient.get<ReasoningTraceResponse>(
      `/emma/explainability/trace/${encodeURIComponent(threadId)}/${messageIndex}`
    )
  },
}
