"use client"

import { useState, useRef, useCallback, useEffect } from 'react'
import { VoiceConnectionState, TTSProvider } from './types'
import { base64ToUint8Array, decodeAudioData, createPcmBlob } from './audioUtils'
import { createVoiceSession } from '@/lib/services/gemini-voice.service'

interface UseGeminiVoiceOptions {
  ttsProvider: TTSProvider
  kokoroBaseUrl?: string
  kokoroVoice?: string
  systemPrompt?: string
  voiceName?: string
  onTranscript?: (text: string) => void
  onResponse?: (text: string) => void
  onError?: (error: string) => void
}

interface UseGeminiVoiceReturn {
  connectionState: VoiceConnectionState
  isListening: boolean
  isSpeaking: boolean
  transcript: string
  response: string
  error: string | null
  connect: () => Promise<void>
  disconnect: () => void
  interrupt: () => void
  analyser: AnalyserNode | null
}

export function useGeminiVoice({
  ttsProvider,
  kokoroBaseUrl = 'http://localhost:8880',
  kokoroVoice = 'af_bella',  // Default Kokoro voice
  systemPrompt,
  voiceName = 'Zephyr',
  onTranscript,
  onResponse,
  onError,
}: UseGeminiVoiceOptions): UseGeminiVoiceReturn {
  const [connectionState, setConnectionState] = useState<VoiceConnectionState>(VoiceConnectionState.DISCONNECTED)
  const [isListening, setIsListening] = useState(false)
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [transcript, setTranscript] = useState('')
  const [response, setResponse] = useState('')
  const [error, setError] = useState<string | null>(null)

  // Audio refs
  const audioContextRef = useRef<AudioContext | null>(null)
  const inputAudioContextRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const processorRef = useRef<ScriptProcessorNode | null>(null)
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null)

  // Playback timing
  const nextStartTimeRef = useRef<number>(0)
  const sourcesRef = useRef<Set<AudioBufferSourceNode>>(new Set())

  // Session ref (for Gemini)
  const sessionRef = useRef<any>(null)

  // Audio buffer for Kokoro TTS (accumulates recorded audio for STT)
  const audioBufferRef = useRef<Float32Array[]>([])

  // Initialize Audio Contexts
  const ensureAudioContexts = useCallback(() => {
    if (!audioContextRef.current) {
      audioContextRef.current = new (window.AudioContext || (window as any).webkitAudioContext)({ sampleRate: 24000 })
      analyserRef.current = audioContextRef.current.createAnalyser()
      analyserRef.current.fftSize = 512
      analyserRef.current.smoothingTimeConstant = 0.5
      analyserRef.current.connect(audioContextRef.current.destination)
    }
    if (!inputAudioContextRef.current) {
      inputAudioContextRef.current = new (window.AudioContext || (window as any).webkitAudioContext)({ sampleRate: 16000 })
    }
  }, [])

  // Connect to Gemini Live using ephemeral token from backend
  const connectGemini = useCallback(async () => {
    try {
      setConnectionState(VoiceConnectionState.CONNECTING)
      setError(null)

      // 1. Request ephemeral token from backend
      console.log('Requesting ephemeral token from backend...')
      const sessionData = await createVoiceSession({
        system_prompt: systemPrompt,
        voice_name: voiceName,
      })

      console.log('Received voice session:', {
        model: sessionData.model,
        voice: sessionData.voice_name,
        expires: sessionData.expires_at,
      })

      // 2. Initialize audio contexts
      ensureAudioContexts()
      if (audioContextRef.current?.state === 'suspended') {
        await audioContextRef.current.resume()
      }

      // 3. Get microphone (requires HTTPS or localhost)
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error(
          'El micrófono requiere HTTPS. Accede a https://nouxcube.local:3000 o usa localhost.'
        )
      }
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream

      // 4. Connect to Gemini using ephemeral token
      const { GoogleGenAI, Modality } = await import('@google/genai')
      const ai = new GoogleGenAI({ apiKey: sessionData.ephemeral_token })

      const session = await ai.live.connect({
        model: sessionData.model,
        callbacks: {
          onopen: () => {
            console.log('Gemini Live Connected')
            setConnectionState(VoiceConnectionState.CONNECTED)
            setIsListening(true)

            // Start processing input audio
            if (!inputAudioContextRef.current || !streamRef.current) return

            const source = inputAudioContextRef.current.createMediaStreamSource(streamRef.current)
            sourceRef.current = source

            const processor = inputAudioContextRef.current.createScriptProcessor(2048, 1, 1)
            processorRef.current = processor

            processor.onaudioprocess = (e) => {
              const inputData = e.inputBuffer.getChannelData(0)
              const pcmBlob = createPcmBlob(inputData)

              if (sessionRef.current) {
                sessionRef.current.sendRealtimeInput({ media: pcmBlob })
              }
            }

            source.connect(processor)
            processor.connect(inputAudioContextRef.current.destination)
          },
          onmessage: async (message: any) => {
            // Handle Audio Output
            const base64Audio = message.serverContent?.modelTurn?.parts?.[0]?.inlineData?.data
            if (base64Audio && audioContextRef.current && analyserRef.current) {
              setIsSpeaking(true)
              const ctx = audioContextRef.current

              const audioBuffer = await decodeAudioData(
                base64ToUint8Array(base64Audio),
                ctx,
                24000,
                1
              )

              const now = ctx.currentTime
              nextStartTimeRef.current = Math.max(nextStartTimeRef.current, now)

              const bufferSource = ctx.createBufferSource()
              bufferSource.buffer = audioBuffer
              bufferSource.connect(analyserRef.current)

              bufferSource.onended = () => {
                sourcesRef.current.delete(bufferSource)
                if (sourcesRef.current.size === 0) {
                  setTimeout(() => setIsSpeaking(false), 200)
                }
              }

              bufferSource.start(nextStartTimeRef.current)
              nextStartTimeRef.current += audioBuffer.duration
              sourcesRef.current.add(bufferSource)
            }

            // Handle text response
            const textContent = message.serverContent?.modelTurn?.parts?.[0]?.text
            if (textContent) {
              setResponse(prev => prev + textContent)
              onResponse?.(textContent)
            }

            // Handle interruption
            if (message.serverContent?.interrupted) {
              console.log("Interrupted")
              sourcesRef.current.forEach(s => {
                try { s.stop() } catch (e) {}
              })
              sourcesRef.current.clear()
              nextStartTimeRef.current = 0
              setIsSpeaking(false)
            }
          },
          onclose: () => {
            console.log('Session closed')
            disconnect()
          },
          onerror: (e: any) => {
            console.error('Session error', e)
            setError('Connection error')
            onError?.('Connection error')
            disconnect()
          }
        },
        config: {
          responseModalities: [Modality.AUDIO],
          speechConfig: {
            voiceConfig: { prebuiltVoiceConfig: { voiceName: sessionData.voice_name } },
          },
          // System prompt is already configured server-side in the ephemeral token
          // systemInstruction: sessionData.system_prompt,
        },
      })

      sessionRef.current = session

    } catch (err: any) {
      console.error('Gemini connection error:', err)
      setError(err.message || 'Failed to connect')
      onError?.(err.message || 'Failed to connect')
      setConnectionState(VoiceConnectionState.ERROR)
    }
  }, [voiceName, systemPrompt, ensureAudioContexts, onResponse, onError])

  // Connect to Kokoro TTS (local)
  const connectKokoro = useCallback(async () => {
    try {
      setConnectionState(VoiceConnectionState.CONNECTING)
      setError(null)

      ensureAudioContexts()
      if (audioContextRef.current?.state === 'suspended') {
        await audioContextRef.current.resume()
      }

      // Get microphone
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream

      // Setup audio processing
      if (!inputAudioContextRef.current) return

      const source = inputAudioContextRef.current.createMediaStreamSource(stream)
      sourceRef.current = source

      const processor = inputAudioContextRef.current.createScriptProcessor(2048, 1, 1)
      processorRef.current = processor

      // Accumulate audio data
      processor.onaudioprocess = (e) => {
        const inputData = e.inputBuffer.getChannelData(0)
        audioBufferRef.current.push(new Float32Array(inputData))
      }

      source.connect(processor)
      processor.connect(inputAudioContextRef.current.destination)

      setConnectionState(VoiceConnectionState.CONNECTED)
      setIsListening(true)

      console.log('Kokoro TTS mode ready')

    } catch (err: any) {
      console.error(err)
      setError(err.message || 'Failed to initialize Kokoro TTS')
      onError?.(err.message || 'Failed to initialize Kokoro TTS')
      setConnectionState(VoiceConnectionState.ERROR)
    }
  }, [ensureAudioContexts, onError])

  // Send text to Kokoro TTS for speech synthesis
  // Uses OpenAI-compatible API: POST /v1/audio/speech
  const sendToKokoro = useCallback(async (text: string) => {
    if (!audioContextRef.current || !analyserRef.current) return

    try {
      setIsSpeaking(true)

      // Call Kokoro-FastAPI (OpenAI-compatible endpoint)
      const response = await fetch(`${kokoroBaseUrl}/v1/audio/speech`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: 'kokoro',
          input: text,
          voice: kokoroVoice,  // e.g., 'af_bella', 'af_sarah', 'am_adam'
          response_format: 'mp3',
          speed: 1.0,
        })
      })

      if (!response.ok) {
        throw new Error(`Kokoro TTS error: ${response.status}`)
      }

      const audioData = await response.arrayBuffer()
      const audioBuffer = await audioContextRef.current.decodeAudioData(audioData)

      const bufferSource = audioContextRef.current.createBufferSource()
      bufferSource.buffer = audioBuffer
      bufferSource.connect(analyserRef.current)

      bufferSource.onended = () => {
        setIsSpeaking(false)
      }

      bufferSource.start()

    } catch (err: any) {
      console.error('Kokoro TTS error:', err)
      setIsSpeaking(false)
      onError?.(err.message)
    }
  }, [kokoroBaseUrl, kokoroVoice, onError])

  // Main connect function
  const connect = useCallback(async () => {
    if (ttsProvider === 'gemini') {
      await connectGemini()
    } else {
      await connectKokoro()
    }
  }, [ttsProvider, connectGemini, connectKokoro])

  // Disconnect
  const disconnect = useCallback(() => {
    sessionRef.current = null

    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop())
      streamRef.current = null
    }

    if (processorRef.current && inputAudioContextRef.current) {
      processorRef.current.disconnect()
      sourceRef.current?.disconnect()
      processorRef.current = null
    }

    sourcesRef.current.forEach(s => {
      try { s.stop() } catch(e) {}
    })
    sourcesRef.current.clear()
    nextStartTimeRef.current = 0
    audioBufferRef.current = []

    setIsSpeaking(false)
    setIsListening(false)
    setConnectionState(VoiceConnectionState.DISCONNECTED)
    setTranscript('')
    setResponse('')
  }, [])

  // Interrupt current speech
  const interrupt = useCallback(() => {
    sourcesRef.current.forEach(s => {
      try { s.stop() } catch(e) {}
    })
    sourcesRef.current.clear()
    nextStartTimeRef.current = 0
    setIsSpeaking(false)
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      disconnect()
      if (audioContextRef.current) audioContextRef.current.close()
      if (inputAudioContextRef.current) inputAudioContextRef.current.close()
    }
  }, [disconnect])

  return {
    connectionState,
    isListening,
    isSpeaking,
    transcript,
    response,
    error,
    connect,
    disconnect,
    interrupt,
    analyser: analyserRef.current,
  }
}
