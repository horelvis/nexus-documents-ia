"use client"

/**
 * Gemini Voice Service - Stub for Emma On-Premise
 *
 * Voice functionality will be implemented later with on-premise TTS services.
 */

export interface VoiceSession {
  send: (text: string) => void
  close: () => void
  onAudio: (callback: (audio: Blob) => void) => void
  onError: (callback: (error: Error) => void) => void
}

/**
 * Create a voice session (stub implementation)
 */
export async function createVoiceSession(): Promise<VoiceSession> {
  console.warn('[GeminiVoice] Voice sessions not implemented for Emma on-premise')

  return {
    send: () => {
      console.warn('[GeminiVoice] send() not implemented')
    },
    close: () => {
      console.warn('[GeminiVoice] close() not implemented')
    },
    onAudio: () => {
      console.warn('[GeminiVoice] onAudio() not implemented')
    },
    onError: () => {
      console.warn('[GeminiVoice] onError() not implemented')
    },
  }
}
