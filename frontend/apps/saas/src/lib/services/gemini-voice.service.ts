/**
 * Gemini Voice Service
 *
 * Handles communication with the backend for Emma Voice Mode.
 * Fetches ephemeral tokens for secure Gemini Live API access.
 */

import { apiClient } from '../api-client'

export interface VoiceSessionRequest {
  system_prompt?: string
  voice_name?: string
}

export interface VoiceSessionResponse {
  ephemeral_token: string
  expires_at: string
  ws_url: string
  model: string
  voice_name: string
  system_prompt: string
}

export interface VoiceConfigResponse {
  enabled: boolean
  gemini_enabled: boolean
  kokoro_enabled: boolean
  kokoro_base_url: string
  default_voice: string
  system_prompt: string
}

/**
 * Create a voice session with an ephemeral Gemini token.
 *
 * This token is short-lived (10 minutes) and single-use,
 * allowing secure direct connection to Gemini Live API.
 */
export async function createVoiceSession(
  request: VoiceSessionRequest = {}
): Promise<VoiceSessionResponse> {
  const response = await apiClient.post<VoiceSessionResponse>(
    '/gemini/voice-session',
    request
  )

  if (response.error || !response.data) {
    throw new Error(response.error || 'Failed to create voice session')
  }

  return response.data
}

/**
 * Get voice mode configuration.
 *
 * Returns available voice providers and their settings.
 */
export async function getVoiceConfig(): Promise<VoiceConfigResponse> {
  const response = await apiClient.get<VoiceConfigResponse>('/gemini/voice-config')

  if (response.error || !response.data) {
    throw new Error(response.error || 'Failed to get voice config')
  }

  return response.data
}

export const geminiVoiceService = {
  createVoiceSession,
  getVoiceConfig,
}
