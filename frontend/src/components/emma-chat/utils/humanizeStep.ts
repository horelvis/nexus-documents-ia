/**
 * Pure function that converts raw LangGraph reasoning_steps into
 * user-friendly ActivityStep[] for display in the ActivityTimeline.
 *
 * Rules:
 * - Rewrite (actual reformulation) → shown with new query text
 * - Memory recall → shown with doc count
 * - A `tool_call` followed by a matching `tool_result` merges into one completed step
 * - A standalone `tool_call` (no result yet) renders as an active step
 * - Everything else (thinking, routing, response, error) → ignored
 */

export type ActivityIcon = 'search' | 'read' | 'analyze' | 'web' | 'legal' | 'write' | 'done'

export interface ActivityStep {
  id: string
  text: string
  status: 'completed' | 'active'
  icon: ActivityIcon
}

export interface RawReasoningStep {
  type: string
  content: string
  source?: string
  /** Pre-humanized label from the backend — used directly when present */
  summary?: string
}

// ─── Pipeline step patterns ──────────────────────────────────────────────────

type PipelinePattern = {
  pattern: RegExp
  text: string | ((match: RegExpMatchArray) => string)
  icon: ActivityIcon
}

const ROUTING_PATTERNS: PipelinePattern[] = [
  {
    pattern: /^Rewrite:\s*'.+'\s*→\s*'(.+)'/,
    text: (m) => `Reformulada: "${m[1]}"`,
    icon: 'analyze',
  },
  // Catch-all: skip all other routing (Intent, Rewrite pass-through, etc.)
  { pattern: /.*/, text: '', icon: 'analyze' },
]

const THINKING_PATTERNS: PipelinePattern[] = [
  {
    pattern: /^Memory recall:\s*(\d+)/,
    text: (m) => `Memoria consultada (${m[1]} docs)`,
    icon: 'search',
  },
]

function matchPipelineStep(
  step: RawReasoningStep,
  stepIdx: number,
): ActivityStep | null {
  const patterns = step.type === 'routing' ? ROUTING_PATTERNS : THINKING_PATTERNS

  for (const { pattern, text, icon } of patterns) {
    const match = step.content.match(pattern)
    if (match) {
      if (text === '') return null
      const label = typeof text === 'function' ? text(match) : text
      return { id: `step-${stepIdx}`, text: label, status: 'completed', icon }
    }
  }

  return null
}

// ─── Tool configs ────────────────────────────────────────────────────────────

/** Extract the tool name from `tool_name(args...)` */
function extractToolName(content: string): string {
  const m = content.match(/^(\w+)\(/)
  return m ? m[1] : ''
}

/** Extract query= arg from tool_call content, truncated */
function extractQuery(content: string): string {
  const m = content.match(/query=([^,)]+)/)
  if (!m) return ''
  const q = m[1].trim()
  return q.length > 40 ? q.substring(0, 37) + '...' : q
}

/** Extract document title from get_document_content result.
 *  Backend format: "**Documento: Contrato de Servicios**\n..." */
function extractDocTitle(content: string): string | null {
  const m = content.match(/\*{0,2}Documento:\s*(.+?)\*{0,2}\s*\n/)
  return m ? m[1].trim() : null
}

type ToolConfig = {
  icon: ActivityIcon
  activeText: (callContent: string) => string
  resultText: (resultContent: string) => string
}

