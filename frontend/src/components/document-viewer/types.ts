import type { DocGenMetadata, VerifiedGenerationMetadata, PredictiveAnalysisMetadata } from '@/lib/types/emma'

/**
 * Document type for the unified DocumentViewer.
 * Named "ViewerDocument" to avoid collision with DOM's global Document
 * and the project's DocumentInfo type.
 */
export type ViewerDocumentType = 'docgen' | 'verified' | 'predictive' | 'generic'

export interface ViewerDocument {
  id: string
  title: string
  type: ViewerDocumentType
  /** Markdown content — used by DocumentPage when no children are provided */
  content?: string
  /** Date string for the document header */
  date: string
  /** Subtitle or metadata line (e.g. "Documento legal · 1.2s") */
  subtitle?: string
  /** Execution time in ms (shown in footer) */
  executionTimeMs?: number
}

// ── Bridge functions ───────────────────────────────────────────

function formatDate(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')} ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`
}

export function docGenToViewerDocument(metadata: DocGenMetadata): ViewerDocument {
  return {
    id: `docgen-${Date.now()}`,
    title: metadata.document_type || 'Documento Generado',
    type: 'docgen',
    content: metadata.document_text,
    date: formatDate(),
    subtitle: metadata.document_type || 'Documento legal',
    executionTimeMs: metadata.execution_time_ms,
  }
}

export function verifiedToViewerDocument(metadata: VerifiedGenerationMetadata): ViewerDocument {
  return {
    id: `verified-${metadata.session_id}`,
    title: 'Informe de Verificación',
    type: 'verified',
    date: formatDate(),
    subtitle: metadata.topic,
    executionTimeMs: metadata.execution_time_ms,
  }
}

export function predictiveToViewerDocument(metadata: PredictiveAnalysisMetadata): ViewerDocument {
  return {
    id: `predictive-${metadata.session_id || Date.now()}`,
    title: 'Informe de Análisis Predictivo',
    type: 'predictive',
    date: formatDate(),
    subtitle: metadata.case_description || 'N/A',
    executionTimeMs: metadata.execution_time_ms,
  }
}
