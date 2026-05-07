'use client'

/**
 * Emma Main Page
 *
 * Full-screen Emma chat interface for on-premise deployment.
 * Uses shadcn sidebar layout matching the SaaS version design.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { useRouter } from 'next/navigation'
import Image from 'next/image'
import { IconBrain } from '@tabler/icons-react'
import {
  SidebarProvider,
  SidebarInset,
} from '@/components/ui'
import { useAuth } from '@/contexts/auth-context'
import { EmmaChat } from '@/components/emma-chat'
import { AppSidebar } from '@/components/layout/app-sidebar'
import { PageHeader } from '@/components/layout/page-header'
import { ConversationSidebar } from '@/components/conversation-sidebar'
import { conversationService } from '@/lib/services/conversation.service'
import { EmmaMessage } from '@/lib/types/emma'

export default function EmmaPage() {
  const { isLoaded, isAuthenticated } = useAuth()
  const router = useRouter()

  // Sidebar and conversation state
  const [historyOpen, setHistoryOpen] = useState(false)

  // Open history panel when navigating from another page via ?history=open
  useEffect(() => {
    if (typeof window === 'undefined') return
    const params = new URLSearchParams(window.location.search)
    if (params.get('history') === 'open') {
      setHistoryOpen(true)
      window.history.replaceState({}, '', '/')
    }
  }, [])
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null)
  const [conversationMessages, setConversationMessages] = useState<EmmaMessage[]>([])

  // Load active conversation. The chat now hydrates messages from the
  // LangGraph checkpointer via the SDK (EmmaChat reads ``conversationId``
  // and remounts the StreamProvider with the new threadId), so we only
  // need to expose the id; we no longer pre-load anything from the
  // legacy localStorage service. ``conversationMessages`` stays empty
  // — the SDK's ``stream.messages`` is the source of truth.
  const loadConversation = useCallback((id: string) => {
    setConversationMessages([])
    setActiveConversationId(id)
  }, [])

  // Create new conversation
  const handleNewConversation = useCallback(() => {
    setActiveConversationId(null)
    setConversationMessages([])
  }, [])

  // Handle conversation selection from history
  const handleSelectConversation = useCallback((id: string) => {
    loadConversation(id)
    setHistoryOpen(false)
  }, [loadConversation])

  // Handle conversation deletion
  const handleDeleteConversation = useCallback((id: string) => {
    if (activeConversationId === id) {
      handleNewConversation()
    }
  }, [activeConversationId, handleNewConversation])

  // Handle bulk deletion of conversations
  const handleDeleteMultiple = useCallback((ids: string[]) => {
    if (activeConversationId && ids.includes(activeConversationId)) {
      handleNewConversation()
    }
  }, [activeConversationId, handleNewConversation])

  // Ref to track active conversation without causing callback recreation
  const activeConversationIdRef = useRef(activeConversationId)
  activeConversationIdRef.current = activeConversationId

  // Save messages to conversation
  // IMPORTANT: No dependency on activeConversationId to prevent recreation during streaming
  const handleMessagesChange = useCallback((messages: EmmaMessage[]) => {
    setConversationMessages(messages)

    // Auto-save to localStorage
    if (messages.length > 0) {
      const currentConvId = activeConversationIdRef.current
      if (currentConvId) {
        // Update existing conversation
        conversationService.update(currentConvId, { messages })
      } else {
        // Create new conversation when first message is sent
        const hasUserMessage = messages.some((m) => m.type === 'user')
        if (hasUserMessage) {
          const newConv = conversationService.create(messages)
          setActiveConversationId(newConv.id)
        }
      }
    }
  }, []) // Stable callback - uses ref for activeConversationId

  // Redirect to login if not authenticated
  useEffect(() => {
    if (isLoaded && !isAuthenticated) {
      router.push('/auth/sign-in')
    }
  }, [isLoaded, isAuthenticated, router])

  // Loading state
  if (!isLoaded) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#05070d]">
        <div className="pointer-events-none absolute inset-0">
          <div className="absolute inset-x-0 top-0 h-[500px] bg-gradient-to-b from-cyan-500/8 via-transparent to-transparent" />
          <div className="absolute right-0 top-1/4 h-[600px] w-[600px] rounded-full bg-cyan-500/5 blur-[120px]" />
        </div>
        <div className="relative flex flex-col items-center gap-6">
          <div className="relative">
            <div className="absolute -inset-4 rounded-full bg-cyan-500/20 blur-xl" />
            <Image
              src="/logo-single.png"
              alt="NouxCube AI"
              width={64}
              height={64}
              className="relative h-16 w-auto"
              priority
            />
          </div>
          <div className="flex flex-col items-center gap-2">
            <div className="h-1 w-32 overflow-hidden rounded-full bg-white/10">
              <div className="h-full w-1/2 animate-[shimmer_1.5s_ease-in-out_infinite] rounded-full bg-gradient-to-r from-transparent via-cyan-400 to-transparent" />
            </div>
            <p className="text-sm text-slate-400">Cargando...</p>
          </div>
        </div>
      </div>
    )
  }

  // Not authenticated
  if (!isAuthenticated) {
    return null
  }

  return (
    <SidebarProvider>
      {/* Main Sidebar - inset variant for modern look */}
      <AppSidebar
        variant="inset"
        onNewConversation={handleNewConversation}
        onOpenHistory={() => setHistoryOpen(true)}
      />

      {/* Main Content */}
      <SidebarInset>
        {/* Header */}
        <PageHeader>
          <div className="flex items-center gap-2">
            <IconBrain className="h-5 w-5 text-primary" />
            <span className="font-semibold">Emma</span>
          </div>
        </PageHeader>

        {/* Main Content Area - Emma Chat */}
        <div className="flex-1 min-h-0 overflow-hidden">
          <EmmaChat
            className="h-full"
            messages={conversationMessages}
            onMessagesChange={handleMessagesChange}
            conversationId={activeConversationId}
          />
        </div>
      </SidebarInset>

      {/* Conversation History Sidebar (Sheet) */}
      <ConversationSidebar
        isOpen={historyOpen}
        onOpenChange={setHistoryOpen}
        activeConversationId={activeConversationId}
        onSelectConversation={handleSelectConversation}
        onNewConversation={handleNewConversation}
        onDeleteConversation={handleDeleteConversation}
        onDeleteMultiple={handleDeleteMultiple}
      />
    </SidebarProvider>
  )
}
