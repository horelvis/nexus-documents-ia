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
  tenantId: string
}

/**
 * Base URL for the backend API (without /api/v1 suffix).
 */
function getBackendBaseUrl(): string {
  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || process.env.NEXT_PUBLIC_API_URL || ''
  if (baseUrl && !baseUrl.startsWith('/')) {
    return baseUrl.replace(/\/+$/, '')
  }
  if (typeof window !== 'undefined') {
    return window.location.origin
  }
  return ''
}

/** Session-based API path prefix */
const SESSIONS_BASE = '/api/v1/emma/sessions'

/**
 * URL rewrite map: LangGraph SDK paths → backend emma/sessions paths.
 * Order matters — more specific patterns first.
 */
const URL_REWRITES: [RegExp, string][] = [
  // /api/threads/{id}/runs/stream → /api/v1/emma/sessions/{id}/continue
  [/\/api\/threads\/([^/]+)\/runs\/stream/, `${SESSIONS_BASE}/$1/continue`],
  // /api/threads/{id}/history → /api/v1/emma/sessions/{id}/history
  [/\/api\/threads\/([^/]+)\/history/, `${SESSIONS_BASE}/$1/history`],
  // /api/threads/{id}/state → /api/v1/emma/sessions/{id}/state
  [/\/api\/threads\/([^/]+)\/state/, `${SESSIONS_BASE}/$1/state`],
  // /api/threads/{id} → /api/v1/emma/sessions/{id}
  [/\/api\/threads\/([^/]+)$/, `${SESSIONS_BASE}/$1`],
  // /api/threads → /api/v1/emma/sessions
  [/\/api\/threads$/, SESSIONS_BASE],
  // /api/assistants/* → /api/v1/emma/assistants/*
  [/\/api\/assistants(.*)/, '/api/v1/emma/assistants$1'],
]

/**
 * Custom fetch that rewrites LangGraph SDK paths (/threads/*)
 * to the backend's session-based endpoints (/api/v1/emma/sessions/*).
 */
async function rewriteFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
  let rewritten = url
  for (const [pattern, replacement] of URL_REWRITES) {
    if (pattern.test(rewritten)) {
      rewritten = rewritten.replace(pattern, replacement)
      break
    }
  }
  if (rewritten !== url) {
    console.log('[Emma] URL rewrite:', url, '→', rewritten)
  }
  const response = await fetch(rewritten, init)

  // The SDK expects `thread_id` but the backend returns `session_id`.
  // Map session_id → thread_id in JSON responses.
  const ct = response.headers.get('content-type') || ''
  if (ct.includes('application/json')) {
    const body = await response.json()
    if (body && typeof body === 'object' && 'session_id' in body && !('thread_id' in body)) {
      body.thread_id = body.session_id
    }
    return new Response(JSON.stringify(body), {
      status: response.status,
      statusText: response.statusText,
      headers: response.headers,
    })
  }
  return response
}

export function EmmaStreamProvider({
  children,
  assistantId = 'emma-react',
  threadId,
  onThreadId,
  tenantId,
}: EmmaStreamProviderProps) {
  // Memoize token read so it doesn't re-evaluate on every render
  const token = useMemo(() => getSSOToken(), [])

  // Memoize headers to prevent useStream from recreating the client
  const defaultHeaders = useMemo(
    () => ({
      'X-Tenant-ID': tenantId,
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    }),
    [tenantId, token],
  )

  const apiUrl = useMemo(() => `${getBackendBaseUrl()}/api`, [])

  const callerOptions = useMemo(() => ({ fetch: rewriteFetch }), [])

  const stream = useStream<EmmaStateType>({
    apiUrl,
    assistantId,
    threadId,
    messagesKey: 'messages',
    defaultHeaders,
    callerOptions,
    onThreadId,
    fetchStateHistory: true,
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
