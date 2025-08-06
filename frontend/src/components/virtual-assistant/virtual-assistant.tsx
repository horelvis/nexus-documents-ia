"use client"

import { useState, useEffect } from "react"
import { ChatButton } from "./chat-button"
import { ChatSidebar } from "./chat-sidebar"
import { VirtualAssistantProvider } from "@/contexts/virtual-assistant-context"

export function VirtualAssistant() {
  const [isOpen, setIsOpen] = useState(false)
  const [unreadCount, setUnreadCount] = useState(0)

  // Handle escape key to close sidebar
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        setIsOpen(false)
      }
    }
    
    window.addEventListener("keydown", handleEscape)
    return () => window.removeEventListener("keydown", handleEscape)
  }, [isOpen])

  // Reset unread count when opening
  useEffect(() => {
    if (isOpen) {
      setUnreadCount(0)
    }
  }, [isOpen])

  return (
    <VirtualAssistantProvider>
      <>
        <ChatButton 
          isOpen={isOpen} 
          onClick={() => setIsOpen(!isOpen)}
          unreadCount={unreadCount}
        />
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