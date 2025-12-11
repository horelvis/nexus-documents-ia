"use client"

import { cn } from "@/lib/utils"
import { Mic, MicOff, X, Loader2, AlertCircle, Hand } from "lucide-react"
import { VoiceConnectionState, VoiceControlsProps } from "./types"

export function VoiceControls({
  connectionState,
  isListening,
  isSpeaking,
  onConnect,
  onDisconnect,
  onInterrupt,
  disabled = false,
}: VoiceControlsProps) {
  const isConnected = connectionState === VoiceConnectionState.CONNECTED
  const isConnecting = connectionState === VoiceConnectionState.CONNECTING
  const isError = connectionState === VoiceConnectionState.ERROR

  return (
    <div className="flex items-center justify-center gap-4">
      {/* Main control button */}
      {!isConnected && !isConnecting ? (
        <button
          onClick={onConnect}
          disabled={disabled || isConnecting}
          className={cn(
            "group relative flex items-center justify-center gap-3 px-8 py-4",
            "bg-primary text-primary-foreground rounded-full",
            "hover:bg-primary/90 transition-all duration-300",
            "shadow-lg hover:shadow-xl hover:shadow-primary/20",
            "hover:scale-105 active:scale-95",
            "disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100"
          )}
        >
          <div className="absolute inset-0 rounded-full bg-gradient-to-r from-blue-400/20 to-purple-400/20 opacity-0 group-hover:opacity-100 transition-opacity" />
          {isError ? (
            <>
              <AlertCircle className="w-5 h-5 relative z-10" />
              <span className="font-medium relative z-10">Reintentar</span>
            </>
          ) : (
            <>
              <Mic className="w-5 h-5 relative z-10" />
              <span className="font-medium relative z-10">Iniciar conversaci&oacute;n</span>
            </>
          )}
        </button>
      ) : isConnecting ? (
        <div className="flex flex-col items-center gap-2">
          <Loader2 className="w-8 h-8 text-primary animate-spin" />
          <span className="text-sm text-muted-foreground">Conectando...</span>
        </div>
      ) : (
        <div className="flex items-center gap-4">
          {/* Interrupt button (shown when Emma is speaking) */}
          {isSpeaking && (
            <button
              onClick={onInterrupt}
              className={cn(
                "flex items-center justify-center gap-2 px-4 py-2",
                "bg-amber-500/20 text-amber-600 rounded-full",
                "hover:bg-amber-500/30 transition-all duration-200",
                "border border-amber-500/30"
              )}
              title="Interrumpir"
            >
              <Hand className="w-4 h-4" />
              <span className="text-sm font-medium">Interrumpir</span>
            </button>
          )}

          {/* Disconnect button */}
          <button
            onClick={onDisconnect}
            className={cn(
              "group flex items-center justify-center w-14 h-14 rounded-full",
              "bg-destructive/10 border border-destructive/30 text-destructive",
              "hover:bg-destructive hover:text-destructive-foreground",
              "transition-all duration-300",
              "shadow-lg hover:shadow-destructive/40",
              "hover:scale-110 active:scale-90"
            )}
            title="Desconectar"
          >
            <X className="w-6 h-6 transition-transform group-hover:rotate-90" />
          </button>
        </div>
      )}
    </div>
  )
}

// Status indicator component
export function VoiceStatus({
  connectionState,
  isListening,
  isSpeaking,
}: {
  connectionState: VoiceConnectionState
  isListening: boolean
  isSpeaking: boolean
}) {
  const getStatusText = () => {
    if (connectionState !== VoiceConnectionState.CONNECTED) {
      return connectionState === VoiceConnectionState.CONNECTING
        ? 'Conectando...'
        : 'Desconectado'
    }
    if (isSpeaking) return 'Emma est&aacute; hablando'
    if (isListening) return 'Escuchando...'
    return 'Conectado'
  }

  const getStatusColor = () => {
    if (connectionState !== VoiceConnectionState.CONNECTED) {
      return connectionState === VoiceConnectionState.CONNECTING
        ? 'text-amber-500'
        : 'text-muted-foreground'
    }
    if (isSpeaking) return 'text-blue-500'
    if (isListening) return 'text-green-500'
    return 'text-muted-foreground'
  }

  return (
    <div className="h-8 flex items-center justify-center">
      <p className={cn(
        "text-sm font-light tracking-[0.15em] uppercase transition-all duration-500",
        getStatusColor(),
        (isListening || isSpeaking) ? 'opacity-100' : 'opacity-60'
      )}>
        {getStatusText()}
      </p>
    </div>
  )
}
