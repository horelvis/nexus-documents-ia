/**
 * Type stub for @/hooks/use-tts.
 * Actual implementation lives in the consuming app.
 */

export type TTSStatus = 'idle' | 'loading' | 'playing' | 'streaming' | 'paused' | 'error'

export declare function useTTS(options?: {
  defaultVoiceId?: string
  defaultLanguage?: string
  autoPlay?: boolean
  useStreaming?: boolean
}): {
  status: TTSStatus
  error: string | null
  isPlaying: boolean
  isLoading: boolean
  isStreaming: boolean
  isSpeaking: boolean
  isSupported: boolean
  speak: (text: string) => void
  stop: () => void
  toggle: (text?: string) => void
}
