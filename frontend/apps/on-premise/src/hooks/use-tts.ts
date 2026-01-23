/**
 * TTS Hook - Stub for Emma App
 *
 * This is a placeholder that will be implemented when TTS is integrated
 * with Emma's SSO-based authentication system.
 */

import { useState, useCallback } from "react"

export type TTSStatus = "idle" | "loading" | "playing" | "paused" | "error" | "streaming"

export interface TTSVoice {
  voice_id: string
  name: string
  language: string
  gender?: string
  description?: string
  provider: string
}

export interface UseTTSOptions {
  defaultVoiceId?: string
  defaultLanguage?: string
  speed?: number
  autoPlay?: boolean
  useStreaming?: boolean
  onPlayStart?: () => void
  onPlayEnd?: () => void
  onError?: (error: string) => void
  onFirstChunk?: () => void
}

export interface UseTTSReturn {
  status: TTSStatus
  error: string | null
  isPlaying: boolean
  isLoading: boolean
  isStreaming: boolean
  duration: number
  currentTime: number
  voices: TTSVoice[]
  selectedVoice: string
  speak: (text: string) => Promise<void>
  speakStream: (text: string) => Promise<void>
  stop: () => void
  pause: () => void
  resume: () => void
  toggle: () => void
  setVoice: (voiceId: string) => void
  loadVoices: () => Promise<void>
}

/**
 * TTS Hook stub - TTS functionality not yet implemented for Emma
 */
export function useTTS(options: UseTTSOptions = {}): UseTTSReturn {
  const [status] = useState<TTSStatus>("idle")
  const [selectedVoice, setSelectedVoice] = useState(options.defaultVoiceId || "")

  const noop = useCallback(async () => {
    console.warn("[useTTS] TTS not implemented for Emma app yet")
  }, [])

  const noopSync = useCallback(() => {
    console.warn("[useTTS] TTS not implemented for Emma app yet")
  }, [])

  return {
    status,
    error: null,
    isPlaying: false,
    isLoading: false,
    isStreaming: false,
    duration: 0,
    currentTime: 0,
    voices: [],
    selectedVoice,
    speak: noop,
    speakStream: noop,
    stop: noopSync,
    pause: noopSync,
    resume: noopSync,
    toggle: noopSync,
    setVoice: setSelectedVoice,
    loadVoices: noop,
  }
}

export default useTTS
