"use client"

import { MessageCircle, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

interface ChatButtonProps {
  isOpen: boolean
  onClick: () => void
  unreadCount?: number
}

export function ChatButton({ isOpen, onClick, unreadCount = 0 }: ChatButtonProps) {
  return (
    <Button
      onClick={onClick}
      className={cn(
        "fixed bottom-6 right-6 h-14 w-14 rounded-full shadow-lg",
        "bg-primary hover:bg-primary/90 transition-all duration-300",
        "z-40 flex items-center justify-center",
        isOpen && "scale-0 opacity-0"
      )}
      size="icon"
      aria-label={isOpen ? "Cerrar asistente virtual" : "Abrir asistente virtual"}
    >
      {isOpen ? (
        <X className="h-6 w-6" />
      ) : (
        <div className="relative">
          <MessageCircle className="h-6 w-6" />
          {unreadCount > 0 && (
            <span className="absolute -top-2 -right-2 h-5 w-5 rounded-full bg-red-500 text-white text-xs flex items-center justify-center">
              {unreadCount > 9 ? "9+" : unreadCount}
            </span>
          )}
        </div>
      )}
    </Button>
  )
}