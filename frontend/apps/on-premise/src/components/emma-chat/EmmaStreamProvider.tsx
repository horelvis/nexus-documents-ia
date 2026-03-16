'use client'

import React, { createContext, useContext, ReactNode } from 'react'
import { useStream } from '@langchain/langgraph-sdk/react'
import type { Message } from '@langchain/langgraph-sdk'

type StateType = { messages: Message[] }

type StreamContextType = ReturnType<typeof useStream<StateType>>
const StreamContext = createContext<StreamContextType | undefined>(undefined)

interface EmmaStreamProviderProps {
  children: ReactNode
  apiUrl: string
  assistantId?: string
  threadId: string | null
  onThreadId: (id: string) => void
  apiKey?: string
  tenantId: string
}

export function EmmaStreamProvider({
  children,
  apiUrl,
  assistantId = 'emma-react',
  threadId,
  onThreadId,
  apiKey,
  tenantId,
}: EmmaStreamProviderProps) {
  const stream = useStream<StateType>({
    apiUrl,
    assistantId,
    threadId,
    apiKey: apiKey || undefined,
    defaultHeaders: {
      'X-Tenant-ID': tenantId,
      ...(apiKey ? { 'X-API-Key': apiKey } : {}),
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
