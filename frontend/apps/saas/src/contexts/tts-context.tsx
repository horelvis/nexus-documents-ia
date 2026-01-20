"use client"

/**
 * TTS Context - Manages Text-to-Speech preferences
 *
 * Provides global TTS settings for Emma chat:
 * - Auto-play: Automatically read responses aloud
 * - Voice selection: Choose TTS voice
 * - Language: Set language for synthesis
 */

import React, { createContext, useContext, useState, useEffect, useCallback } from "react"

export interface TTSPreferences {
  /** Auto-play TTS for new responses */
  autoPlay: boolean
  /** Selected voice ID */
  voiceId: string
  /** Language code (en-US, es-ES) */
  language: string
  /** Playback speed (0.5 - 2.0) */
  speed: number
  /** Whether TTS is enabled at all */
  enabled: boolean
}

interface TTSContextValue {
  preferences: TTSPreferences
  updatePreferences: (updates: Partial<TTSPreferences>) => void
  resetPreferences: () => void
}

const DEFAULT_PREFERENCES: TTSPreferences = {
  autoPlay: false,
  voiceId: "es-ES-Neural2-A",  // Google TTS: Spanish (Spain) female voice
  language: "es-ES",
  speed: 1.0,
  enabled: true,
}

const STORAGE_KEY = "emma_tts_preferences"

// Migration map for old voice IDs to new Google TTS voice IDs
const VOICE_MIGRATION_MAP: Record<string, string> = {
  // Spanish voices
  "sp-Spk0_woman": "es-ES-Neural2-A",
  "sp-Spk1_man": "es-ES-Neural2-B",
  // English voices
  "en-Carter_man": "en-US-Neural2-A",
  "en-Davis_man": "en-US-Neural2-A",
  "en-Mike_man": "en-US-Neural2-A",
  "en-Frank_man": "en-US-Neural2-A",
  "en-Emma_woman": "en-US-Neural2-C",
  "en-Grace_woman": "en-US-Neural2-C",
  // German voices -> fallback to English
  "de-Spk0_man": "en-US-Neural2-A",
  "de-Spk1_woman": "en-US-Neural2-C",
  // French voices -> fallback to English
  "fr-Spk0_man": "en-US-Neural2-A",
  "fr-Spk1_woman": "en-US-Neural2-C",
  // Italian voices -> fallback to Spanish
  "it-Spk0_woman": "es-ES-Neural2-A",
  "it-Spk1_man": "es-ES-Neural2-B",
  // Portuguese voices -> fallback to Spanish
  "pt-Spk0_woman": "es-ES-Neural2-A",
  "pt-Spk1_man": "es-ES-Neural2-B",
  // Other voices -> fallback to Spanish
  "nl-Spk0_man": "es-ES-Neural2-B",
  "nl-Spk1_woman": "es-ES-Neural2-A",
  "pl-Spk0_man": "es-ES-Neural2-B",
  "pl-Spk1_woman": "es-ES-Neural2-A",
  "jp-Spk0_man": "es-ES-Neural2-B",
  "jp-Spk1_woman": "es-ES-Neural2-A",
  "kr-Spk0_woman": "es-ES-Neural2-A",
  "kr-Spk1_man": "es-ES-Neural2-B",
  "in-Samuel_man": "en-US-Neural2-A",
}

function migrateVoiceId(voiceId: string): string {
  return VOICE_MIGRATION_MAP[voiceId] || voiceId
}

const TTSContext = createContext<TTSContextValue | null>(null)

export function TTSProvider({ children }: { children: React.ReactNode }) {
  const [preferences, setPreferences] = useState<TTSPreferences>(DEFAULT_PREFERENCES)
  const [isInitialized, setIsInitialized] = useState(false)

  // Load preferences from localStorage on mount (with migration)
  useEffect(() => {
    if (typeof window !== "undefined") {
      try {
        const stored = localStorage.getItem(STORAGE_KEY)
        if (stored) {
          const parsed = JSON.parse(stored)
          // Migrate old voice IDs to new Google TTS format
          const migratedVoiceId = migrateVoiceId(parsed.voiceId || DEFAULT_PREFERENCES.voiceId)
          const needsMigration = migratedVoiceId !== parsed.voiceId

          const newPreferences = {
            ...DEFAULT_PREFERENCES,
            ...parsed,
            voiceId: migratedVoiceId
          }
          setPreferences(newPreferences)

          // Save migrated preferences back to localStorage
          if (needsMigration) {
            console.info(`TTS voice migrated: ${parsed.voiceId} -> ${migratedVoiceId}`)
            localStorage.setItem(STORAGE_KEY, JSON.stringify(newPreferences))
          }
        }
      } catch (e) {
        console.error("Failed to load TTS preferences:", e)
      }
      setIsInitialized(true)
    }
  }, [])

  // Save preferences to localStorage when they change
  useEffect(() => {
    if (isInitialized && typeof window !== "undefined") {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences))
      } catch (e) {
        console.error("Failed to save TTS preferences:", e)
      }
    }
  }, [preferences, isInitialized])

  const updatePreferences = useCallback((updates: Partial<TTSPreferences>) => {
    setPreferences(prev => ({ ...prev, ...updates }))
  }, [])

  const resetPreferences = useCallback(() => {
    setPreferences(DEFAULT_PREFERENCES)
  }, [])

  return (
    <TTSContext.Provider value={{ preferences, updatePreferences, resetPreferences }}>
      {children}
    </TTSContext.Provider>
  )
}

export function useTTSPreferences(): TTSContextValue {
  const context = useContext(TTSContext)
  if (!context) {
    // Return default values if not wrapped in provider
    return {
      preferences: DEFAULT_PREFERENCES,
      updatePreferences: () => {},
      resetPreferences: () => {},
    }
  }
  return context
}

export default TTSContext
