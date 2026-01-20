// Voice mode types for Emma Chat

export type TTSProvider = 'gemini' | 'kokoro'

export enum VoiceConnectionState {
  DISCONNECTED = 'DISCONNECTED',
  CONNECTING = 'CONNECTING',
  CONNECTED = 'CONNECTED',
  ERROR = 'ERROR',
}

export interface VoiceState {
  connectionState: VoiceConnectionState
  isListening: boolean
  isSpeaking: boolean
  transcript: string
  error: string | null
}

export interface AudioVisualizerProps {
  analyser: AnalyserNode | null
  isActive: boolean
  color?: string
}

export interface VoiceControlsProps {
  connectionState: VoiceConnectionState
  isListening: boolean
  isSpeaking: boolean
  onConnect: () => void
  onDisconnect: () => void
  onInterrupt: () => void
  disabled?: boolean
}

export interface TTSSelectorProps {
  value: TTSProvider
  onChange: (provider: TTSProvider) => void
  disabled?: boolean
}

export interface GeminiVoiceConfig {
  apiKey: string
  model?: string
  voiceName?: string
  systemInstruction?: string
}

export interface KokoroConfig {
  baseUrl: string
  voice?: string  // e.g., 'af_bella', 'af_sarah', 'am_adam', 'bf_emma'
  speed?: number  // 0.5 - 2.0
}

export interface VoiceModeProps {
  ttsProvider: TTSProvider
  onTranscript?: (text: string) => void
  onResponse?: (text: string) => void
  onError?: (error: string) => void
  systemPrompt?: string
  disabled?: boolean
}
