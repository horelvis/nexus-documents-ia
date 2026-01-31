import { useAuth } from '@clerk/nextjs'
import { useCallback, useMemo } from 'react'
import { API_CONFIG } from '../config'

// Error types for better UX
export type EmmaErrorType = 'network' | 'timeout' | 'server' | 'auth' | 'serviceUnavailable' | 'unknown'

export interface EmmaError {
  type: EmmaErrorType
  message: string
  /** i18n key for title: emma.errors.{type}.title */
  titleKey: string
  /** i18n key for message: emma.errors.{type}.message */
  messageKey: string
  canRetry: boolean
  originalError?: Error
}

/**
 * Classify errors and return i18n translation keys
 * Usage: const error = classifyError(err); t(error.titleKey); t(error.messageKey)
 */
export function classifyError(error: unknown): EmmaError {
  const err = error instanceof Error ? error : new Error(String(error))
  const message = err.message.toLowerCase()

  // Network errors (offline, DNS, connection refused)
  if (
    message.includes('failed to fetch') ||
    message.includes('network') ||
    message.includes('net::') ||
    message.includes('networkerror') ||
    message.includes('connection refused') ||
    message.includes('dns') ||
    message.includes('econnrefused')
  ) {
    return {
      type: 'network',
      message: err.message,
      titleKey: 'emma.errors.network.title',
      messageKey: 'emma.errors.network.message',
      canRetry: true,
      originalError: err
    }
  }

  // Timeout errors
  if (
    message.includes('timeout') ||
    message.includes('timed out') ||
    message.includes('aborted')
  ) {
    return {
      type: 'timeout',
      message: err.message,
      titleKey: 'emma.errors.timeout.title',
      messageKey: 'emma.errors.timeout.message',
      canRetry: true,
      originalError: err
    }
  }

  // Service unavailable (503, backend down)
  if (
    message.includes('503') ||
    message.includes('service unavailable') ||
    message.includes('unavailable') ||
    message.includes('502') ||
    message.includes('bad gateway')
  ) {
    return {
      type: 'serviceUnavailable',
      message: err.message,
      titleKey: 'emma.errors.serviceUnavailable.title',
      messageKey: 'emma.errors.serviceUnavailable.message',
      canRetry: true,
      originalError: err
    }
  }

  // Server errors (500, 502, etc.)
  if (
    message.includes('500') ||
    message.includes('internal server') ||
    message.includes('server error')
  ) {
    return {
      type: 'server',
      message: err.message,
      titleKey: 'emma.errors.server.title',
      messageKey: 'emma.errors.server.message',
      canRetry: true,
      originalError: err
    }
  }

  // Auth errors
  if (
    message.includes('401') ||
    message.includes('403') ||
    message.includes('unauthorized') ||
    message.includes('forbidden')
  ) {
    return {
      type: 'auth',
      message: err.message,
      titleKey: 'emma.errors.auth.title',
      messageKey: 'emma.errors.auth.message',
      canRetry: false,
      originalError: err
    }
  }

  // Unknown errors - still provide a friendly message
  return {
    type: 'unknown',
    message: err.message,
    titleKey: 'emma.errors.unknown.title',
    messageKey: 'emma.errors.unknown.message',
    canRetry: true,
    originalError: err
  }
}

export interface EmmaQuery {
  query: string
  session_id: string
  tenant_id: string
  context?: Record<string, any>
  enable_debug?: boolean
}

export interface DocumentAnalysisRequest {
  document_id: string
  tenant_id: string
  analysis_type?: 'legal' | 'financial' | 'compliance' | 'general'
}

export interface AnalysisRisk {
  id: string
  type: 'risk' | 'recommendation'
  severity?: 'high' | 'medium' | 'low'
  title: string
  description: string
  clause?: string
  pageNumber: number
  highlight: {
    x: number
    y: number
    width: number
    height: number
  }
}

// New interfaces for annotated PDF analysis
export interface AnnotationRect {
  x0: number
  y0: number
  x1: number
  y1: number
}

export interface PDFAnnotation {
  id: string
  type: 'risk' | 'recommendation' | 'info'
  severity?: 'high' | 'medium' | 'low' | null
  title: string
  description: string
  page_number: number
  rect: AnnotationRect
  text_found: string
  confidence: number
}

export interface AnalysisRiskBackend {
  id: string
  type: string
  severity?: string
  title: string
  description: string
  quote?: string
  clause?: string
  recommendation?: string
}