const TOOL_CONFIGS: Record<string, ToolConfig> = {
  smart_search: {
    icon: 'search',
    activeText: (call) => {
      const q = extractQuery(call)
      return q ? `Buscando "${q}"...` : 'Buscando información...'
    },
    resultText: (content) => {
      // Backend: "Se encontraron N resultados para 'query':"
      const m = content.match(/[Ss]e encontraron (\d+) resultado/)
      if (m) return `${m[1]} resultados encontrados`
      if (/[Nn]o se encontraron/.test(content)) return 'Sin resultados'
      return 'Búsqueda completada'
    },
  },
  get_document_content: {
    icon: 'read',
    activeText: () => 'Leyendo documento...',
    resultText: (content) => {
      const title = extractDocTitle(content)
      return title ? `Leí "${title}"` : 'Documento leído'
    },
  },
  structural_query: {
    icon: 'analyze',
    activeText: () => 'Consultando el grafo...',
    resultText: (content) => {
      const m = content.match(/\*{0,2}Total de documentos\*{0,2}:\s*(\d+)/)
      return m ? `${m[1]} documentos en el grafo` : 'Consulta al grafo completada'
    },
  },
  web_search: {
    icon: 'web',
    activeText: (call) => {
      const q = extractQuery(call)
      return q ? `Buscando en internet "${q}"...` : 'Buscando en internet...'
    },
    resultText: () => 'Resultados de internet obtenidos',
  },
  search_jurisprudence: {
    icon: 'legal',
    activeText: (call) => {
      const q = extractQuery(call)
      return q ? `Buscando jurisprudencia: "${q}"...` : 'Buscando jurisprudencia...'
    },
    resultText: () => 'Jurisprudencia encontrada',
  },
  generate_knowledge_report: {
    icon: 'write' as ActivityIcon,
    activeText: () => 'Generando informe de conocimiento...',
    resultText: () => 'Informe generado',
  },
}

// ─── Main export ───────────────────────────────────────────────────────────────

export function humanizeSteps(steps: RawReasoningStep[]): ActivityStep[] {
  const result: ActivityStep[] = []
  let globalIdx = 0

  let i = 0
  while (i < steps.length) {
    const step = steps[i]

    // 1. Pipeline steps — routing and thinking with recognized content
    if (step.type === 'routing' || step.type === 'thinking') {
      const pipelineStep = matchPipelineStep(step, globalIdx)
      if (pipelineStep) {
        result.push(pipelineStep)
        globalIdx++
      }
      i++
      continue
    }

    // 2. Tool calls — merge with result when available
    if (step.type === 'tool_call') {
      const toolName = extractToolName(step.content)
      const config = TOOL_CONFIGS[toolName]
      const icon: ActivityIcon = config?.icon ?? 'analyze'

      // Look for the next tool_result that belongs to this tool_call
      let resultStep: RawReasoningStep | null = null
      let resultIndex = -1
      for (let j = i + 1; j < steps.length; j++) {
        if (steps[j].type === 'tool_call') break
        if (
          steps[j].type === 'tool_result' &&
          (steps[j].source === toolName || extractToolName(step.content) === toolName)
        ) {
          resultStep = steps[j]
          resultIndex = j
          break
        }
      }

      if (resultStep !== null) {
        // Prefer backend summary → frontend regex fallback
        const text = resultStep.summary
          || (config ? config.resultText(resultStep.content) : 'Paso completado')
        result.push({ id: `step-${globalIdx}`, text, status: 'completed', icon })
        globalIdx++
        i = resultIndex + 1
      } else {
        const text = step.summary
          || config?.activeText(step.content)
          || 'Procesando...'
        result.push({ id: `step-${globalIdx}`, text, status: 'active', icon })
        globalIdx++
        i++
      }
      continue
    }

    // 3. Report progress events (report.assembling, report.generating, report.complete)
    if (step.type.startsWith('report.')) {
      const reportLabels: Record<string, { text: string; icon: ActivityIcon }> = {
        'report.assembling': { text: 'Recopilando datos del grafo...', icon: 'search' },
        'report.generating': { text: 'Generando informe...', icon: 'write' },
        'report.complete': { text: 'Informe generado', icon: 'done' },
      }
      const label = reportLabels[step.type]
      if (label) {
        const status = step.type === 'report.complete' ? 'completed' : 'active' as const
        result.push({ id: `step-${globalIdx}`, text: label.text, status, icon: label.icon })
        globalIdx++
      }
      i++
      continue
    }

    // 4. Everything else — skip
    i++
  }

  return result
}
