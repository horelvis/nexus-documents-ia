'use client'

import React, { createContext, useContext, ReactNode } from 'react'
import { useStream } from '@langchain/langgraph-sdk/react'
import type { Message } from '@langchain/langgraph-sdk'

type StateType = { messages: Message[] }

type StreamContextType = ReturnType<typeof useStream<StateType>>
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

  const stream = useStream<StateType>({
    apiUrl,
    assistantId,
    threadId,
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