export interface AnalysisRecommendationBackend {
  id: string
  type: string
  title: string
  description: string
  quote?: string
  priority?: string
  action_required?: string
}

export interface DocumentAnalysisResultBackend {
  document_id: string
  summary: string
  risks: AnalysisRiskBackend[]
  recommendations: AnalysisRecommendationBackend[]
  confidence_score: number
  analysis_type: string
  metadata?: Record<string, any>
}

export interface AnnotatedPDFResponse {
  annotated_pdf: string  // Base64 encoded PDF
  annotations: PDFAnnotation[]
  pages_annotated: number
  total_annotations: number
  failed_annotations: number
  analysis: DocumentAnalysisResultBackend
}

// Markdown document interfaces
export interface MarkdownPage {
  page_number: number
  content: string
  char_count: number
}

export interface DocumentMarkdownResponse {
  document_id: string
  full_markdown: string
  pages: MarkdownPage[]
  total_pages: number
  total_chars: number
  metadata: Record<string, any>
}

export interface AnalysisWithMarkdownResponse {
  markdown: DocumentMarkdownResponse
  annotations: PDFAnnotation[]
  annotated_markdown: string
  analysis: DocumentAnalysisResultBackend
}

export interface DocumentAnalysisResponse {
  document_id: string
  document_title: string
  analysis_type: string
  summary: string
  risks: AnalysisRisk[]
  recommendations: AnalysisRisk[]
  confidence_score: number
  execution_time_ms: number
}

export interface EmmaResponse {
  query: string
  answer: string
  session_id: string
  tenant_id: string
  decision_path: string[]
  tools_used: string[]
  data: any
  visualization: any
  confidence_score: number
  execution_time_ms: number
  iterations: number
  learning_applied: boolean
}

export interface EmmaAgent {
  name: string
  description: string
  capabilities: string[]
  status: 'active' | 'inactive'
}

const normalizedBaseUrl = (API_CONFIG.BASE_URL || '').replace(/\/$/, '')
const BASE_API_URL = `${normalizedBaseUrl}${API_CONFIG.API_V1}`
const EMMA_QUERY_PATH = '/weaviate/emma/v2/query'
const EMMA_QUERY_STREAM_PATH = '/weaviate/emma/v2/query/stream'
const EMMA_TOOLS_PATH = '/weaviate/emma/tools'
const EMMA_ANALYZE_WITH_ANNOTATIONS_PATH = '/weaviate/emma/analyze-with-annotations'
const EMMA_GET_ANALYSIS_PATH = '/weaviate/emma/analysis'  // GET /analysis/{job_id}
const EMMA_DOCUMENT_MARKDOWN_PATH = '/weaviate/emma/document/markdown'
const EMMA_ANALYZE_MARKDOWN_PATH = '/weaviate/emma/analyze/markdown'
const EMMA_CLARIFICATION_RESOLVE_PATH = '/weaviate/emma/clarification/resolve'
const EMMA_CLARIFICATION_PENDING_PATH = '/weaviate/emma/clarification/pending'

// Stored analysis result (from database)
export interface StoredAnalysisResult {
  id: string
  document_id: string
  tenant_id: string
  created_by: string | null
  status: 'pending' | 'processing' | 'completed' | 'failed'
  progress: number
  current_step: string | null
  error_message: string | null
  analysis_type: string
  detected_document_type: string | null
  detected_document_type_display: string | null
  detection_confidence: number | null
  plan_id: string | null
  plan_title: string | null
  total_steps: number | null
  steps_completed: number | null
  summary: string | null
  risks: AnalysisRiskBackend[]
  recommendations: AnalysisRecommendationBackend[]
  findings: Array<{
    id: string
    type: string
    severity?: string
    title: string
    description: string
    quote?: string
    legal_basis?: string
    legal_reference?: string
  }>
  annotations: PDFAnnotation[]
  execution_log: Array<Record<string, any>>
  annotated_pdf_path: string | null
  annotated_pdf_url: string | null
  confidence_score: number | null
  execution_time_ms: number | null
  started_at: string | null
  completed_at: string | null
  created_at: string | null
  updated_at: string | null
}

// Clarification option for Human-in-the-Loop UI
export interface ClarificationOption {
  label: string
  value: string
  description?: string
}

