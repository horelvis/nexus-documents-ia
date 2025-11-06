// Type definitions for Elysia Chat Components

export interface ElysiaQueryInputProps {
  onSendQuery: (query: string, route?: string, mimick?: boolean) => Promise<void>
  isLoading?: boolean
  disabled?: boolean
  className?: string
  placeholder?: string
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

export interface ElysiaMarkdownFormatProps {
  content: string
  citations?: Citation[]
  variant?: "primary" | "secondary" | "highlight"
  className?: string
}

export type ElysiaMessageType = "user" | "query" | "result" | "text" | "error" | "warning" | "info" | "self_healing_error" | "system"

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

export interface ElysiaMessage {
  id: string
  type: ElysiaMessageType
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
    debug_data?: ChainOfThoughtData
  }
  suggestions?: string[]
  isStreaming?: boolean
  isCollapsed?: boolean
}

export interface ElysiaRenderChatProps {
  messages: ElysiaMessage[]
  isLoading?: boolean
  error?: string | null
  socketStatus?: "connected" | "disconnected" | "connecting"
  onFeedback?: (messageId: string, feedback: "positive" | "negative") => void
  onSuggestionClick?: (suggestion: string) => void
  onDocumentClick?: (doc: DocumentInfo) => void
  onPreviewClick?: (doc: DocumentInfo) => void
  currentView?: "chat" | "code" | "result"
  onViewChange?: (view: "chat" | "code" | "result") => void
  className?: string
  isAdmin?: boolean
}

export interface DisplayRendererProps {
  message: ElysiaMessage
  onDocumentClick?: (doc: DocumentInfo) => void
  onPreviewClick?: (doc: DocumentInfo) => void
  isAdmin?: boolean
}

export interface ElysiaSession {
  session_id: string
  messages: ElysiaMessage[]
  created_at: Date
}

export interface ElysiaChatProps {
  tenantId?: string
  className?: string
  initialMessage?: string
  onClose?: () => void
  isAdmin?: boolean
}

// API Response types
export interface ElysiaApiResponse {
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