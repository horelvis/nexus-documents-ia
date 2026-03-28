/**
 * useMessageConverter — Memoized SDK→EmmaMessage conversion with stable IDs.
 *
 * Key differences from the old `convertStreamState`:
 * 1. Uses `m.id` from SDK messages directly (NOT `msg-${i}`)
 * 2. Memoized via useMemo keyed on SDK references
 * 3. Stable placeholder IDs: `progress-current` and `interrupt-{type}` (NOT Date.now())
 * 4. Flash-disappear cache: useRef cache for when SDK briefly empties messages
 */
import { useEffect, useMemo, useRef } from 'react'
import type { Message as SDKMessage } from '@langchain/langgraph-sdk'
import type { EmmaMessage, DocumentInfo } from '@/lib/types/emma'
import type { EmmaStateType } from '../EmmaStreamProvider'
import { isHITLReview, isClarification } from '../types/interrupts'

/**
 * Filter sources to only those actually referenced in the response text.
 * Matches by: title/name keywords, boe_id, or document_id.
 */
function filterReferencedSources(
  sources: DocumentInfo[],
  responseText: string,
): DocumentInfo[] {
  if (!responseText || sources.length === 0) return sources

  const textLower = responseText.toLowerCase()

  return sources.filter((src) => {
    // Match by boe_id (e.g., "Real Decreto Legislativo 2/2015" or BOE ref)
    if (src.boe_id && textLower.includes(src.boe_id.toLowerCase())) return true

    // Match by document_id (rare in text, but possible)
    if (src.id && textLower.includes(src.id.toLowerCase())) return true

    // Match by title/name — extract significant keywords (3+ chars) and
    // check if enough of them appear in the response text.
    const name = src.name || ''
    if (name) {
      const nameLower = name.toLowerCase()

      // Direct substring match for short names (≤40 chars)
      if (nameLower.length <= 40 && nameLower.length >= 3 && textLower.includes(nameLower)) {
        return true
      }

      // For longer names, check if significant keywords overlap.
      // Strip common extensions and split into words.
      const stripped = nameLower.replace(/\.(pdf|docx?|xlsx?|txt|md|odt|rtf)$/, '')
      const words = stripped.split(/[\s_\-./]+/).filter((w) => w.length >= 3)
      if (words.length === 0) return false

      // Require at least 50% of significant words present (min 2 for long titles)
      const threshold = Math.max(2, Math.ceil(words.length * 0.5))
      const matched = words.filter((w) => textLower.includes(w)).length
      if (matched >= threshold) return true
    }

    return false
  })
}

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
  const metadataCacheRef = useRef<Map<string, EmmaMessage['metadata']>>(new Map())

  // Derive stable keys for memoization
  const reasoningLen = values?.reasoning_steps?.length ?? 0
  const sourcesLen = values?.sources?.length ?? 0
  const success = values?.success
  const explanation = values?.explanation
  const interrupt = values?.__interrupt__

  const messages = useMemo(() => {
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    void isLoading // tracked as dependency for progress placeholder
    const reasoningSteps = values?.reasoning_steps ?? []
    const sources = values?.sources ?? []

    // 0. Deduplicate SDK messages by ID (first occurrence wins — keeps correct position).
    // When a `values` event delivers [h1, a1, h2] and a late `messages` event re-appends
    // a1 at the end → [h1, a1, h2, a1']. First-wins keeps [h1, a1, h2] (correct order).
    // Last-wins would produce [h1, h2, a1'] — wrong position for a1.
    const dedupedSdk = (() => {
      const seen = new Set<string>()
      return sdkMessages.filter((m) => {
        if (!m.id) return true
        if (seen.has(m.id)) return false
        seen.add(m.id)
        return true
      })
    })()

    // 1. Convert SDK messages — filter empty AI (tool-call turns)
    const converted = dedupedSdk
      .filter(
        (m): m is SDKMessage & { type: 'human' | 'ai' } =>
          (m.type === 'human' || m.type === 'ai') &&
          !(m.type === 'ai' && !getTextContent(m)),
      )
      .map((m) => {
        const rawContent = getTextContent(m)

        // Detect HITL resume values persisted as human messages by LangGraph.
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

    // 1b. Remove prefix-duplicate AI messages (defensive — backend fix is primary).
    // If synthesize creates a new message instead of updating, the pre-guardrail
    // response (shorter, no disclaimer) is a prefix of the post-guardrail one.
    // Keep only the longer version.
    for (let i = converted.length - 1; i > 0; i--) {
      const curr = converted[i]
      const prev = converted[i - 1]
      if (curr.type === 'result' && prev.type === 'result' && curr.content && prev.content) {
        if (curr.content.startsWith(prev.content)) {
          converted.splice(i - 1, 1)
          i-- // adjust index after removal
        } else if (prev.content.startsWith(curr.content)) {
          converted.splice(i, 1)
        }
      }
    }

    // 2. Restore cached metadata for previous turns' AI messages
    for (let i = 0; i < converted.length; i++) {
      const msg = converted[i]
      if (msg.type === 'result' && !msg.metadata?.rawReasoningSteps) {
        const cached = metadataCacheRef.current.get(msg.id)
        if (cached) {
          converted[i] = { ...msg, metadata: { ...msg.metadata, ...cached } }
        }
      }
    }

    // 3. Attach reasoning steps + sources to the current turn's AI message

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

    const hasMetadata = reasoningSteps.length > 0 || sources.length > 0 || explanation

    if (hasMetadata) {
      const stepsMetadata: EmmaMessage['metadata'] = {
        slmIsThinking: !success && reasoningSteps.length > 0,
        rawReasoningSteps: reasoningSteps,
      }

      if (explanation) {
        stepsMetadata!.explanation = explanation
      }

      if (sources.length > 0) {
        const allDocs = sources.map((s) => {
          const src = s as Record<string, unknown>
          const pageRaw = src.page ?? src.page_number
          return {
            name: (src.title as string) || (src.name as string) || 'Fuente',
            id: (src.document_id as string) || (src.id as string),
            url: src.url as string,
            boe_id: src.boe_id as string,
            graph_link: src.graph_link as string,
            source_type: (src.source_type as string) || (src.type as string),
            fileType: (src.file_type as string) || (src.mime_type as string) || (src.document_type as string),
            relevanceScore: Number(src.score || src.relevance) || undefined,
            page: pageRaw != null ? Number(pageRaw) : undefined,
            excerpt: (src.excerpt as string) || (src.snippet as string) || undefined,
          }
        }) as DocumentInfo[]

        // Only show sources actually referenced in the response text.
        // During streaming (success=false), show all so cards appear progressively.
        const responseText = currentAiIdx >= 0 ? converted[currentAiIdx].content : ''
        const filtered = success && responseText
          ? filterReferencedSources(allDocs, responseText)
          : allDocs
        stepsMetadata!.documents = filtered.length > 0 ? filtered : allDocs
      }

      if (currentAiIdx >= 0) {
        // Attach to existing current-turn AI message
        converted[currentAiIdx] = {
          ...converted[currentAiIdx],
          metadata: { ...converted[currentAiIdx].metadata, ...stepsMetadata },
        }
      } else if (!success) {
        // No AI message yet and turn is actively processing — create progress placeholder.
        // Guard: if success=true, reasoning_steps are stale from the previous turn.
        converted.push({
          id: 'progress-current',
          type: 'progress',
          content: '',
          timestamp: new Date(),
          metadata: stepsMetadata,
        })
      }
    }

    // 3b. Guarantee a progress placeholder when loading, even without reasoning_steps.
    // This covers the gap between submit and the first backend event.
    if (isLoading && !success && currentAiIdx < 0 && !hasMetadata && lastHumanIdx >= 0) {
      converted.push({
        id: 'progress-current',
        type: 'progress',
        content: '',
        timestamp: new Date(),
        metadata: {},
      })
    }

    // 4. Detect HITL interrupt from values.__interrupt__ and create inline message
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
  }, [sdkMessages, reasoningLen, sourcesLen, success, explanation, interrupt, isLoading])

  // Write metadata to cache after render (side-effect, safe in useEffect)
  useEffect(() => {
    for (const msg of messages) {
      if (msg.metadata?.rawReasoningSteps && msg.metadata.rawReasoningSteps.length > 0) {
        metadataCacheRef.current.set(msg.id, msg.metadata)
      }
    }
  }, [messages])

  // Flash-disappear prevention: cache last non-empty conversion
  if (messages.length > 0) {
    cacheRef.current = messages
  }

  return { messages: cacheRef.current }
}