// SSE Event types from backend
export interface EmmaStreamEvent {
  event: 'start' | 'planning' | 'plan_created' | 'step_start' | 'step_complete' | 'step_error' | 'consolidating' | 'complete' | 'error' | 'token' | 'delegation' | 'first_token' | 'progress' | 'slm_thinking' | 'clarification_needed' | 'confirmation_needed' | 'suggestions_available'
  data: {
    message?: string
    progress?: number
    step?: number
    // Human-in-the-Loop clarification fields
    question?: string
    header?: string
    options?: ClarificationOption[]
    multi_select?: boolean
    severity?: 'info' | 'warning' | 'critical'
    suggestions?: Array<{ label: string; action: string; description?: string }>
    total_steps?: number
    agent?: string
    description?: string
    findings_count?: number
    execution_time_ms?: number
    error?: string
    plan_id?: string
    steps?: Array<{ index: number; description: string; agent: string }>
    final_result?: any
    answer?: string
    success?: boolean
    session_id?: string
    // Delegation event fields (when Emma uses tools)
    tool?: string
    elapsed_ms?: number
    // Progress stage tracking
    stage?: 'init' | 'loading_document' | 'analyzing' | 'context_preparation' | 'thinking' | 'searching' | 'generating'
    // slm_thinking event fields
    content?: string
    type?: string
    slmIsThinking?: boolean
    slmThinkingStep?: { step: number; type: string; content: string; entities?: string[]; confidence?: number }
    // Token streaming fields
    text?: string
    token?: string
    // Complete event fields
    confidence_score?: number
    decision_path?: string[]
    tools_used?: string[]
  }
}

// SSE Event types for analysis with annotations
export interface AnalysisStreamEvent {
  event: 'start' | 'extracting' | 'extracted' | 'planning' | 'plan_created' | 'step_start' | 'searching_legal' | 'legal_found' | 'agent_executing' | 'step_complete' | 'step_error' | 'consolidating' | 'annotating' | 'annotated' | 'complete' | 'error'
  data: {
    message?: string
    progress?: number
    step?: number
    step_index?: number
    total_steps?: number
    agent?: string
    description?: string
    legal_chars?: number
    findings?: Array<{
      type: string
      severity?: string
      title: string
      description: string
      quote?: string
    }>
    findings_count?: number
    execution_time_ms?: number
    error?: string
    plan_id?: string
    steps?: Array<{ index: number; description: string; agent: string }>
    pages?: number
    chars?: number
    total?: number
    // Complete event data
    success?: boolean
    annotated_pdf?: string
    annotations?: Array<{
      id: string
      type: string
      severity?: string
      title: string
      description: string
      page_number: number
      rect: { x0: number; y0: number; x1: number; y1: number }
      confidence: number
    }>
    pages_annotated?: number
    total_annotations?: number
    failed_annotations?: number
    analysis?: {
      document_id: string
      summary: string
      risks: Array<{
        id: string
        type: string
        severity: string
        title: string
        description: string
        quote?: string
        clause?: string
      }>
      recommendations: Array<{
        id: string
        type: string
        title: string
        description: string
        quote?: string
        priority: string
      }>
      confidence_score: number
      analysis_type: string
    }
    final_result?: any
  }
}

const fetchWithTimeout = async (url: string, options: RequestInit = {}, useEmmaTimeout: boolean = false) => {
  const controller = new AbortController()
  const timeoutMs = useEmmaTimeout
    ? (API_CONFIG.EMMA_TIMEOUT ?? 180000)  // 3 minutes for Emma operations
    : (API_CONFIG.TIMEOUT ?? 30000)
  const timeoutId: ReturnType<typeof setTimeout> = setTimeout(() => controller.abort(), timeoutMs)

  try {
    return await fetch(url, { ...options, signal: controller.signal })
  } catch (error) {
    const errorName = (error as { name?: string })?.name

    if (errorName === 'AbortError') {
      throw new Error(`Emma request timed out after ${Math.ceil(timeoutMs / 1000)}s`)
    }
    throw error
  } finally {
    clearTimeout(timeoutId)
  }
}

const parseResponse = async <T>(response: Response, defaultErrorPrefix: string): Promise<T> => {
  const rawPayload = await response.text()
  let data: any = null

  if (rawPayload) {
    try {
      data = JSON.parse(rawPayload)
    } catch {
      data = rawPayload
    }
  }

  if (!response.ok) {
    const detail =
      typeof data === 'string'
        ? data
        : data?.detail || data?.message || data?.error || ''
    const message = detail
      ? `${defaultErrorPrefix}: ${detail}`
      : `${defaultErrorPrefix} (status ${response.status})`
    throw new Error(message)
  }

  return data as T
}

