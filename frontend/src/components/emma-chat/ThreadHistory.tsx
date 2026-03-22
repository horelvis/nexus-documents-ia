'use client'

import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { SquarePen, MessageSquare } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAuth } from '@/contexts/auth-context'
import { apiClient } from '@/lib/api-client'

interface ThreadItem {
  session_id: string
  metadata?: Record<string, unknown>
  created_at?: string
}

interface ThreadHistoryProps {
  currentThreadId: string | null
  onSelectThread: (threadId: string | null) => void
}

export function ThreadHistory({
  currentThreadId,
  onSelectThread,
}: ThreadHistoryProps) {
  const { tenantId } = useAuth()
  const [threads, setThreads] = useState<ThreadItem[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    console.log('[ThreadHistory] tenantId:', tenantId)
    if (!tenantId) return
    setIsLoading(true)
    setError(null)
    console.log('[ThreadHistory] Fetching sessions...')
    apiClient.get<ThreadItem[]>('/emma/sessions', {
      params: { limit: 20 },
      headers: { 'X-Tenant-ID': tenantId },
    }).then((response) => {
      if (response.error) {
        setError(response.error)
      } else if (response.data) {
        setThreads(response.data)
      }
    }).catch((err) => {
      console.error('Failed to load threads:', err)
      setError('Error al cargar conversaciones')
    }).finally(() => {
      setIsLoading(false)
    })
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
        {isLoading && (
          <p className="py-4 text-center text-xs text-muted-foreground">
            Cargando...
          </p>
        )}
        {threads.length === 0 && !isLoading && (
          <p className="py-4 text-center text-xs text-muted-foreground">
            {error || 'No hay conversaciones'}
          </p>
        )}
      </div>
    </div>
  )
}
