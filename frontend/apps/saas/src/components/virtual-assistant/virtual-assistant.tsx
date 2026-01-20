"use client"

import { useEffect } from "react"
import { ChatSidebar } from "./chat-sidebar"
import { VirtualAssistantProvider } from "@/contexts/virtual-assistant-context"
import { useChatUI } from "@/contexts/chat-ui-context"

export function VirtualAssistant() {
  const { isOpen, unreadCount, setIsOpen, toggleChat } = useChatUI()

  // Handle escape key to close sidebar
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        setIsOpen(false)
      }
    }
    
    window.addEventListener("keydown", handleEscape)
    return () => window.removeEventListener("keydown", handleEscape)
  }, [isOpen, setIsOpen])

  return (
    <VirtualAssistantProvider>
      <>
        {/* Chat Button removed - now only in header */}
        <ChatSidebar 
          isOpen={isOpen} 
          onClose={() => setIsOpen(false)} 
        />
        {/* Overlay for mobile */}
        {isOpen && (
          <div
            className="fixed inset-0 bg-black/50 z-40 lg:hidden"
            onClick={() => setIsOpen(false)}
          />
        )}
      </>
    </VirtualAssistantProvider>
  )
}