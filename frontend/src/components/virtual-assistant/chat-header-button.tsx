"use client"

import { Bot } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { WelcomeTooltip } from "@/components/ui/welcome-tooltip"
import { useWelcomeMessage } from "@/hooks/use-welcome-message"
import { useUser } from "@clerk/nextjs"

interface ChatHeaderButtonProps {
  isOpen: boolean
  onClick: () => void
  unreadCount?: number
}

export function ChatHeaderButton({ isOpen, onClick, unreadCount = 0 }: ChatHeaderButtonProps) {
  const { welcomeMessage, isLoading } = useWelcomeMessage()
  const { user } = useUser()

  const button = (
    <Button
      variant="ghost"
      size="sm"
      onClick={onClick}
      className={cn(
        "relative h-9 w-9 hover:bg-accent hover:text-accent-foreground",
        isOpen && "bg-accent text-accent-foreground"
      )}
      aria-label={isOpen ? "Cerrar asistente virtual" : "Abrir asistente virtual"}
    >
      <Bot className="h-4 w-4 text-primary" />
      {unreadCount > 0 && (
        <span className="absolute -top-1 -right-1 h-4 w-4 rounded-full bg-red-500 text-white text-xs flex items-center justify-center">
          {unreadCount > 9 ? "9+" : unreadCount}
        </span>
      )}
    </Button>
  )

  // Don't show welcome tooltip if chat is already open or still loading
  if (isOpen || isLoading || !welcomeMessage) {
    return button
  }

  return (
    <WelcomeTooltip
      welcomeMessage={welcomeMessage.message}
      userId={user?.id}
      showOnce={true}
    >
      {button}
    </WelcomeTooltip>
  )
}