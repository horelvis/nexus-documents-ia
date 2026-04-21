"use client"

import { useState, useEffect } from 'react'
import { cn } from "@/lib/utils"
import { AudioVisualizer } from './AudioVisualizer'
import { VoiceControls, VoiceStatus } from './VoiceControls'
import { useGeminiVoice } from './useGeminiVoice'
import { VoiceConnectionState } from './types'
import { AlertCircle } from 'lucide-react'

interface EmmaVoiceModeProps {
  className?: string
  kokoroBaseUrl?: string
  kokoroVoice?: string
  systemPrompt?: string
  onTranscript?: (text: string) => void
  onResponse?: (text: string) => void
}

export function EmmaVoiceMode({
  className,
  kokoroBaseUrl = 'http://localhost:8880',
  kokoroVoice = 'af_bella',
  systemPrompt,
  onTranscript,
  onResponse,
}: EmmaVoiceModeProps) {
  const [transcript, setTranscript] = useState('')
  const [responseText, setResponseText] = useState('')

  const {
    connectionState,
    isListening,
    isSpeaking,
    error,
    connect,
    disconnect,
    interrupt,
    analyser,
  } = useGeminiVoice({
    ttsProvider: 'gemini',
    kokoroBaseUrl,
    kokoroVoice,
    systemPrompt: systemPrompt || `Eres Emma, una asistente de IA profesional especializada en análisis de documentos legales. Respondes en español de forma concisa, profesional y clara. Ayudas a los usuarios a entender sus documentos, identificar riesgos y proporcionar recomendaciones.`,
    voiceName: 'Zephyr',
    onTranscript: (text) => {
      setTranscript(text)
      onTranscript?.(text)
    },
    onResponse: (text) => {
      setResponseText(prev => prev + text)
      onResponse?.(text)
    },
    onError: (err) => {
      console.error('Voice error:', err)
    },
  })

  // Clear response when disconnecting
  useEffect(() => {
    if (connectionState === VoiceConnectionState.DISCONNECTED) {
      setTranscript('')
      setResponseText('')
    }
  }, [connectionState])

  const isConnected = connectionState === VoiceConnectionState.CONNECTED

  return (
    <div className={cn(
      "flex flex-col items-center h-full p-6 relative",
      className
    )}>
      {/* Background ambience */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-[20%] left-[20%] w-[40%] h-[40%] bg-blue-500/5 rounded-full blur-[100px]" />
        <div className="absolute bottom-[20%] right-[20%] w-[40%] h-[40%] bg-purple-500/5 rounded-full blur-[100px]" />
      </div>

      {/* Main Visualizer Area */}
      <div className="flex-1 w-full max-w-lg flex flex-col items-center justify-center relative z-10 min-h-0">
        {/* Error message */}
        {error && (
          <div className="absolute top-4 z-20 flex items-center gap-2 bg-destructive/10 text-destructive px-4 py-2 rounded-lg border border-destructive/20">
            <AlertCircle className="w-4 h-4" />
            <span className="text-sm">{error}</span>
          </div>
        )}

        {/* Visualizer */}
        <div className="w-full aspect-square max-w-[300px] flex items-center justify-center">
          <AudioVisualizer
            analyser={analyser}
            isActive={isConnected && (isListening || isSpeaking)}
          />
        </div>

        {/* Status */}
        <VoiceStatus
          connectionState={connectionState}
          isListening={isListening}
          isSpeaking={isSpeaking}
        />

        {/* Transcript display */}
        {isConnected && (transcript || responseText) && (
          <div className="w-full max-w-md mt-4 space-y-2">
            {transcript && (
              <div className="text-sm text-muted-foreground">
                <span className="font-medium text-foreground">Tú:</span> {transcript}
              </div>
            )}
            {responseText && (
              <div className="text-sm text-muted-foreground">
                <span className="font-medium text-primary">Emma:</span> {responseText}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Controls - always visible at bottom */}
      <div className="w-full max-w-lg z-10 pt-4 pb-2 shrink-0">
        <VoiceControls
          connectionState={connectionState}
          isListening={isListening}
          isSpeaking={isSpeaking}
          onConnect={connect}
          onDisconnect={disconnect}
          onInterrupt={interrupt}
        />
      </div>
    </div>
  )
}
