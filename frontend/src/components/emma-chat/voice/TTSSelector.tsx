"use client"

import { cn } from "@/lib/utils"
import { TTSProvider, TTSSelectorProps } from "./types"

export function TTSSelector({ value, onChange, disabled = false }: TTSSelectorProps) {
  return (
    <div className="flex items-center gap-2 p-1 bg-muted rounded-lg">
      <button
        type="button"
        onClick={() => onChange('gemini')}
        disabled={disabled}
        className={cn(
          "flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-md transition-all duration-200",
          value === 'gemini'
            ? "bg-background text-foreground shadow-sm"
            : "text-muted-foreground hover:text-foreground",
          disabled && "opacity-50 cursor-not-allowed"
        )}
      >
        <GeminiIcon className="w-4 h-4" />
        <span>Gemini</span>
      </button>
      <button
        type="button"
        onClick={() => onChange('kokoro')}
        disabled={disabled}
        className={cn(
          "flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-md transition-all duration-200",
          value === 'kokoro'
            ? "bg-background text-foreground shadow-sm"
            : "text-muted-foreground hover:text-foreground",
          disabled && "opacity-50 cursor-not-allowed"
        )}
      >
        <KokoroIcon className="w-4 h-4" />
        <span>Kokoro</span>
      </button>
    </div>
  )
}

// Gemini icon (simplified Google AI icon)
function GeminiIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
    >
      <circle cx="12" cy="12" r="3" fill="currentColor" />
      <path d="M12 2v4M12 18v4M2 12h4M18 12h4" />
      <path d="M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
    </svg>
  )
}

// Kokoro TTS icon (stylized K with audio waves)
function KokoroIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
    >
      {/* Stylized sound wave / cherry blossom inspired */}
      <circle cx="12" cy="12" r="8" strokeWidth="1.5" />
      <path d="M12 6v12" strokeWidth="2" />
      <path d="M8 9l4 3-4 3" strokeWidth="2" strokeLinejoin="round" />
      <path d="M16 9l-4 3 4 3" strokeWidth="2" strokeLinejoin="round" />
    </svg>
  )
}