export function useEmmaService() {
  const { getToken } = useAuth()
  const apiBase = BASE_API_URL

  const queryEmma = useCallback(async (query: EmmaQuery): Promise<EmmaResponse> => {
    const token = await getToken()

    const response = await fetchWithTimeout(
      `${apiBase}${EMMA_QUERY_PATH}`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token || ''}`
        },
        body: JSON.stringify(query)
      },
      true  // Use Emma timeout (3 minutes for PlanningFlow)
    )

    return await parseResponse<EmmaResponse>(response, 'Emma query failed')
  }, [getToken, apiBase])

  /**
   * Query Emma with SSE streaming for real-time progress updates.
   *
   * @param query - The query to send
   * @param onEvent - Callback for each SSE event (progress updates)
   * @returns Promise that resolves when stream completes
   */
  const queryEmmaStream = useCallback(async (
    query: EmmaQuery,
    onEvent: (event: EmmaStreamEvent) => void
  ): Promise<void> => {
    const token = await getToken()

    const response = await fetch(`${apiBase}${EMMA_QUERY_STREAM_PATH}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token || ''}`
      },
      body: JSON.stringify(query)
    })

    if (!response.ok) {
      throw new Error(`Stream request failed: ${response.status}`)
    }

    const reader = response.body?.getReader()
    if (!reader) {
      throw new Error('No response body')
    }

    const decoder = new TextDecoder()
    let buffer = ''
    let currentEvent: string | null = null
    let currentData: string | null = null

    const processLines = (lines: string[]) => {
      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEvent = line.slice(7).trim()
        } else if (line.startsWith('data: ')) {
          currentData = line.slice(6)
        } else if (line === '' && currentEvent && currentData) {
          // Empty line marks end of event
          try {
            const parsedData = JSON.parse(currentData)
            onEvent({
              event: currentEvent as EmmaStreamEvent['event'],
              data: parsedData
            })
          } catch (e) {
            console.warn('Failed to parse SSE data:', currentData)
          }
          currentEvent = null
          currentData = null
        }
      }
    }

    try {
      while (true) {
        const { done, value } = await reader.read()

        if (value) {
          buffer += decoder.decode(value, { stream: !done })
        }

        // Parse SSE events from buffer
        const lines = buffer.split('\n')
        buffer = done ? '' : (lines.pop() || '') // Keep incomplete line unless done

        processLines(lines)

        if (done) {
          // Process any remaining buffer content when stream ends
          if (buffer) {
            processLines([buffer, ''])
          }
          break
        }
      }
    } finally {
      reader.releaseLock()
    }
  }, [getToken, apiBase])

  const getAvailableAgents = useCallback(async (): Promise<EmmaAgent[]> => {
    try {
      const token = await getToken()
      const response = await fetchWithTimeout(`${apiBase}${EMMA_TOOLS_PATH}`, {
        headers: {
          'Authorization': `Bearer ${token || ''}`
        }
      })

      const data = await parseResponse<{ tools?: EmmaAgent[] }>(
        response,
        'Failed to get agents'
      )

      if (data?.tools && Array.isArray(data.tools) && data.tools.length > 0) {
        return data.tools
      }

      return [
        { name: 'text_response', description: 'Generación de respuestas de texto', capabilities: ['conversación', 'respuestas'], status: 'active' },
        { name: 'cited_summarize', description: 'Resúmenes con citas de documentos', capabilities: ['resumen', 'citas', 'documentos'], status: 'active' },
        { name: 'aggregate', description: 'Agregación de datos', capabilities: ['análisis', 'agregación'], status: 'active' },
        { name: 'query', description: 'Búsquedas avanzadas en documentos', capabilities: ['búsqueda', 'consultas'], status: 'active' },
        { name: 'visualise', description: 'Visualización de datos', capabilities: ['gráficos', 'visualización'], status: 'active' }
      ]
    } catch (error) {
      console.error('Error getting Emma agents:', error)
      return []
    }
  }, [getToken, apiBase])

  const sendMessage = useCallback(async (
    message: string,
    sessionId: string,
    tenantId: string,
    enableDebug: boolean = false,
    context?: Record<string, any>
  ): Promise<EmmaResponse> => {
    return queryEmma({
      query: message,
      session_id: sessionId,
      tenant_id: tenantId,
      enable_debug: enableDebug,
      context
    })
  }, [queryEmma])

  const getWelcomeMessage = useCallback(async (sessionId: string, tenantId: string): Promise<EmmaResponse> => {
    return queryEmma({
      query: "Genera un mensaje de bienvenida personalizado para el usuario",
      session_id: sessionId,
      tenant_id: tenantId,
      context: { is_welcome: true }
    })
  }, [queryEmma])

  /**
   * Analyze a specific document for legal risks and recommendations
   */
  const analyzeDocument = useCallback(async (
    documentId: string,
    tenantId: string,
    documentTitle: string,
    analysisType: 'legal' | 'financial' | 'compliance' | 'general' = 'legal'
  ): Promise<DocumentAnalysisResponse> => {
    const sessionId = `analysis-${documentId}-${Date.now()}`

    // Query Emma with structured analysis request
    const analysisPrompt = `Analiza el documento "${documentTitle}" (ID: ${documentId}) e identifica:

1. RIESGOS: Cláusulas problemáticas, ambigüedades legales, obligaciones excesivas, falta de límites de responsabilidad
2. RECOMENDACIONES: Mejoras sugeridas para cada riesgo identificado

Para cada hallazgo, proporciona:
- Severidad (alto/medio/bajo)
- Descripción clara del problema o recomendación
- Cláusula específica afectada si aplica

IMPORTANTE: Responde en formato estructurado para análisis legal.`

    const response = await queryEmma({
      query: analysisPrompt,
      session_id: sessionId,
      tenant_id: tenantId,
      context: {
        document_id: documentId,
        analysis_type: analysisType,
        structured_output: true
      },
      enable_debug: true
    })

    // Parse the response and extract structured data
    return parseAnalysisResponse(response, documentId, documentTitle, analysisType)
  }, [queryEmma])

  /**
   * Analyze a document and get PDF with native annotations (highlights)
   * This uses PyMuPDF in the backend to add real PDF annotations
   */
  const analyzeDocumentWithAnnotations = useCallback(async (
    documentId: string,
    tenantId: string,
    analysisType: 'legal' | 'contract' | 'compliance' = 'legal',
    pdfFile?: File
  ): Promise<AnnotatedPDFResponse> => {
    const token = await getToken()

    // Use FormData for multipart/form-data request
    const formData = new FormData()
    formData.append('document_id', documentId)
    formData.append('tenant_id', tenantId)
    formData.append('analysis_type', analysisType)

    if (pdfFile) {
      formData.append('file', pdfFile)
    }

    const response = await fetchWithTimeout(
      `${apiBase}${EMMA_ANALYZE_WITH_ANNOTATIONS_PATH}`,
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token || ''}`
          // Don't set Content-Type for FormData - browser sets it with boundary
        },
        body: formData
      },
      true  // Use Emma timeout (3 minutes for analysis)
    )

    return await parseResponse<AnnotatedPDFResponse>(
      response,
      'Analysis with annotations failed'
    )
  }, [getToken, apiBase])

  /**
   * Analyze a document with streaming progress updates.
   * Returns an async generator that yields SSE events as analysis progresses.
   */
  const analyzeDocumentWithAnnotationsStream = useCallback(async function* (
    documentId: string,
    tenantId: string,
    analysisType: 'legal' | 'contract' | 'compliance' = 'legal',
    pdfFile?: File
  ): AsyncGenerator<AnalysisStreamEvent, void, unknown> {
    const token = await getToken()

    const formData = new FormData()
    formData.append('document_id', documentId)
    formData.append('tenant_id', tenantId)
    formData.append('analysis_type', analysisType)

    if (pdfFile) {
      formData.append('file', pdfFile)
    }

    const response = await fetch(
      `${apiBase}${EMMA_ANALYZE_WITH_ANNOTATIONS_PATH}/stream`,
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token || ''}`
        },
        body: formData
      }
    )

    if (!response.ok) {
      // Try to extract detailed error from response body
      let errorDetail = ''
      try {
        const errorBody = await response.json()
        errorDetail = errorBody?.detail || errorBody?.message || errorBody?.error || ''
      } catch {
        // Response body not JSON or empty
      }

      const errorMessage = errorDetail
        ? `Error de análisis: ${errorDetail}`
        : `Error de análisis (código ${response.status})`

      throw new Error(errorMessage)
    }

    const reader = response.body?.getReader()
    if (!reader) {
      throw new Error('Response body is not readable')
    }

    const decoder = new TextDecoder()
    let buffer = ''

    let currentEvent = ''
    let currentData = ''

    const processLine = (line: string): AnalysisStreamEvent | null => {
      if (line.startsWith('event: ')) {
        currentEvent = line.slice(7).trim()
      } else if (line.startsWith('data: ')) {
        currentData = line.slice(6)
      } else if (line === '' && currentEvent && currentData) {
        try {
          const data = JSON.parse(currentData)
          const event = { event: currentEvent as AnalysisStreamEvent['event'], data }
          currentEvent = ''
          currentData = ''
          return event
        } catch (e) {
          console.warn('Failed to parse SSE data:', currentData?.slice(0, 100), e)
          currentEvent = ''
          currentData = ''
        }
      }
      return null
    }

    try {
      while (true) {
        const { done, value } = await reader.read()

        if (value) {
          buffer += decoder.decode(value, { stream: !done })
        }

        // Process complete SSE messages
        const lines = buffer.split('\n')

        if (done) {
          // Stream ended - process ALL lines including partial ones
          buffer = ''
          for (const line of lines) {
            const event = processLine(line)
            if (event) yield event
          }
          // Final flush with empty line to trigger any pending event
          const finalEvent = processLine('')
          if (finalEvent) yield finalEvent
          break
        } else {
          // Keep incomplete line in buffer for next iteration
          buffer = lines.pop() || ''
          for (const line of lines) {
            const event = processLine(line)
            if (event) yield event
          }
        }
      }
    } finally {
      reader.releaseLock()
    }
  }, [getToken, apiBase])

  /**
   * Convert a PDF document to Markdown format.
   * Uses PyMuPDF4LLM for LLM-optimized text extraction.
   */
  const getDocumentMarkdown = useCallback(async (
    pdfFile: File,
    documentId: string
  ): Promise<DocumentMarkdownResponse> => {
    const token = await getToken()

    const formData = new FormData()
    formData.append('pdf_file', pdfFile)
    formData.append('document_id', documentId)

    const response = await fetchWithTimeout(
      `${apiBase}${EMMA_DOCUMENT_MARKDOWN_PATH}`,
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token || ''}`
        },
        body: formData
      },
      true
    )

    return await parseResponse<DocumentMarkdownResponse>(
      response,
      'Failed to convert PDF to Markdown'
    )
  }, [getToken, apiBase])

  /**
   * Analyze a document and return results with Markdown view instead of PDF.
   * This is an alternative to analyzeDocumentWithAnnotations that provides
   * text-based viewing with inline annotation highlights.
   */
  const analyzeDocumentWithMarkdown = useCallback(async (
    pdfFile: File,
    documentId: string,
    tenantId: string,
    analysisType: 'legal' | 'contract' | 'compliance' = 'legal'
  ): Promise<AnalysisWithMarkdownResponse> => {
    const token = await getToken()

    const formData = new FormData()
    formData.append('pdf_file', pdfFile)
    formData.append('document_id', documentId)
    formData.append('tenant_id', tenantId)
    formData.append('analysis_type', analysisType)

    const response = await fetchWithTimeout(
      `${apiBase}${EMMA_ANALYZE_MARKDOWN_PATH}`,
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token || ''}`
        },
        body: formData
      },
      true
    )

    return await parseResponse<AnalysisWithMarkdownResponse>(
      response,
      'Analysis with markdown failed'
    )
  }, [getToken, apiBase])

  /**
   * Get a stored analysis result by job ID.
   * Use this to load previously completed analyses instead of running a new one.
   */
  const getStoredAnalysis = useCallback(async (
    jobId: string
  ): Promise<StoredAnalysisResult | null> => {
    const token = await getToken()

    try {
      const response = await fetchWithTimeout(
        `${apiBase}${EMMA_GET_ANALYSIS_PATH}/${jobId}`,
        {
          method: 'GET',
          headers: {
            'Authorization': `Bearer ${token || ''}`
          }
        },
        true
      )

      if (response.status === 404) {
        return null
      }

      return await parseResponse<StoredAnalysisResult>(
        response,
        'Failed to get stored analysis'
      )
    } catch (error) {
      console.error('Failed to get stored analysis:', error)
      return null
    }
  }, [getToken, apiBase])

  /**
   * Resolve a Human-in-the-Loop clarification request.
   * Called when user selects an option from the clarification UI.
   *
   * This is part of the OpenCode-style permission system where the system
   * (not the LLM) decides when to ask for user input.
   */
  const resolveClarification = useCallback(async (
    sessionId: string,
    tenantId: string,
    selectedValues: string[],
    requestId?: string,
    followUpQuery?: string
  ): Promise<{ success: boolean; message: string; selectedDocument?: { id: string } }> => {
    const token = await getToken()

    try {
      const response = await fetchWithTimeout(
        `${apiBase}${EMMA_CLARIFICATION_RESOLVE_PATH}`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token || ''}`
          },
          body: JSON.stringify({
            session_id: sessionId,
            tenant_id: tenantId,
            request_id: requestId,
            selected_values: selectedValues,
            follow_up_query: followUpQuery
          })
        }
      )

      return await parseResponse<{ success: boolean; message: string; selected_document?: { id: string } }>(
        response,
        'Failed to resolve clarification'
      )
    } catch (error) {
      console.error('Clarification resolution failed:', error)
      return {
        success: false,
        message: error instanceof Error ? error.message : 'Error desconocido'
      }
    }
  }, [getToken, apiBase])

  /**
   * Check if there's a pending clarification for a session.
   */
  const getPendingClarification = useCallback(async (
    sessionId: string,
    tenantId: string
  ): Promise<{ hasPending: boolean; context?: Record<string, any> }> => {
    const token = await getToken()

    try {
      const response = await fetchWithTimeout(
        `${apiBase}${EMMA_CLARIFICATION_PENDING_PATH}/${sessionId}?tenant_id=${tenantId}`,
        {
          method: 'GET',
          headers: {
            'Authorization': `Bearer ${token || ''}`
          }
        }
      )

      const data = await parseResponse<{ has_pending: boolean; context?: Record<string, any> }>(
        response,
        'Failed to get pending clarification'
      )

      return {
        hasPending: data.has_pending,
        context: data.context
      }
    } catch (error) {
      console.error('Failed to get pending clarification:', error)
      return { hasPending: false }
    }
  }, [getToken, apiBase])

  return useMemo(() => ({
    queryEmma,
    queryEmmaStream,
    getAvailableAgents,
    sendMessage,
    getWelcomeMessage,
    analyzeDocument,
    analyzeDocumentWithAnnotations,
    analyzeDocumentWithAnnotationsStream,
    getDocumentMarkdown,
    analyzeDocumentWithMarkdown,
    getStoredAnalysis,
    // Human-in-the-Loop (HITL) clarification functions
    resolveClarification,
    getPendingClarification,
  }), [queryEmma, queryEmmaStream, getAvailableAgents, sendMessage, getWelcomeMessage, analyzeDocument, analyzeDocumentWithAnnotations, analyzeDocumentWithAnnotationsStream, getDocumentMarkdown, analyzeDocumentWithMarkdown, getStoredAnalysis, resolveClarification, getPendingClarification])
}

