/**
 * Document Generation Detection Utility
 *
 * Detects whether an Emma response is a generated legal document
 * and extracts structured metadata from it.
 */
import { DocGenMetadata } from '@/lib/types/emma'

// ── Detection patterns ──────────────────────────────────────────────

const DOC_GEN_VERBS = /(^|\s)(genera|redacta|elabora|crea|prepara|escribe|haz|hazme|draft|write|necesito que redactes|necesito un|quiero un|dame un)/

const DOC_TYPE_WORDS = /(contrato|demanda|recurso|escrito|acta|carta|convenio|acuerdo|estatuto|reglamento|poder|testamento|querella|denuncia|certificado|declaración|solicitud|reclamación|documento|modelo|plantilla|borrador)/

const CLAUSE_PATTERN = /^(?:#{1,3}\s+)?(?:CLÁUSULA|Cláusula|CLAUSULA|PRIMERA|SEGUNDA|TERCERA|CUARTA|QUINTA|SEXTA|SÉPTIMA|OCTAVA|NOVENA|DÉCIMA|\d+[\.\)]\s*[-–])/gm

const PENDING_FIELD_PATTERN = /\[[A-ZÁÉÍÓÚÜÑ\s_]{2,}\]/g

const LEGAL_SOURCE_PATTERN = /(?:Ley|Real Decreto|Estatuto|Código|Directiva|Reglamento|Orden|Convenio)[^\n.;]*/g

// ── Document type mapping ───────────────────────────────────────────

const DOC_TYPE_MAP: [string, string][] = [
  ['contrato', 'Contrato'],
  ['demanda', 'Demanda'],
  ['recurso', 'Recurso'],
  ['escrito', 'Escrito'],
  ['acta', 'Acta'],
  ['carta', 'Carta'],
  ['informe', 'Informe'],
  ['convenio', 'Convenio'],
  ['acuerdo', 'Acuerdo'],
  ['poder', 'Poder notarial'],
  ['denuncia', 'Denuncia'],
  ['querella', 'Querella'],
  ['certificado', 'Certificado'],
  ['solicitud', 'Solicitud'],
  ['reclamación', 'Reclamación'],
  ['testamento', 'Testamento'],
]

// ── Public API ──────────────────────────────────────────────────────

interface DetectionInput {
  query: string
  content: string
  toolsUsed?: string[]
  domains?: string[]
}

/**
 * Checks if the response should be rendered as a generated document.
 *
 * Primary detection is via backend signal (docgen_agent in tools_used or
 * "generate" / "docgen" in domains). The ActionIntentClassifier in the backend
 * now handles routing "genera un contrato laboral" → docgen_agent reliably.
 *
 * Client-side regex and content heuristics are kept as fallbacks only.
 */
export function isDocGenResult({ query, content, toolsUsed = [], domains = [] }: DetectionInput): boolean {
  // 1. Backend signal (primary — ActionIntentClassifier ensures this fires)
  if (toolsUsed.includes('docgen_agent') || domains.includes('docgen') || domains.includes('generate')) return true

  // 2. Query intent fallback: user explicitly asked to generate a document
  const q = query.toLowerCase().trim()
  if (DOC_GEN_VERBS.test(q) && DOC_TYPE_WORDS.test(q)) return true

  // 3. Content fallback: long structured document with clauses + placeholders
  const clauses = (content.match(CLAUSE_PATTERN) || []).length
  const fields = (content.match(PENDING_FIELD_PATTERN) || []).length
  if (content.length > 800 && clauses >= 2 && fields >= 1) return true

  return false
}

/**
 * Extracts structured metadata from a generated document response.
 */
export function extractDocGenMetadata(query: string, content: string, executionTimeMs?: number): DocGenMetadata {
  const q = query.toLowerCase()

  // Document type
  const docType = DOC_TYPE_MAP.find(([key]) => q.includes(key))?.[1] || 'Documento legal'

  // Pending fields (deduplicated)
  const pendingFields = [...new Set(content.match(PENDING_FIELD_PATTERN) || [])]

  // Legal sources (deduplicated)
  const sourcesUsed = [...new Set(content.match(LEGAL_SOURCE_PATTERN) || [])]

  return {
    document_text: content,
    document_type: docType,
    pending_fields: pendingFields,
    sources_used: sourcesUsed,
    execution_time_ms: executionTimeMs,
  }
}
