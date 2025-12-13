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
  voiceId: "sp-Spk0_woman",  // Default to Spanish female voice
  language: "es-ES",
  speed: 1.0,
  enabled: true,
}

const STORAGE_KEY = "emma_tts_preferences"

const TTSContext = createContext<TTSContextValue | null>(null)

export function TTSProvider({ children }: { children: React.ReactNode }) {
  const [preferences, setPreferences] = useState<TTSPreferences>(DEFAULT_PREFERENCES)
  const [isInitialized, setIsInitialized] = useState(false)

  // Load preferences from localStorage on mount
  useEffect(() => {
    if (typeof window !== "undefined") {
      try {
        const stored = localStorage.getItem(STORAGE_KEY)
        if (stored) {
          const parsed = JSON.parse(stored)
          setPreferences({ ...DEFAULT_PREFERENCES, ...parsed })
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
