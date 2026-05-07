'use client'

/**
 * Lightweight @-mention autocomplete for the chat textarea.
 *
 * Renders a popover above the textarea showing active agents whose slug
 * or name match the partial query the user has typed after `@`. Click
 * (or Enter, handled by parent) inserts `@<slug> ` at the caret.
 */

import { useEffect, useMemo, useState } from 'react'
import { IconRobot } from '@tabler/icons-react'
import { agentsService } from '@/lib/services/agents.service'
import type { Agent } from '@/lib/types/agent'

interface AgentMentionDropdownProps {
  /** Query string after the @ (e.g., "con" for "@con"). null hides the menu. */
  query: string | null
  /** Index of the currently highlighted item (controlled by parent for kb nav). */
  highlightedIndex: number
  onHighlight: (i: number) => void
  onSelect: (slug: string) => void
}

export function AgentMentionDropdown({
  query,
  highlightedIndex,
  onHighlight,
  onSelect,
}: AgentMentionDropdownProps) {
  const [agents, setAgents] = useState<Agent[]>([])

  useEffect(() => {
    let cancelled = false
    void (async () => {
      const r = await agentsService.list({ active: true, order_by: 'usage_count' })
      if (!cancelled && r.data) setAgents(r.data)
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const filtered = useMemo(() => {
    if (query === null) return []
    const q = query.toLowerCase()
    return agents
      .filter((a) => a.slug.toLowerCase().includes(q) || a.name.toLowerCase().includes(q))
      .slice(0, 8)
  }, [agents, query])

  if (query === null || filtered.length === 0) return null

  return (
    <div className="absolute bottom-full left-0 right-0 mb-2 z-30 bg-popover border border-border rounded-lg shadow-lg overflow-hidden">
      <div className="px-3 py-1.5 text-xs text-muted-foreground border-b border-border bg-muted/30">
        🤖 Asistentes
      </div>
      <ul role="listbox" className="max-h-60 overflow-y-auto">
        {filtered.map((agent, i) => (
          <li
            key={agent.id}
            role="option"
            aria-selected={i === highlightedIndex}
            className={`px-3 py-2 cursor-pointer flex items-center gap-2 text-sm ${
              i === highlightedIndex ? 'bg-accent' : 'hover:bg-accent/50'
            }`}
            onMouseEnter={() => onHighlight(i)}
            onMouseDown={(e) => {
              e.preventDefault()
              onSelect(agent.slug)
            }}
          >
            <IconRobot className="h-4 w-4 text-muted-foreground shrink-0" />
            <span className="font-mono">@{agent.slug}</span>
            {agent.description && (
              <span className="text-xs text-muted-foreground truncate flex-1">
                — {agent.description}
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Returns the agents that match a query — used by parent for Enter-key insertion. */
export function useAgentMentionMatches(query: string | null) {
  const [agents, setAgents] = useState<Agent[]>([])

  useEffect(() => {
    let cancelled = false
    void (async () => {
      const r = await agentsService.list({ active: true, order_by: 'usage_count' })
      if (!cancelled && r.data) setAgents(r.data)
    })()
    return () => {
      cancelled = true
    }
  }, [])

  return useMemo(() => {
    if (query === null) return [] as Agent[]
    const q = query.toLowerCase()
    return agents
      .filter((a) => a.slug.toLowerCase().includes(q) || a.name.toLowerCase().includes(q))
      .slice(0, 8)
  }, [agents, query])
}
