"use client"

import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { X } from "lucide-react"

interface WelcomeTooltipProps {
  children: React.ReactNode
  welcomeMessage?: string
  userId?: string
  onDismiss?: () => void
  showOnce?: boolean
}

export function WelcomeTooltip({ 
  children, 
  welcomeMessage = "¡Estoy aquí para ayudarte!", 
  userId,
  onDismiss,
  showOnce = true 
}: WelcomeTooltipProps) {
  const [isVisible, setIsVisible] = useState(false)
  const [shouldShow, setShouldShow] = useState(false)

  useEffect(() => {
    if (showOnce && userId) {
      const key = `welcome-tooltip-dismissed-${userId}`
      const wasDismissed = localStorage.getItem(key)
      
      if (!wasDismissed) {
        // Show tooltip after a short delay for better UX
        const timer = setTimeout(() => {
          setShouldShow(true)
          setIsVisible(true)
        }, 2000)
        
        return () => clearTimeout(timer)
      }
    } else if (!showOnce) {
      // Always show if showOnce is false
      setShouldShow(true)
    }
  }, [userId, showOnce])

  const handleDismiss = () => {
    setIsVisible(false)
    
    if (showOnce && userId) {
      const key = `welcome-tooltip-dismissed-${userId}`
      localStorage.setItem(key, 'true')
    }
    
    onDismiss?.()
  }

  if (!shouldShow) {
    return <>{children}</>
  }

  return (
    <TooltipProvider>
      <Tooltip open={isVisible} onOpenChange={setIsVisible}>
        <TooltipTrigger asChild>
          {children}
        </TooltipTrigger>
        <TooltipContent 
          side="left" 
          className="max-w-xs bg-primary text-primary-foreground shadow-lg"
          sideOffset={8}
        >
          <div className="flex items-start gap-2">
            <div className="flex-1">
              <p className="text-sm font-medium">{welcomeMessage}</p>
              <p className="text-xs opacity-90 mt-1">
                Haz click para conversar conmigo
              </p>
            </div>
            <Button
              variant="ghost"
              size="icon"
              className="h-4 w-4 p-0 hover:bg-primary-foreground/20 text-primary-foreground"
              onClick={handleDismiss}
            >
              <X className="h-3 w-3" />
            </Button>
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}