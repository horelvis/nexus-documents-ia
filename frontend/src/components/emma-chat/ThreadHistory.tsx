'use client'

import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { SquarePen, MessageSquare } from 'lucide-react'
import { cn } from '@/lib/utils'

interface ThreadItem {
  session_id: string
  metadata?: Record<string, unknown>
  created_at?: string
}

interface ThreadHistoryProps {
  currentThreadId: string | null
  onSelectThread: (threadId: string | null) => void
  apiUrl: string
  tenantId: string
  apiKey?: string
}

export function ThreadHistory({
  currentThreadId,
  onSelectThread,
  apiUrl,
  tenantId,
  apiKey,
}: ThreadHistoryProps) {
  const [threads, setThreads] = useState<ThreadItem[]>([])
  const [isLoading, setIsLoading] = useState(false)

  async function loadThreads() {
    setIsLoading(true)
    try {
      const headers: Record<string, string> = { 'X-Tenant-ID': tenantId }
      if (apiKey) headers['X-API-Key'] = apiKey
      const response = await fetch(`${apiUrl}/v1/emma/sessions?limit=20`, { headers })
      if (response.ok) {
        setThreads(await response.json())
      }
    } catch (err) {
      console.error('Failed to load threads:', err)
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadThreads()
  }, [tenantId])

  return (
    <div className="flex h-full w-64 flex-col border-r bg-muted/30">
      <div className="flex items-center justify-between border-b p-3">
        <span className="text-sm font-semibold">Conversaciones</span>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={() => onSelectThread(null)}
        >
          <SquarePen className="h-4 w-4" />
        </Button>
      </div>
      <div className="flex-1 overflow-y-auto p-2">
        {threads.map((thread) => (
          <button
            key={thread.session_id}
            onClick={() => onSelectThread(thread.session_id)}
            className={cn(
              'w-full rounded-lg px-3 py-2 text-left text-sm transition-colors',
              thread.session_id === currentThreadId
                ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300'
                : 'hover:bg-muted'
            )}
          >
            <div className="flex items-center gap-2">
              <MessageSquare className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />
              <span className="truncate">
                {(thread.metadata?.title as string) || thread.session_id.slice(0, 8)}
              </span>
            </div>
          </button>
        ))}
        {threads.length === 0 && !isLoading && (
          <p className="py-4 text-center text-xs text-muted-foreground">
            No hay conversaciones
          </p>
        )}
      </div>
    </div>
  )
}
