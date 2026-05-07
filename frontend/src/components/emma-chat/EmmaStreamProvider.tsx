'use client'

import React, { createContext, useContext, useMemo, ReactNode } from 'react'
import { useStream } from '@langchain/langgraph-sdk/react'
import type { Message } from '@langchain/langgraph-sdk'

/**
 * Full LangGraph state type — must match the values snapshots
 * emitted by the adapter (langgraph_adapter.py).
 */
export type EmmaStateType = {
  messages: Message[]
  reasoning_steps?: Array<{
    type: string
    content: string
    source?: string
    summary?: string
  }>
  sources?: Array<Record<string, unknown>>
  __interrupt__?: Array<{
    value: Record<string, unknown>
    resumable?: boolean
  }>
  thread_id?: string
  success?: boolean
  fast_path?: boolean
  latency_ms?: number
  metadata?: Record<string, unknown>
  explanation?: string
  guardrail_metadata?: {
    guardrail_blocked?: boolean
    guardrail_redacted?: boolean
    guardrail_warnings?: string[]
  }
  /** Slug forwarded by useStreamSubmit when the user typed @<slug>. */
  agent_slug?: string
  /** Resolved agent metadata emitted by classify_node for the bubble badge. */
  agent_metadata?: {
    agent_id?: string
    agent_slug?: string
    agent_name?: string
    agent_color?: string
    agent_icon?: string
  }
}

type StreamContextType = ReturnType<typeof useStream<EmmaStateType>>
const StreamContext = createContext<StreamContextType | undefined>(undefined)

const SSO_TOKEN_KEY = 'nexus_sso_tokens'

function getSSOToken(): string | undefined {
  if (typeof window === 'undefined') return undefined
  try {
    const stored = sessionStorage.getItem(SSO_TOKEN_KEY)
    if (!stored) return undefined
    return JSON.parse(stored).access_token || undefined
  } catch {
    return undefined
  }
}

interface EmmaStreamProviderProps {
  children: ReactNode
  assistantId?: string
  threadId: string | null
  onThreadId: (id: string) => void
}

/**
 * API URL for the LangGraph protocol endpoints.
 * Routes through Next.js rewrites at /api/threads/* which proxy
 * to the core API. Must be absolute because the SDK does `new URL(apiUrl + path)`.
 */
function getApiUrl(): string {
  if (typeof window !== 'undefined') {
    return `${window.location.origin}/api`
  }
  return 'http://localhost:3001/api'
}

export function EmmaStreamProvider({
  children,
  assistantId = 'emma-react',
  threadId,
  onThreadId,
}: EmmaStreamProviderProps) {
  // Read the SSO token fresh on every render. ``apiClient`` (axios) has
  // an interceptor that may have refreshed the token in sessionStorage
  // between the provider's initial mount and a later thread switch;
  // memoising once meant the SDK kept stale (or empty) credentials and
  // ``GET /api/threads/<id>/state`` came back as 401, with the SDK
  // surfacing nothing in the network tab.
  const token = getSSOToken()
  const defaultHeaders = useMemo(
    () => ({
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    }),
    [token],
  )

  const apiUrl = useMemo(() => getApiUrl(), [])

  const stream = useStream<EmmaStateType>({
    apiUrl,
    assistantId,
    threadId,
    messagesKey: 'messages',
    defaultHeaders,
    onThreadId,
    // ``false`` triggers ``client.threads.getState(threadId)`` (single
    // snapshot with the final ``values.messages``). The other modes
    // (``true`` or ``{limit: N}``) call ``getHistory`` which returns an
    // array of checkpoint snapshots; each checkpoint contains the
    // accumulated messages up to that step, so the SDK ends up
    // surfacing duplicates as it walks the array. We don't need
    // time-travel here, so the cleaner contract is ``getState``.
    fetchStateHistory: false,
  })

  return (
    <StreamContext.Provider value={stream}>
      {children}
    </StreamContext.Provider>
  )
}

export function useEmmaStream(): StreamContextType {
  const context = useContext(StreamContext)
  if (!context) {
    throw new Error('useEmmaStream must be used within EmmaStreamProvider')
  }
  return context
}
