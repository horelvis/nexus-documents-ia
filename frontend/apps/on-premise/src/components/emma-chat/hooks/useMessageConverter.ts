/**
 * useMessageConverter — Memoized SDK→EmmaMessage conversion with stable IDs.
 *
 * Key differences from the old `convertStreamState`:
 * 1. Uses `m.id` from SDK messages directly (NOT `msg-${i}`)
 * 2. Memoized via useMemo keyed on SDK references
 * 3. Stable placeholder IDs: `progress-current` and `interrupt-{type}` (NOT Date.now())
 * 4. Flash-disappear cache: useRef cache for when SDK briefly empties messages
 */
import { useMemo, useRef } from 'react'
import type { Message as SDKMessage } from '@langchain/langgraph-sdk'
import type { EmmaMessage, DocumentInfo } from '@/lib/types/emma'
import type { EmmaStateType } from '../EmmaStreamProvider'
import { isHITLReview, isClarification } from '../types/interrupts'

/** Extract text content from an SDK message (handles string and array formats). */
function getTextContent(m: SDKMessage): string {
  if (typeof m.content === 'string') return m.content
  if (Array.isArray(m.content)) {
    return m.content
      .filter((c): c is { type: 'text'; text: string } =>
        (c as Record<string, unknown>).type === 'text',
      )
      .map((c) => c.text)
      .join('')
  }
  return ''
}

/**
 * Detect if a human message is actually a HITL resume value persisted by
 * LangGraph's Command(resume=...).  These contain raw Python dict reprs
 * like `{'type': 'edit', 'edited_args': {...}}` or JSON equivalents.
 *
 * Returns a user-friendly label if detected, or null if it's a real user message.
 */
