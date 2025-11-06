"use client"

import { ChatHeaderButton } from "@/components/virtual-assistant/chat-header-button"
import { useChatUI } from "@/contexts/chat-ui-context"

export function SiteHeaderChat() {
  const { isOpen, unreadCount, toggleChat } = useChatUI()
  
  return (
    <ChatHeaderButton 
      isOpen={isOpen}
      onClick={toggleChat}
      unreadCount={unreadCount}
    />
  )
}