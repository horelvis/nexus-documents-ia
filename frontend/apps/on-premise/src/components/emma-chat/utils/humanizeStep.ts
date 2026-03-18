/**
 * Pure function that converts raw LangGraph reasoning_steps into
 * user-friendly ActivityStep[] for display in the ActivityTimeline.
 *
 * Rules:
 * - `thinking` and `routing` steps are silently ignored
 * - A `tool_call` followed by a matching `tool_result` merges into one completed step
 * - A standalone `tool_call` (no result yet) renders as an active step
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
}

// ─── Internal helpers ──────────────────────────────────────────────────────────

/** Extract the tool name from a tool_call content string like `tool_name(args...)` */
function extractToolName(content: string): string {
  const match = content.match(/^(\w+)\(/)
  return match ? match[1] : ''
}

type ToolConfig = {
  icon: ActivityIcon
  activeText: string
  resultText: (content: string) => string
}

const TOOL_CONFIGS: Record<string, ToolConfig> = {
  smart_search: {
    icon: 'search',
    activeText: 'Buscando información...',
    resultText: (content) => {
      const match = content.match(/Found (\d+) results/)
      return match ? `Encontré ${match[1]} documentos relevantes` : 'Documentos encontrados'
    },
  },
  get_document_content: {
    icon: 'read',
    activeText: 'Leyendo documento...',
    resultText: (content) => {
      // Extract a filename: a word (no spaces) containing a dot followed by 2-5 chars extension
      const fileMatch = content.match(/\b([\w\-.]+\.\w{2,5})\b/)
      return fileMatch ? `Leí ${fileMatch[1]}` : 'Documento leído'
    },
  },
  structural_query: {
    icon: 'analyze',
    activeText: 'Consultando el grafo de conocimiento...',
    resultText: (content) => {
      const match = content.match(/Total de documentos\*{0,2}:\s*(\d+)/)
      return match ? `El grafo reportó ${match[1]} documentos` : 'Consulta al grafo completada'
    },
  },
  web_search: {
    icon: 'web',
    activeText: 'Buscando en internet...',
    resultText: () => 'Resultados de internet obtenidos',
  },
  search_jurisprudence: {
    icon: 'legal',
    activeText: 'Buscando jurisprudencia...',
    resultText: () => 'Jurisprudencia encontrada',
  },
}

const IGNORED_TYPES = new Set(['thinking', 'routing'])

// ─── Main export ───────────────────────────────────────────────────────────────

/**
 * Converts an array of raw LangGraph reasoning steps into ActivityStep[].
 *
 * Merging strategy:
 *  - Iterates sequentially; when a `tool_call` is encountered, look-ahead for
 *    the next `tool_result` with a matching source/tool name.
 *  - If found → emit one completed step, advance past both.
 *  - If not found → emit one active step (in-flight tool call).
 */
export function humanizeSteps(steps: RawReasoningStep[]): ActivityStep[] {
  const result: ActivityStep[] = []

  // Filter out ignored step types upfront for cleaner indexing
  const relevant = steps.filter((s) => !IGNORED_TYPES.has(s.type))

  let i = 0
  while (i < relevant.length) {
    const step = relevant[i]

    if (step.type === 'tool_call') {
      const toolName = extractToolName(step.content)
      const config = TOOL_CONFIGS[toolName]
      const icon: ActivityIcon = config?.icon ?? 'analyze'

      // Look for the next tool_result that belongs to this tool_call
      // (same tool name, appears before any other tool_call)
      let resultStep: RawReasoningStep | null = null
      let resultIndex = -1
      for (let j = i + 1; j < relevant.length; j++) {
        if (relevant[j].type === 'tool_call') {
          // Another tool_call before any result — stop looking
          break
        }
        if (
          relevant[j].type === 'tool_result' &&
          (relevant[j].source === toolName || extractToolName(step.content) === toolName)
        ) {
          resultStep = relevant[j]
          resultIndex = j
          break
        }
      }

      if (resultStep !== null) {
        // Merged completed step
        const text = config
          ? config.resultText(resultStep.content)
          : 'Procesando...'
        result.push({
          id: `step-${i}`,
          text,
          status: 'completed',
          icon,
        })
        // Skip past the result we consumed
        i = resultIndex + 1
      } else {
        // Active (in-flight) step
        const text = config?.activeText ?? 'Procesando...'
        result.push({
          id: `step-${i}`,
          text,
          status: 'active',
          icon,
        })
        i += 1
      }
    } else if (step.type === 'tool_result') {
      // Orphaned tool_result not consumed by a preceding tool_call — skip silently
      i += 1
    } else {
      // Any other step type not in ignored list but also not tool_call/result — skip
      i += 1
    }
  }

  return result
}
