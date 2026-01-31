'use client'

/**
 * Emma Main Page
 *
 * Full-screen Emma chat interface for on-premise deployment.
 * Uses shadcn sidebar layout matching the SaaS version design.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { IconBrain, IconLoader2 } from '@tabler/icons-react'
import {
  SidebarProvider,
  SidebarInset,
  SidebarTrigger,
} from '@nexus/shared/ui'
import { useAuth } from '@/contexts/auth-context'
import { EmmaChat } from '@/components/emma-chat'
import { AppSidebar } from '@/components/layout/app-sidebar'
import { ConversationSidebar } from '@/components/conversation-sidebar'
import { conversationService } from '@/lib/services/conversation.service'
import { EmmaMessage } from '@/lib/types/emma'

export default function EmmaPage() {
  const { isLoaded, isAuthenticated } = useAuth()
  const router = useRouter()

  // Sidebar and conversation state
  const [historyOpen, setHistoryOpen] = useState(false)
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null)
  const [conversationMessages, setConversationMessages] = useState<EmmaMessage[]>([])

  // Load active conversation messages
  const loadConversation = useCallback((id: string) => {
    const conversation = conversationService.get(id)
    if (conversation) {
      setConversationMessages(conversation.messages)
      setActiveConversationId(id)
    }
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
      <div className="flex items-center justify-center h-screen bg-background">
        <div className="flex flex-col items-center gap-4">
          <div className="relative">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-primary to-primary/70 flex items-center justify-center shadow-lg">
              <IconBrain className="h-8 w-8 text-primary-foreground" />
            </div>
            <IconLoader2 className="absolute -bottom-1 -right-1 h-5 w-5 animate-spin text-primary" />
          </div>
          <p className="text-sm text-muted-foreground">Cargando Emma...</p>
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
        <header className="h-14 border-b flex items-center px-4 shrink-0">
          <div className="flex items-center gap-2">
            <SidebarTrigger className="-ml-1" />
            <div className="h-4 w-px bg-border" />
            <div className="flex items-center gap-2">
              <IconBrain className="h-5 w-5 text-primary" />
              <span className="font-semibold">Emma</span>
            </div>
          </div>
        </header>

        {/* Main Content Area - Emma Chat */}
        <main className="flex-1 min-h-0 overflow-hidden">
          <EmmaChat
            className="h-full"
            messages={conversationMessages}
            onMessagesChange={handleMessagesChange}
            conversationId={activeConversationId}
          />
        </main>
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
