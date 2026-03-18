/**
 * Pure function that converts raw LangGraph reasoning_steps into
 * user-friendly ActivityStep[] for display in the ActivityTimeline.
 *
 * Rules:
 * - Known pipeline steps (routing, thinking) are shown with humanized labels
 *   based on their content patterns (classify, rewrite, memory recall)
 * - LLM internal thinking (no recognized pattern) is silently ignored
 * - A `tool_call` followed by a matching `tool_result` merges into one completed step
 * - A standalone `tool_call` (no result yet) renders as an active step
 * - `response` steps are ignored (the synthesize phase is shown by ActivityTimeline)
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

// ─── Pipeline step patterns ──────────────────────────────────────────────────
// Match known content patterns from classify, rewrite, and memory_recall nodes
// to show pipeline progression in the timeline.

type PipelinePattern = {
  pattern: RegExp
  text: string | ((match: RegExpMatchArray) => string)
  icon: ActivityIcon
}

/** Routing steps — only show when the user benefits from knowing */
const ROUTING_PATTERNS: PipelinePattern[] = [
  // Rewrite with actual reformulation — user sees their ambiguous query was improved
  {
    pattern: /^Rewrite:\s*'.+'\s*→\s*'(.+)'/,
    text: (m) => `Reformulada: "${m[1]}"`,
    icon: 'analyze',
  },
  // Everything else (Intent, Rewrite pass-through) — internal plumbing, skip
  { pattern: /.*/, text: '', icon: 'analyze' },
]

/** Thinking steps — only show memory recall for multi-turn conversations */
const THINKING_PATTERNS: PipelinePattern[] = [
  {
    pattern: /^Memory recall:\s*(\d+)/,
    text: (m) => `Memoria consultada (${m[1]} docs)`,
    icon: 'search',
  },
]

/**
 * Try to match a routing or thinking step against known pipeline patterns.
 * Returns an ActivityStep if matched, null if the step should be ignored.
 */
function matchPipelineStep(
  step: RawReasoningStep,
  stepIdx: number,
): ActivityStep | null {
  const patterns = step.type === 'routing' ? ROUTING_PATTERNS : THINKING_PATTERNS

  for (const { pattern, text, icon } of patterns) {
    const match = step.content.match(pattern)
    if (match) {
      // Empty text means "skip this step"
      if (text === '') return null
      const label = typeof text === 'function' ? text(match) : text
      return { id: `step-${stepIdx}`, text: label, status: 'completed', icon }
    }
  }

  return null // No pattern matched — ignore
}

// ─── Tool configs ────────────────────────────────────────────────────────────

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

// ─── Main export ───────────────────────────────────────────────────────────────

/**
 * Converts an array of raw LangGraph reasoning steps into ActivityStep[].
 *
 * Handles three categories:
 *  1. Pipeline steps (routing/thinking with known content patterns) → completed steps
 *  2. Tool calls → merged with results when available, or shown as active
 *  3. Everything else (LLM thinking, response, error, unknown) → ignored
 */
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
        const text = config ? config.resultText(resultStep.content) : 'Procesando...'
        result.push({ id: `step-${globalIdx}`, text, status: 'completed', icon })
        globalIdx++
        i = resultIndex + 1
      } else {
        const text = config?.activeText ?? 'Procesando...'
        result.push({ id: `step-${globalIdx}`, text, status: 'active', icon })
        globalIdx++
        i++
      }
      continue
    }

    // 3. Everything else — skip silently
    // (tool_result orphans, response, error, unknown types)
    i++
  }

  return result
}
