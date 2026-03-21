/**
 * Document Forge Detection Utility
 *
 * Detects whether an Emma response contains a forge_document tool result
 * and extracts the session_id from the answer text for API fetching.
 *
 * Pattern mirrors docgen-detector.ts but simpler: we detect by tool name
 * and extract the session_id from the synthesized answer text.
 */
import type { ForgeMetadata, ForgeAction } from '@/lib/types/emma'

// Session ID pattern: `abc123-def456` or similar UUID format in backticks
const SESSION_ID_PATTERN = /Session ID:\s*`([^`]+)`/i

// Forge action detection from answer text
const ANALYZE_MARKERS = /campos detectados|campos modificables|he detectado/i
const RENDER_MARKERS = /documento generado|campos rellenados|descargar/i
const PERSIST_MARKERS = /guardado permanentemente|indexado en/i

interface ForgeDetectionInput {
  content: string
  toolsUsed?: string[]
}

/**
 * Checks if the response is a forge_document result.
 * Primary detection: `forge_document` in tools_used.
 */
export function isForgeResult({ content, toolsUsed = [] }: ForgeDetectionInput): boolean {
  return toolsUsed.includes('forge_document')
}

/**
 * Extracts forge metadata from the synthesized answer text.
 * The session_id is extracted from text, then the full data
 * should be fetched via GET /forge/sessions/{id}/info.
 */
export function extractForgeMetadata(content: string, executionTimeMs?: number): ForgeMetadata | null {
  const sessionMatch = content.match(SESSION_ID_PATTERN)
  if (!sessionMatch) return null

  const sessionId = sessionMatch[1]

  // Detect action from answer text markers
  let action: ForgeAction = 'analyze'
  if (PERSIST_MARKERS.test(content)) action = 'persist'
  else if (RENDER_MARKERS.test(content)) action = 'render'

  // Extract basic info from text (will be enriched by API call)
  const titleMatch = content.match(/Documento (?:analizado|generado):\s*\*\*([^*]+)\*\*/i)
  const confidenceMatch = content.match(/Confianza:\s*(\d+)%/i)
  const typeMatch = content.match(/Tipo:\s*(\S+)/i)

  return {
    action,
    session_id: sessionId,
    source_title: titleMatch?.[1] || '',
    document_type: typeMatch?.[1] || '',
    confidence: confidenceMatch ? parseInt(confidenceMatch[1]) / 100 : 0,
    fields: [], // Will be populated by API call
    status: action === 'render' ? 'rendered' : action === 'persist' ? 'persisted' : 'analyzed',
  }
}
