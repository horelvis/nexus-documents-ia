'use client'

import { useRef, useEffect } from 'react'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'
import type { EmmaMessage, DocumentInfo } from '@/lib/types/emma'
import { MessageBubble } from './messages/MessageBubble'
import { LoadingBubble } from './messages/LoadingBubble'
import { ErrorBubble } from './messages/ErrorBubble'

interface EmmaRenderChatProps {
  messages: EmmaMessage[]
  isLoading?: boolean
  error?: string | null
  onFeedback?: (messageId: string, feedback: 'positive' | 'negative') => void
  onSuggestionClick?: (suggestion: string) => void
  onRetry?: (failedQuery: string) => void
  onOpenFullscreen?: (doc: DocumentInfo) => void
  className?: string
  showTerminalHeader?: boolean
  renderHITLReview?: (request: any, messageId: string) => React.ReactNode
  renderBranchSwitcher?: (messageId: string) => React.ReactNode
  renderCommandBar?: (messageId: string, content: string) => React.ReactNode
}

export function EmmaRenderChat({
  messages,
  isLoading = false,
  error = null,
  onFeedback,
  onSuggestionClick,
  onRetry,
  onOpenFullscreen,
  className,
  showTerminalHeader = false,
  renderHITLReview,
  renderBranchSwitcher,
  renderCommandBar,
}: EmmaRenderChatProps) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const prevMessageCountRef = useRef(0)
  const isUserNearBottomRef = useRef(true)
  const lastContentRef = useRef('')

  useEffect(() => {
    const scrollArea = scrollRef.current?.querySelector('[data-radix-scroll-area-viewport]')
    if (!scrollArea) return

    const handleScroll = () => {
      const threshold = 150
      isUserNearBottomRef.current =
        scrollArea.scrollHeight - scrollArea.scrollTop - scrollArea.clientHeight < threshold
    }

    scrollArea.addEventListener('scroll', handleScroll, { passive: true })
    return () => scrollArea.removeEventListener('scroll', handleScroll)
  }, [])

  useEffect(() => {
    const messageCount = messages.length
    const isNewMessage = messageCount > prevMessageCountRef.current
    prevMessageCountRef.current = messageCount

    const lastMsg = messages[messages.length - 1]
    const lastContent = lastMsg?.content ?? ''
    const isContentGrowing = lastContent.length > lastContentRef.current.length
    lastContentRef.current = lastContent

    if ((isNewMessage || isContentGrowing) && isUserNearBottomRef.current) {
      requestAnimationFrame(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
      })
    }
  }, [messages.length, messages[messages.length - 1]?.content])

  const showLoader =
    isLoading &&
    !messages.some((m) => m.type === 'progress') &&
    !(messages.length > 0 && messages[messages.length - 1].type === 'result')

  return (
    <div className={cn('h-full flex flex-col relative', className)}>
      {/* Atmospheric gradient — very subtle depth */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute inset-0 bg-gradient-to-b from-primary/[0.02] via-transparent to-primary/[0.01]" />
      </div>

      {showTerminalHeader && <TerminalHeader />}

      <ScrollArea className="flex-1 relative" ref={scrollRef}>
        <div className="space-y-4 px-4 py-4 sm:px-6 lg:px-8 max-w-4xl mx-auto w-full">
          {messages.map((message, idx) => (
            <MessageBubble
              key={message.id}
              message={message}
              isLastMessage={idx === messages.length - 1}
              clarificationAnswered={message.type === 'clarification' && idx < messages.length - 1}
              onFeedback={onFeedback}
              onSuggestionClick={onSuggestionClick}
              onRetry={onRetry}
              onOpenFullscreen={onOpenFullscreen}
              renderHITLReview={renderHITLReview}
              renderBranchSwitcher={renderBranchSwitcher}
              renderCommandBar={renderCommandBar}
            />
          ))}

          {showLoader && <LoadingBubble />}
          {error && <ErrorBubble error={error} />}

          <div ref={messagesEndRef} />
        </div>
      </ScrollArea>
    </div>
  )
}

function TerminalHeader() {
  return (
    <div className="relative flex items-center gap-3 px-4 py-2.5 border-b border-border/20 z-10">
      <div className="flex items-center gap-1.5">
        <span className="h-2.5 w-2.5 rounded-full bg-red-500/70" />
        <span className="h-2.5 w-2.5 rounded-full bg-yellow-500/70" />
        <span className="h-2.5 w-2.5 rounded-full bg-green-500/70" />
      </div>
      <span className="text-[10px] font-mono text-muted-foreground/40 tracking-wider">
        emma-orchestrator
      </span>
    </div>
  )
}
