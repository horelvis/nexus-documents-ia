// Type definitions for Elysia Chat Components

export interface ElysiaQueryInputProps {
  onSendQuery: (query: string, route?: string, mimick?: boolean) => Promise<void>
  isLoading?: boolean
  disabled?: boolean
  className?: string
  placeholder?: string
}

export interface Citation {
  id: string
  title: string
  url?: string
  page?: number
  excerpt?: string
}

export interface ElysiaMarkdownFormatProps {
  content: string
  citations?: Citation[]
  variant?: "primary" | "secondary" | "highlight"
  className?: string
}

export type ElysiaMessageType = "user" | "result" | "text" | "error" | "warning" | "self_healing_error" | "system"

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
    citations?: Citation[]
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
  currentView?: "chat" | "code" | "result"
  onViewChange?: (view: "chat" | "code" | "result") => void
  className?: string
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