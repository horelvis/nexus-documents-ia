'use client'

export function LoadingBubble() {
  return (
    <div className="w-full emma-message-enter py-3">
      <div className="flex items-start gap-3">
        <div className="relative shrink-0 mt-0.5">
          <img src="/emma-avatar.png" alt="Emma" className="h-7 w-7 rounded-full object-cover object-top" />
          <span className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full bg-primary ring-2 ring-background animate-pulse" />
        </div>
        <div className="pt-2">
          <TypingDots />
        </div>
      </div>
    </div>
  )
}

export function ThinkingIndicator() {
  return (
    <div className="flex items-center gap-2 text-sm text-muted-foreground">
      <span>Procesando</span>
      <TypingDots />
    </div>
  )
}

function TypingDots() {
  return (
    <div className="flex items-center gap-1">
      <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/50 emma-typing-dot" />
      <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/50 emma-typing-dot" style={{ animationDelay: '0.2s' }} />
      <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/50 emma-typing-dot" style={{ animationDelay: '0.4s' }} />
    </div>
  )
}
