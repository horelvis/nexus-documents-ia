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
  | 'hitl_review'
  | 'verified_progress'
  | 'verified_result'
  | 'predictive_result'
  | 'docgen_result'
  | 'forge_result'

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
  // Legal graph integration (for BOE legislation sources)
  boe_id?: string           // BOE identifier (e.g., "BOE-A-2015-11430")
  graph_link?: string       // Deep link to knowledge tree (e.g., "/admin/knowledge-tree?focus=BOE-A-2015-11430")
  source_type?: string      // "public_knowledge" | "tenant" | etc.
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

// ── HITL Protocol Types (Phase 1) ──

export interface ActionRequest {
  name: string
  args: Record<string, unknown>
  description?: string
}

export interface ReviewConfig {
  allowed_decisions: ('approve' | 'edit' | 'reject')[]
  editable_fields?: string[]
}

export interface HITLReviewRequest {
  type: 'hitl_review'
  action_request: ActionRequest
  review_config: ReviewConfig
}

export interface HITLClarificationRequest {
  type: 'clarification'
  question: string
  options: Array<{ label: string; value: string }>
}

export interface HITLConfirmationRequest {
  type: 'confirmation'
  question: string
  options: Array<{ label: string; value: string }>
}

export type InterruptValue =
  | HITLReviewRequest
  | HITLClarificationRequest
  | HITLConfirmationRequest

export type HITLDecision =
  | { type: 'approve' }
  | { type: 'edit'; edited_args: Record<string, unknown> }
  | { type: 'reject'; message?: string }

export interface WorkflowStep {
  index: number
  description: string
  agent: string
  status: 'pending' | 'in_progress' | 'completed' | 'error'
  findings_count?: number
  execution_time_ms?: number
  error?: string
}

// Semantic step types — human-readable action categories
export type SLMThinkingStepType =
  | 'searching'      // Search in documents/legislation/jurisprudence/internet
  | 'reading'        // Reading a specific document
  | 'analyzing'      // Domain analysis
  | 'querying'       // Structural query
  | 'browsing'       // Web search
  | 'listing'        // Listing sources
  | 'connecting'     // External connector query
  | 'preparing'      // Preparing final response
  | 'search_result'  // Search results summary
  | 'doc_read'       // Document read confirmation
  | 'thinking'       // LLM reasoning (secondary)
  | 'error'          // Error / quality gate
  // Swarm types
  | 'swarm_decompose'
  | 'swarm_worker'
  | 'swarm_worker_done'
  | 'swarm_synthesize'

export interface SLMThinkingStep {
  step: number
  type: SLMThinkingStepType
  content: string
  detail?: string
  entities?: string[]
  confidence?: number
}

// ReasoningStep uses same semantic types
export type ReasoningStepType = SLMThinkingStepType

export interface ReasoningStep {
  type: ReasoningStepType
  content: string
  detail?: string
  confidence?: number
  entities?: string[]
  source?: string
  timestamp_ms?: number
  metadata?: Record<string, unknown>
}

// Verified Generation types
export type VerifiedClaimStatus = 'generating' | 'verifying' | 'verified' | 'rejected' | 'corrected' | 'review'

export type VerificationType = 'fidelity_only' | 'corroborated' | 'independent'

export interface VerifiedClaimInfo {
  claim_id: string
  claim_number: number
  total_expected: number
  claim_text: string
  status: VerifiedClaimStatus
  confidence?: number
  evidence_count?: number
  original_text?: string
  evidence_sources?: VerifiedSource[]
  verification_type?: VerificationType
  verification_reason?: string
  /** HITL: whether this claim needs human review (below confidence threshold) */
  needs_review?: boolean
  /** HITL: whether this claim was auto-approved (above threshold) */
  auto_approved?: boolean
}

export interface VerifiedSource {
  id: string
  title?: string
  source?: string
  url?: string
  roj?: string
  ecli?: string
}

export interface DoiValidation {
  doi: string
  valid: boolean
  context?: string
  metadata?: {
    title?: string
    authors?: string[]
    year?: number
    journal?: string
    type?: string
  }
}

