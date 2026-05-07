/**
 * Parses an agent mention from a chat input string.
 *
 * Two flavours:
 *  1. Tagged input — the rich-input-with-mentions component emits
 *     entity tags as `<@agent:<slug>:<name>>`. We use parseEntityTags
 *     to find the FIRST `agent`-typed tag and return its id (=slug).
 *  2. Plain text fallback — when the input is plain (e.g. legacy paths
 *     or pre-fill via `?prefill=@<slug>+`), look for a leading `@<slug>`.
 *
 * Returns ``null`` when no agent mention is found.
 */
import { parseEntityTags } from '@/components/ui/entity-renderer'

const PLAIN_AGENT_RE = /(^|\s)@([a-z][a-z0-9_]{1,49})\b/

export function extractAgentSlug(input: string): string | null {
  if (!input) return null

  const tags = parseEntityTags(input)
  for (const part of tags) {
    if (part.type === 'entity' && part.entity?.type === 'agent') {
      return part.entity.id
    }
  }

  const m = input.match(PLAIN_AGENT_RE)
  if (m) return m[2]
  return null
}
