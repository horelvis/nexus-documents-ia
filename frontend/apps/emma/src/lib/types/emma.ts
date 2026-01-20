/**
 * Type definitions for Emma Chat Components (On-Premise)
 */

export type EmmaMessageType =
  | 'user'
  | 'result'
  | 'text'
  | 'error'
  | 'warning'
  | 'info'
  | 'progress'
  | 'clarification'

export interface Citation {
  id?: string
  document?: string
  title?: string
  url?: string
  page?: number
  excerpt?: string
  relevance?: number
}

export interface DocumentInfo {
  name: string
  id?: string
  url?: string
  previewUrl?: string
  collection?: string
  createdAt?: string
  author?: string
  fileType?: string
  relevanceScore?: number
}

export interface ClarificationOption {
  label: string
  value: string
  description?: string
}

export interface ClarificationData {
  question: string
  header?: string
  options: ClarificationOption[]
  multi_select?: boolean
  severity?: 'info' | 'warning' | 'critical'
  type?: 'clarification' | 'confirmation' | 'suggestion'
}

export interface WorkflowStep {
  index: number
  description: string
  agent: string
  status: 'pending' | 'in_progress' | 'completed' | 'error'
  findings_count?: number
  execution_time_ms?: number
  error?: string
}

export interface EmmaMessage {
  id: string
  type: EmmaMessageType
  content: string
  timestamp: Date
  metadata?: {
    confidence_score?: number
    decision_path?: string[]
    tools_used?: string[]
    execution_time_ms?: number
    processing_time?: number
    sources?: Citation[]
    citations?: Citation[]
    agent_flow?: string[]
    suggestions?: string[]
    documents?: DocumentInfo[]
    // Progress streaming fields
    progress?: number
    step?: number
    total_steps?: number
    agent?: string
    plan_id?: string
    workflow_steps?: WorkflowStep[]
    isStreaming?: boolean // Flag indicating content is being streamed
    streaming_text?: string // Accumulated streamed answer (tokens)
    // Error handling fields
    errorType?: string
    canRetry?: boolean
    failedQuery?: string
    // Human-in-the-Loop clarification
    clarification?: ClarificationData
  }
  suggestions?: string[]
  isStreaming?: boolean
}

// Stream event from backend
export interface EmmaStreamEvent {
  event: string
  data: {
    message?: string
    text?: string // Token text for streaming events
    progress?: number
    step?: number
    total_steps?: number
    agent?: string
    plan_id?: string
    steps?: Array<{ index: number; description: string; agent: string }>
    answer?: string
    final_result?: {
      summary?: string
      confidence_score?: number
      decision_path?: string[]
      tools_used?: string[]
    }
    confidence_score?: number
    execution_time_ms?: number
    decision_path?: string[]
    tools_used?: string[]
    findings_count?: number
    error?: string
    success?: boolean
    session_id?: string
    elapsed_ms?: number
    // Clarification fields
    question?: string
    header?: string
    options?: ClarificationOption[]
    multi_select?: boolean
    severity?: 'info' | 'warning' | 'critical'
  }
}

// Query request
export interface EmmaQueryRequest {
  query: string
  session_id: string
  tenant_id: string
  enable_debug?: boolean
  context?: Record<string, any>
}

// Props interfaces
export interface EmmaChatProps {
  className?: string
  initialQuery?: string
  onClose?: () => void
  /** External messages (controlled mode) */
  messages?: EmmaMessage[]
  /** Callback when messages change (controlled mode) */
  onMessagesChange?: (messages: EmmaMessage[]) => void
  /** Current conversation ID */
  conversationId?: string | null
}

export interface EmmaRenderChatProps {
  messages: EmmaMessage[]
  isLoading?: boolean
  error?: string | null
  onFeedback?: (messageId: string, feedback: 'positive' | 'negative') => void
  onSuggestionClick?: (suggestion: string) => void
  onRetry?: (failedQuery: string) => void
  onClarificationSubmit?: (messageId: string, selectedValues: string[]) => void
  onDocumentClick?: (doc: DocumentInfo) => void
  onPreviewClick?: (doc: DocumentInfo) => void
  className?: string
}

export interface EmmaQueryInputProps {
  onSendQuery: (query: string) => Promise<void>
  isLoading?: boolean
  disabled?: boolean
  placeholder?: string
  className?: string
}
