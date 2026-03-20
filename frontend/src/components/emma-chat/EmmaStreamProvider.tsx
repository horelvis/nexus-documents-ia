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
 * Constructs the API URL for the emma-agent-service LangGraph endpoint.
 * Uses NEXT_PUBLIC_API_BASE_URL from environment config.
 */
function getApiUrl(): string {
  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || process.env.NEXT_PUBLIC_API_URL || ''
  if (baseUrl && !baseUrl.startsWith('/')) {
    // Absolute URL configured (e.g. https://nouxcube.local)
    return `${baseUrl.replace(/\/+$/, '')}/api`
  }
  // Fallback: same origin
  if (typeof window !== 'undefined') {
    return `${window.location.origin}/api`
  }
  return '/api'
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

  const apiUrl = useMemo(() => getApiUrl(), [])

  const stream = useStream<EmmaStateType>({
    apiUrl,
    assistantId,
    threadId,
    messagesKey: 'messages',
    defaultHeaders,
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