/**
 * Parse Emma's response and extract structured analysis data
 */
function parseAnalysisResponse(
  response: EmmaResponse,
  documentId: string,
  documentTitle: string,
  analysisType: string
): DocumentAnalysisResponse {
  const answer = response.answer || ''
  const risks: AnalysisRisk[] = []
  const recommendations: AnalysisRisk[] = []

  // Extract risks and recommendations from the answer
  // Look for patterns like "## ⚠️ Riesgos" or "Riesgo Alto:" etc.
  const lines = answer.split('\n')
  let currentSection: 'risk' | 'recommendation' | null = null
  let currentItem: Partial<AnalysisRisk> | null = null
  let itemIndex = 0

  for (const line of lines) {
    const trimmedLine = line.trim()

    // Detect section headers
    if (trimmedLine.match(/riesgo|⚠️.*riesgo/i)) {
      currentSection = 'risk'
    } else if (trimmedLine.match(/recomendaci[oó]n|✅.*recomendaci/i)) {
      currentSection = 'recommendation'
    }

    // Detect severity in risks
    const highMatch = trimmedLine.match(/riesgo\s*(alto|high)/i)
    const mediumMatch = trimmedLine.match(/riesgo\s*(medio|medium)/i)
    const lowMatch = trimmedLine.match(/riesgo\s*(bajo|low)/i)

    if (highMatch || mediumMatch || lowMatch || trimmedLine.match(/^[-•*]\s+/)) {
      // Start a new item
      if (currentItem && currentItem.description) {
        // Save previous item
        const item: AnalysisRisk = {
          id: `item-${itemIndex++}`,
          type: currentItem.type || 'risk',
          severity: currentItem.severity,
          title: currentItem.title || (currentItem.type === 'risk' ? 'Riesgo Identificado' : 'Recomendación'),
          description: currentItem.description,
          pageNumber: 1, // Default to page 1
          highlight: generateHighlightPosition(itemIndex)
        }

        if (item.type === 'risk') {
          risks.push(item)
        } else {
          recommendations.push(item)
        }
      }

      // Determine severity
      let severity: 'high' | 'medium' | 'low' = 'medium'
      if (highMatch) severity = 'high'
      else if (lowMatch) severity = 'low'

      currentItem = {
        type: currentSection || 'risk',
        severity: currentSection === 'risk' ? severity : undefined,
        title: highMatch ? 'Riesgo Alto' : mediumMatch ? 'Riesgo Medio' : lowMatch ? 'Riesgo Bajo' : 'Hallazgo',
        description: trimmedLine.replace(/^[-•*]\s+/, '').replace(/riesgo\s*(alto|medio|bajo|high|medium|low):?\s*/i, '')
      }
    } else if (currentItem && trimmedLine && !trimmedLine.startsWith('#')) {
      // Append to current item description
      currentItem.description = (currentItem.description || '') + ' ' + trimmedLine
    }
  }

  // Don't forget the last item
  if (currentItem && currentItem.description) {
    const item: AnalysisRisk = {
      id: `item-${itemIndex}`,
      type: currentItem.type || 'risk',
      severity: currentItem.severity,
      title: currentItem.title || 'Hallazgo',
      description: currentItem.description.trim(),
      pageNumber: 1,
      highlight: generateHighlightPosition(itemIndex)
    }

    if (item.type === 'risk') {
      risks.push(item)
    } else {
      recommendations.push(item)
    }
  }

  // If no structured data was extracted, create items from the raw answer
  if (risks.length === 0 && recommendations.length === 0) {
    // Split answer into paragraphs and create items
    const paragraphs = answer.split(/\n\n+/).filter(p => p.trim().length > 50)

    paragraphs.slice(0, 5).forEach((para, idx) => {
      const isRisk = para.match(/riesgo|problema|falta|carece|ilegal|incumpl/i)
      const item: AnalysisRisk = {
        id: `auto-${idx}`,
        type: isRisk ? 'risk' : 'recommendation',
        severity: isRisk ? (para.match(/alto|grave|crítico/i) ? 'high' : 'medium') : undefined,
        title: isRisk ? 'Riesgo Identificado' : 'Recomendación',
        description: para.replace(/^#+\s*/, '').trim().slice(0, 300),
        pageNumber: 1,
        highlight: generateHighlightPosition(idx)
      }

      if (isRisk) {
        risks.push(item)
      } else {
        recommendations.push(item)
      }
    })
  }

  return {
    document_id: documentId,
    document_title: documentTitle,
    analysis_type: analysisType,
    summary: extractSummary(answer),
    risks,
    recommendations,
    confidence_score: response.confidence_score || 0.8,
    execution_time_ms: response.execution_time_ms || 0
  }
}

/**
 * Generate highlight position for analysis items
 * Distributes items vertically on the page with variation
 */
function generateHighlightPosition(index: number, totalItems: number = 10): AnalysisRisk['highlight'] {
  // Distribute items evenly within the visible area (15% to 85%)
  const availableHeight = 70 // 85 - 15
  const spacing = totalItems > 1 ? availableHeight / (totalItems - 1) : 0
  const baseY = 15 + (index * spacing)

  // Add slight horizontal variation for visual interest
  const xVariation = (index % 3) * 5 // 0, 5, or 10

  return {
    x: 5 + xVariation,
    y: Math.min(baseY, 85),
    width: 85 - xVariation,
    height: 6
  }
}

/**
 * Extract summary from the analysis answer
 */
function extractSummary(answer: string): string {
  // Look for summary section
  const summaryMatch = answer.match(/resumen ejecutivo[:\s]*([\s\S]*?)(?=##|$)/i)
  if (summaryMatch) {
    return summaryMatch[1].trim().slice(0, 500)
  }

  // Take first paragraph as summary
  const firstPara = answer.split(/\n\n/)[0]
  return firstPara?.replace(/^#+\s*/, '').trim().slice(0, 500) || 'Análisis completado'
}

// Backward compatibility aliases
export type ElysiaQuery = EmmaQuery
export type ElysiaResponse = EmmaResponse
export type ElysiaAgent = EmmaAgent
export const useElysiaService = useEmmaService
