/**
 * Type stub for @/contexts/tts-context.
 * Actual implementation lives in the consuming app.
 */
export interface TTSPreferences {
  autoPlay: boolean
  voiceId: string
  language: string
  speed: number
  enabled: boolean
}

export declare function useTTSPreferences(): {
  preferences: TTSPreferences
  updatePreferences: (updates: Partial<TTSPreferences>) => void
}