export interface VerifiedGenerationMetadata {
  session_id: string
  tenant_id?: string
  topic: string
  claims: VerifiedClaimInfo[]
  current_phase: 'generating' | 'verifying' | 'complete' | 'review'
  verified_count: number
  rejected_count: number
  total_claims: number
  document_text?: string
  execution_time_ms?: number
  average_confidence?: number
  sources?: VerifiedSource[]
  doi_validations?: DoiValidation[]
  source_filenames?: string[]
  source_summary?: string
  /** HITL: number of claims requiring review */
  needs_review_count?: number
  /** HITL: confidence threshold used for flagging */
  confidence_threshold?: number
}

// Predictive Analysis types
export type PredictiveFactorStatus = 'extracting' | 'verifying' | 'weighted' | 'rejected'

export interface PredictiveMatchInfo {
  document_id: string
  document_title?: string
  text_excerpt: string
  similarity_score: number
  outcome: string
  supports_factor: boolean
  source: string
  url?: string
  roj?: string
  ecli?: string
  date?: string
  resolution_type?: string
  ponente?: string
}

export interface PredictiveSource {
  id: string
  title?: string
  source: string
  url?: string
  roj?: string
  ecli?: string
  date?: string
  resolution_type?: string
  ponente?: string
}

export interface PredictiveFactorInfo {
  factor_id: string
  factor_number: number
  total_expected: number
  factor_type: string
  description: string
  status: PredictiveFactorStatus
  weight?: number
  confidence?: number
  outcome?: string
  evidence_count?: number
  supporting_matches?: PredictiveMatchInfo[]
}

export interface PredictiveAnalysisMetadata {
  session_id: string
  tenant_id?: string
  case_description: string
  factors: PredictiveFactorInfo[]
  current_phase: 'extracting' | 'verifying' | 'synthesizing' | 'complete'
  weighted_count: number
  rejected_count: number
  total_factors: number
  probability?: number
  primary_outcome?: string
  outcome_probabilities?: Record<string, number>
  recommendation?: string
  disclaimer?: string
  execution_time_ms?: number
  sources?: PredictiveSource[]
}

export interface DocGenMetadata {
  document_text: string
  document_type: string
  pending_fields: string[]
  sources_used: string[]
  execution_time_ms?: number
  download_url?: string
  generated_doc_id?: string
}

// --- Document Forge (template-based document modification) ---

export type ForgeFieldType = 'text' | 'date' | 'number' | 'currency' | 'name' | 'address' | 'email' | 'phone' | 'enum'
export type ForgeSessionStatus = 'analyzed' | 'prepared' | 'rendered' | 'persisted'
export type ForgeAction = 'analyze' | 'render' | 'persist'

export interface ForgeField {
  field_name: string
  label: string
  field_type: ForgeFieldType
  current_value: string
  required: boolean
  description?: string
  context_hint?: string
  suggested_value?: string
  options?: string[]
}

export interface ForgeOutputInfo {
  download_url: string
  size_bytes: number
  format: string
}

export interface ForgeMetadata {
  action: ForgeAction
  session_id: string
  source_title: string
  document_type: string
  confidence: number
  fields: ForgeField[]
  status: ForgeSessionStatus
  field_values?: Record<string, string>
  outputs?: Record<string, ForgeOutputInfo>
  created_at?: string
  updated_at?: string
  fields_filled?: number
  document_title?: string
  document_id?: string
  gcs_paths?: Record<string, string>
  weaviate_indexed?: boolean
}

export interface EmmaMessage {
  id: string
  type: EmmaMessageType
  content: string
  timestamp: Date
  verified?: VerifiedGenerationMetadata
  predictive?: PredictiveAnalysisMetadata
  docgen?: DocGenMetadata
  forge?: ForgeMetadata
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
    agent_reasoning?: string  // Explanation of why this agent was selected
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
    // Human-in-the-Loop review (HITL Protocol Phase 1)
    hitl_review?: HITLReviewRequest
    // LangGraph chain-of-thought
    slmIsThinking?: boolean
    slmThinkingSteps?: SLMThinkingStep[]
    stage?: string
    // Humanized reasoning explanation (from explain node)
    explanation?: string
    // Raw reasoning steps for ActivityTimeline
    rawReasoningSteps?: Array<{ type: string; content: string; source?: string }>
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
    // Interleaved thinking / structural_step fields
    step_type?: ReasoningStepType
    content?: string
    entities?: string[]
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
  onSendQuery: (query: string, attachments?: Attachment[]) => Promise<void>
  isLoading?: boolean
  disabled?: boolean
  placeholder?: string
  className?: string
  maxAttachments?: number  // Default: 10
}

