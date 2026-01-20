// Type definitions for Emma Chat Components

export interface EmmaQueryInputProps {
  onSendQuery: (query: string, route?: string, mimick?: boolean) => Promise<void>
  isLoading?: boolean
  disabled?: boolean
  className?: string
  placeholder?: string
  documentId?: string
  enableMentions?: boolean
}

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

export interface EmmaMarkdownFormatProps {
  content: string
  citations?: Citation[]
  variant?: "primary" | "secondary" | "highlight"
  className?: string
}

export type EmmaMessageType = "user" | "query" | "result" | "text" | "error" | "warning" | "info" | "self_healing_error" | "system" | "progress" | "clarification"

// Human-in-the-Loop clarification option
export interface ClarificationOption {
  label: string
  value: string
  description?: string
}

// Clarification request data (from HITL tools)
export interface ClarificationData {
  question: string
  header?: string
  options: ClarificationOption[]
  multi_select?: boolean
  severity?: 'info' | 'warning' | 'critical'
  type?: 'clarification' | 'confirmation' | 'suggestion'
}

export interface ChainOfThoughtData {
  decision_trace: Array<{
    step: number
    node_id: string
    reasoning: string
    tools_considered: string[]
    tools_selected: string[]
    confidence: number
    execution_time_ms: number
  }>
  reasoning_steps: string[]
  tools_selected: string[]
  enhanced_query?: string
  documents_context: number
}

// Workflow step tracking for progress display
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
    agent_flow?: Array<{
      agent?: string
      action?: string
      result?: string
    }> | string[]
    suggestions?: string[]
    documents?: DocumentInfo[]
    debug_data?: ChainOfThoughtData | any
    // Progress streaming fields
    progress?: number
    step?: number
    total_steps?: number
    agent?: string
    plan_id?: string
    workflow_steps?: WorkflowStep[]
    // Error handling fields (i18n keys)
    errorType?: string
    errorTitleKey?: string
    errorMessageKey?: string
    canRetry?: boolean
    failedQuery?: string
    // Human-in-the-Loop clarification fields
    clarification?: ClarificationData
  }
  suggestions?: string[]
  isStreaming?: boolean
  isCollapsed?: boolean
}

export interface EmmaRenderChatProps {
  messages: EmmaMessage[]
  isLoading?: boolean
  error?: string | null
  socketStatus?: "connected" | "disconnected" | "connecting"
  onFeedback?: (messageId: string, feedback: "positive" | "negative") => void
  onSuggestionClick?: (suggestion: string) => void
  onDocumentClick?: (doc: DocumentInfo) => void
  onPreviewClick?: (doc: DocumentInfo) => void
  onRetry?: (failedQuery: string) => void
  // Human-in-the-Loop clarification handler
  onClarificationSubmit?: (messageId: string, selectedValues: string[]) => void
  currentView?: "chat" | "code" | "result"
  onViewChange?: (view: "chat" | "code" | "result") => void
  className?: string
  isAdmin?: boolean
}

export interface DisplayRendererProps {
  message: EmmaMessage
  onDocumentClick?: (doc: DocumentInfo) => void
  onPreviewClick?: (doc: DocumentInfo) => void
  isAdmin?: boolean
}

export interface EmmaSession {
  session_id: string
  messages: EmmaMessage[]
  created_at: Date
}

export interface EmmaChatProps {
  tenantId?: string
  className?: string
  initialMessage?: string
  onClose?: () => void
  isAdmin?: boolean
}

// API Response types
export interface EmmaApiResponse {
  query: string
  answer: string | string[] | any
  session_id: string
  tenant_id: string
  decision_path?: string[]
  tools_used?: string[]
  data?: any
  visualization?: any
  confidence_score?: number
  execution_time_ms?: number
  iterations?: number
  learning_applied?: boolean
  citations?: any[]
  suggestions?: string[]
}

// Backward compatibility aliases
export type ElysiaQueryInputProps = EmmaQueryInputProps
export type ElysiaMarkdownFormatProps = EmmaMarkdownFormatProps
export type ElysiaMessageType = EmmaMessageType
export type ElysiaMessage = EmmaMessage
export type ElysiaRenderChatProps = EmmaRenderChatProps
export type ElysiaSession = EmmaSession
export type ElysiaChatProps = EmmaChatProps
export type ElysiaApiResponse = EmmaApiResponse