function formatResumeMessage(content: string): string | null {
  const trimmed = content.trim()

  // Python dict repr: {'type': 'approve'} or {'type': 'edit', ...} or {'type': 'reject', ...}
  // JSON: {"type": "approve"} etc.
  const resumePattern = /^[{'\"].*['"]type['"]:\s*['"]?(approve|edit|reject)['"]?/
  if (!resumePattern.test(trimmed)) return null

  if (trimmed.includes("'type': 'approve'") || trimmed.includes('"type": "approve"') || trimmed.includes('"type":"approve"')) {
    return 'Aprobado ✓'
  }
  if (trimmed.includes("'type': 'edit'") || trimmed.includes('"type": "edit"') || trimmed.includes('"type":"edit"')) {
    return 'Editado y enviado ✓'
  }
  if (trimmed.includes("'type': 'reject'") || trimmed.includes('"type": "reject"') || trimmed.includes('"type":"reject"')) {
    // Try to extract rejection message
    const msgMatch = trimmed.match(/['"]message['"]:\s*['"]([^'"]+)['"]/)
    return msgMatch ? `Rechazado: ${msgMatch[1]}` : 'Rechazado ✗'
  }

  return null
}

export function useMessageConverter(
  sdkMessages: SDKMessage[],
  values: EmmaStateType | undefined,
  isLoading: boolean,
): { messages: EmmaMessage[] } {
  const cacheRef = useRef<EmmaMessage[]>([])

  // Derive stable keys for memoization
  const reasoningLen = values?.reasoning_steps?.length ?? 0
  const sourcesLen = values?.sources?.length ?? 0
  const success = values?.success
  const explanation = values?.explanation
  const interrupt = values?.__interrupt__

  const messages = useMemo(() => {
    const reasoningSteps = values?.reasoning_steps ?? []
    const sources = values?.sources ?? []

    if (reasoningSteps.length > 0) {
      console.log('[useMessageConverter] reasoning_steps update:', {
        count: reasoningSteps.length,
        types: reasoningSteps.map(s => s.type),
        success,
      })
    }

    // 1. Convert SDK messages — filter empty AI (tool-call turns)
    const converted = sdkMessages
      .filter(
        (m): m is SDKMessage & { type: 'human' | 'ai' } =>
          (m.type === 'human' || m.type === 'ai') &&
          !(m.type === 'ai' && !getTextContent(m)),
      )
      .map((m) => {
        const rawContent = getTextContent(m)

        // Detect HITL resume values persisted as human messages by LangGraph.
        // Command(resume=decision) stores the raw decision dict as a HumanMessage.
        // Replace with a user-friendly label so it doesn't show raw JSON/Python dict.
        if (m.type === 'human') {
          const friendlyLabel = formatResumeMessage(rawContent)
          if (friendlyLabel) {
            return {
              id: m.id || `msg-fallback-resume`,
              type: 'user' as const,
              content: friendlyLabel,
              timestamp: new Date(),
            } as EmmaMessage
          }
        }

        return {
          id: m.id || `msg-fallback-${m.type}`,
          type: m.type === 'human' ? 'user' : 'result',
          content: rawContent,
          timestamp: new Date(),
        } as EmmaMessage
      })

    // 2. Attach reasoning steps + sources to the current turn's AI message
    if (reasoningSteps.length > 0 || sources.length > 0 || explanation) {
      const stepsMetadata: EmmaMessage['metadata'] = {
        slmIsThinking: !success && reasoningSteps.length > 0,
        rawReasoningSteps: reasoningSteps,
      }

      // Attach humanized explanation when available (from explain node)
      if (explanation) {
        stepsMetadata!.explanation = explanation
      }

      if (sources.length > 0) {
        stepsMetadata!.documents = sources.map((s) => ({
          name: (s as Record<string, string>).title || (s as Record<string, string>).name || 'Fuente',
          id: (s as Record<string, string>).document_id || (s as Record<string, string>).id,
          url: (s as Record<string, string>).url,
          boe_id: (s as Record<string, string>).boe_id,
          graph_link: (s as Record<string, string>).graph_link,
          source_type: (s as Record<string, string>).source_type || (s as Record<string, string>).type,
          fileType: (s as Record<string, string>).file_type || (s as Record<string, string>).mime_type,
          relevanceScore: Number((s as Record<string, string>).score || (s as Record<string, string>).relevance) || undefined,
        })) as DocumentInfo[]
      }

      // Find last human message index (= current turn start)
      let lastHumanIdx = -1
      for (let i = converted.length - 1; i >= 0; i--) {
        if (converted[i].type === 'user') {
          lastHumanIdx = i
          break
        }
      }

      // Find a 'result' message AFTER the last human (= current turn AI)
      let currentAiIdx = -1
      for (let i = lastHumanIdx + 1; i < converted.length; i++) {
        if (converted[i].type === 'result' || converted[i].type === 'progress') {
          currentAiIdx = i
          break
        }
      }

      if (currentAiIdx >= 0) {
        // Attach to existing current-turn AI message
        converted[currentAiIdx] = {
          ...converted[currentAiIdx],
          metadata: { ...converted[currentAiIdx].metadata, ...stepsMetadata },
        }
      } else {
        // No AI message yet — create a progress placeholder with stable ID
        converted.push({
          id: 'progress-current',
          type: 'progress',
          content: '',
          timestamp: new Date(),
          metadata: stepsMetadata,
        })
      }
    }

    // 3. Detect HITL interrupt from values.__interrupt__ and create inline message
    if (Array.isArray(interrupt) && interrupt.length > 0) {
      const interruptEntry = interrupt[0]
      const interruptValue = interruptEntry?.value

      if (interruptValue && typeof interruptValue === 'object') {
        if (isHITLReview(interruptValue)) {
          converted.push({
            id: 'interrupt-hitl-review',
            type: 'clarification',
            content:
              interruptValue.action_request?.description || 'Revision requerida',
            timestamp: new Date(),
            metadata: {
              hitl_review: interruptValue,
            },
          })
        } else if (isClarification(interruptValue)) {
          converted.push({
            id: 'interrupt-clarification',
            type: 'clarification',
            content: interruptValue.question || '',
            timestamp: new Date(),
            metadata: {
              clarification: {
                question: interruptValue.question || '',
                options: interruptValue.options || [],
              },
            },
          })
        }
      }
    }

    return converted
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sdkMessages, reasoningLen, sourcesLen, success, explanation, interrupt])

  // Flash-disappear prevention: cache last non-empty conversion
  if (messages.length > 0) {
    cacheRef.current = messages
  }

  return { messages: cacheRef.current }
}
