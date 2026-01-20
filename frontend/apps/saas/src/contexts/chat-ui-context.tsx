"use client"

import { createContext, useContext, useState, ReactNode } from "react"

interface ChatUIContextType {
  isOpen: boolean
  unreadCount: number
  setIsOpen: (open: boolean) => void
  setUnreadCount: (count: number) => void
  toggleChat: () => void
}

const ChatUIContext = createContext<ChatUIContextType | undefined>(undefined)

export function ChatUIProvider({ children }: { children: ReactNode }) {
  const [isOpen, setIsOpen] = useState(false)
  const [unreadCount, setUnreadCount] = useState(0)

  const toggleChat = () => {
    setIsOpen(!isOpen)
    if (!isOpen) {
      setUnreadCount(0) // Reset unread count when opening
    }
  }

  return (
    <ChatUIContext.Provider value={{
      isOpen,
      unreadCount,
      setIsOpen,
      setUnreadCount,
      toggleChat
    }}>
      {children}
    </ChatUIContext.Provider>
  )
}

export function useChatUI() {
  const context = useContext(ChatUIContext)
  if (context === undefined) {
    throw new Error('useChatUI must be used within a ChatUIProvider')
  }
  return context
}