// ============================================================================
// Attachment Types
// ============================================================================

export type AttachmentSource = 'indexed' | 'upload'

export interface BaseAttachment {
  id: string
  name: string
  type: AttachmentSource
  fileType?: string
  size?: number
}

export interface IndexedAttachment extends BaseAttachment {
  type: 'indexed'
  documentId: string
  connectorType?: string
  previewUrl?: string
}

export interface UploadedAttachment extends BaseAttachment {
  type: 'upload'
  file: File
  uploadStatus: 'pending' | 'uploading' | 'ready' | 'error'
  tempId?: string
}

export type Attachment = IndexedAttachment | UploadedAttachment

// Attachment limits and validation
export const ATTACHMENT_LIMITS = {
  maxAttachments: 10,
  maxFileSizeMB: 50,
  maxFileSizeBytes: 50 * 1024 * 1024, // 50 MB
  allowedMimeTypes: [
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'text/plain',
    'image/png',
    'image/jpeg',
    'image/jpg',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  ],
  allowedExtensions: ['.pdf', '.doc', '.docx', '.txt', '.png', '.jpg', '.jpeg', '.xls', '.xlsx'],
}

// File type to icon/color mapping
export const FILE_TYPE_CONFIG: Record<string, { icon: string; color: string; label: string }> = {
  'application/pdf': { icon: 'pdf', color: 'text-red-500', label: 'PDF' },
  'application/msword': { icon: 'doc', color: 'text-blue-500', label: 'DOC' },
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': { icon: 'docx', color: 'text-blue-500', label: 'DOCX' },
  'text/plain': { icon: 'txt', color: 'text-gray-500', label: 'TXT' },
  'image/png': { icon: 'image', color: 'text-green-500', label: 'PNG' },
  'image/jpeg': { icon: 'image', color: 'text-green-500', label: 'JPG' },
  'image/jpg': { icon: 'image', color: 'text-green-500', label: 'JPG' },
  'application/vnd.ms-excel': { icon: 'xls', color: 'text-emerald-600', label: 'XLS' },
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': { icon: 'xlsx', color: 'text-emerald-600', label: 'XLSX' },
}

export function getFileTypeConfig(mimeType?: string | null, extension?: string | null) {
  if (mimeType && FILE_TYPE_CONFIG[mimeType]) {
    return FILE_TYPE_CONFIG[mimeType]
  }
  // Fallback to extension-based detection
  const ext = extension?.toLowerCase()
  if (ext === '.pdf' || ext === 'pdf') return FILE_TYPE_CONFIG['application/pdf']
  if (ext === '.doc' || ext === 'doc') return FILE_TYPE_CONFIG['application/msword']
  if (ext === '.docx' || ext === 'docx') return FILE_TYPE_CONFIG['application/vnd.openxmlformats-officedocument.wordprocessingml.document']
  if (ext === '.txt' || ext === 'txt') return FILE_TYPE_CONFIG['text/plain']
  if (ext === '.png' || ext === 'png') return FILE_TYPE_CONFIG['image/png']
  if (ext === '.jpg' || ext === 'jpg' || ext === '.jpeg' || ext === 'jpeg') return FILE_TYPE_CONFIG['image/jpeg']
  if (ext === '.xls' || ext === 'xls') return FILE_TYPE_CONFIG['application/vnd.ms-excel']
  if (ext === '.xlsx' || ext === 'xlsx') return FILE_TYPE_CONFIG['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']

  return { icon: 'file', color: 'text-muted-foreground', label: 'FILE' }
}
