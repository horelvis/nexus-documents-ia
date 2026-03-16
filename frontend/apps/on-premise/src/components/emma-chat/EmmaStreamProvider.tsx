'use client'

import React, { createContext, useContext, ReactNode } from 'react'
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
  }>
  sources?: Array<Record<string, unknown>>
  thread_id?: string
  success?: boolean
  fast_path?: boolean
  latency_ms?: number
  metadata?: Record<string, unknown>
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
  apiUrl: string
  assistantId?: string
  threadId: string | null
  onThreadId: (id: string) => void
  tenantId: string
}

export function EmmaStreamProvider({
  children,
  apiUrl,
  assistantId = 'emma-react',
  threadId,
  onThreadId,
  tenantId,
}: EmmaStreamProviderProps) {
  const token = getSSOToken()

  const stream = useStream<EmmaStateType>({
    apiUrl,
    assistantId,
    threadId,
    messagesKey: 'messages',
    defaultHeaders: {
      'X-Tenant-ID': tenantId,
      ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    },
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
