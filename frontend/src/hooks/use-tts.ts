/**
 * TTS Hook - Text-to-Speech functionality for Emma Chat
 *
 * Provides audio playback controls for synthesized speech,
 * supporting both batch and streaming modes.
 *
 * Streaming mode uses WebSocket to receive audio chunks in real-time,
 * allowing playback to start before the entire text is synthesized.
 */

import { useState, useCallback, useRef, useEffect } from "react";
import { useApiClient } from "@/lib/api-client";
import { useAuth } from "@clerk/nextjs";
import { API_CONFIG } from "@/lib/config";

/**
 * Remove emojis and other non-pronounceable characters from text.
 * TTS systems can't handle emojis and they cause errors or silence.
 */
function sanitizeTextForTTS(text: string): string {
  if (!text) return "";

  // Remove emojis and other symbol characters
  // This regex matches most emoji ranges in Unicode
  const emojiRegex = /[\u{1F600}-\u{1F64F}]|[\u{1F300}-\u{1F5FF}]|[\u{1F680}-\u{1F6FF}]|[\u{1F1E0}-\u{1F1FF}]|[\u{2600}-\u{26FF}]|[\u{2700}-\u{27BF}]|[\u{FE00}-\u{FE0F}]|[\u{1F900}-\u{1F9FF}]|[\u{1FA00}-\u{1FA6F}]|[\u{1FA70}-\u{1FAFF}]|[\u{231A}-\u{231B}]|[\u{23E9}-\u{23F3}]|[\u{23F8}-\u{23FA}]|[\u{25AA}-\u{25AB}]|[\u{25B6}]|[\u{25C0}]|[\u{25FB}-\u{25FE}]|[\u{2614}-\u{2615}]|[\u{2648}-\u{2653}]|[\u{267F}]|[\u{2693}]|[\u{26A1}]|[\u{26AA}-\u{26AB}]|[\u{26BD}-\u{26BE}]|[\u{26C4}-\u{26C5}]|[\u{26CE}]|[\u{26D4}]|[\u{26EA}]|[\u{26F2}-\u{26F3}]|[\u{26F5}]|[\u{26FA}]|[\u{26FD}]|[\u{2702}]|[\u{2705}]|[\u{2708}-\u{270D}]|[\u{270F}]|[\u{2712}]|[\u{2714}]|[\u{2716}]|[\u{271D}]|[\u{2721}]|[\u{2728}]|[\u{2733}-\u{2734}]|[\u{2744}]|[\u{2747}]|[\u{274C}]|[\u{274E}]|[\u{2753}-\u{2755}]|[\u{2757}]|[\u{2763}-\u{2764}]|[\u{2795}-\u{2797}]|[\u{27A1}]|[\u{27B0}]|[\u{27BF}]|[\u{2934}-\u{2935}]|[\u{2B05}-\u{2B07}]|[\u{2B1B}-\u{2B1C}]|[\u{2B50}]|[\u{2B55}]|[\u{3030}]|[\u{303D}]|[\u{3297}]|[\u{3299}]|[\u{200D}]|[\u{20E3}]|[\u{FE0F}]/gu;

  let sanitized = text.replace(emojiRegex, "");

  // Also remove variation selectors and zero-width joiners that might remain
  sanitized = sanitized.replace(/[\u200B-\u200D\uFEFF]/g, "");

  // Clean up multiple spaces that might result from emoji removal
  sanitized = sanitized.replace(/\s{2,}/g, " ").trim();

  return sanitized;
}

export type TTSStatus = "idle" | "loading" | "playing" | "paused" | "error" | "streaming";

export interface TTSVoice {
  voice_id: string;
  name: string;
  language: string;
  gender?: string;
  description?: string;
  provider: string;
}

export interface UseTTSOptions {
  /** Default voice ID to use */
  defaultVoiceId?: string;
  /** Default language code */
  defaultLanguage?: string;
  /** Playback speed (0.5 - 2.0) */
  speed?: number;
  /** Auto-play when audio is ready */
  autoPlay?: boolean;
  /** Use streaming mode (WebSocket) for lower latency */
  useStreaming?: boolean;
  /** Callback when playback starts */
  onPlayStart?: () => void;
  /** Callback when playback ends */
  onPlayEnd?: () => void;
  /** Callback on error */
  onError?: (error: string) => void;
  /** Callback when first audio chunk arrives (streaming mode) */
  onFirstChunk?: () => void;
}

export interface UseTTSReturn {
  /** Current TTS status */
  status: TTSStatus;
  /** Error message if any */
  error: string | null;
  /** Whether audio is currently playing */
  isPlaying: boolean;
  /** Whether audio is loading */
  isLoading: boolean;
  /** Whether streaming is active */
  isStreaming: boolean;
  /** Current audio duration in seconds */
  duration: number;
  /** Current playback position in seconds */
  currentTime: number;
  /** Available voices */
  voices: TTSVoice[];
  /** Currently selected voice */
  selectedVoice: string;
  /** Synthesize and play text */
  speak: (text: string) => Promise<void>;
  /** Stream and play text (real-time) */
  speakStream: (text: string) => Promise<void>;
  /** Stop playback */
  stop: () => void;
  /** Pause playback */
  pause: () => void;
  /** Resume playback */
  resume: () => void;
  /** Toggle play/pause */
  toggle: () => void;
  /** Set voice */
  setVoice: (voiceId: string) => void;
  /** Load available voices */
  loadVoices: () => Promise<void>;
}

/**
 * Hook for Text-to-Speech functionality
 *
 * @example
 * ```tsx
 * const { speak, speakStream, stop, isPlaying, status } = useTTS({ useStreaming: true });
 *
 * // Streaming mode (recommended for long text)
 * await speakStream("Hello, this is a long text that will start playing immediately.");
 *
 * // Batch mode (for short text)
 * await speak("Hello!");
 *
 * // Stop playback
 * stop();
 * ```
 */
export function useTTS(options: UseTTSOptions = {}): UseTTSReturn {
  const {
    defaultVoiceId = "Carter",
    defaultLanguage = "en-US",
    speed = 1.0,
    autoPlay = true,
    useStreaming = true,
    onPlayStart,
    onPlayEnd,
    onError,
    onFirstChunk,
  } = options;

  const apiClient = useApiClient();
  const { getToken } = useAuth();

  // State
  const [status, setStatus] = useState<TTSStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [duration, setDuration] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  const [voices, setVoices] = useState<TTSVoice[]>([]);
  const [selectedVoice, setSelectedVoice] = useState(defaultVoiceId);

  // Refs for batch mode
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Refs for streaming mode
  const wsRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const audioQueueRef = useRef<AudioBuffer[]>([]);
  const isPlayingRef = useRef(false);
  const currentSourceRef = useRef<AudioBufferSourceNode | null>(null);
  const startTimeRef = useRef(0);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      // Cleanup batch mode
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current.src = "";
      }
      // Cleanup streaming mode
      if (wsRef.current) {
        wsRef.current.close();
      }
      if (audioContextRef.current) {
        audioContextRef.current.close();
      }
    };
  }, []);

  /**
   * Load available TTS voices
   */
  const loadVoices = useCallback(async () => {
    try {
      const response = await apiClient.get<{
        voices: TTSVoice[];
        default_voice_id: string;
      }>(API_CONFIG.ENDPOINTS.TTS_VOICES);

      if (response.error) {
        console.error("Failed to load TTS voices:", response.error);
        return;
      }

      if (response.data) {
        setVoices(response.data.voices || []);
        if (response.data.default_voice_id) {
          setSelectedVoice(response.data.default_voice_id);
        }
      }
    } catch (err) {
      console.error("Failed to load TTS voices:", err);
    }
  }, [apiClient]);

  /**
   * Play queued audio buffers (streaming mode)
   */
  const playNextChunk = useCallback(async () => {
    if (!audioContextRef.current || audioQueueRef.current.length === 0) {
      if (audioQueueRef.current.length === 0 && isPlayingRef.current) {
        // All chunks played
        isPlayingRef.current = false;
        setStatus("idle");
        onPlayEnd?.();
      }
      return;
    }

    const buffer = audioQueueRef.current.shift();
    if (!buffer) return;

    const source = audioContextRef.current.createBufferSource();
    source.buffer = buffer;
    source.connect(audioContextRef.current.destination);

    currentSourceRef.current = source;

    source.onended = () => {
      playNextChunk();
    };

    source.start(0);
  }, [onPlayEnd]);

  /**
   * Decode base64 audio chunk to AudioBuffer
   */
  const decodeAudioChunk = useCallback(async (base64: string): Promise<AudioBuffer | null> => {
    if (!audioContextRef.current || !base64) return null;

    try {
      const binaryString = atob(base64);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }

      const audioBuffer = await audioContextRef.current.decodeAudioData(bytes.buffer);
      return audioBuffer;
    } catch (err) {
      console.error("Failed to decode audio chunk:", err);
      return null;
    }
  }, []);

  /**
   * Stream synthesize and play text (real-time via WebSocket)
   */
  const speakStream = useCallback(
    async (text: string) => {
      console.log("[TTS Stream] speakStream() called with text length:", text?.length || 0);

      // Sanitize text - remove emojis and non-pronounceable characters
      const sanitizedText = sanitizeTextForTTS(text);

      if (!sanitizedText.trim()) {
        console.log("[TTS Stream] empty text after sanitization, returning");
        return;
      }

      console.log("[TTS Stream] sanitized text length:", sanitizedText.length);

      // Close existing connection
      if (wsRef.current) {
        console.log("[TTS Stream] closing existing WebSocket");
        wsRef.current.close();
      }

      setStatus("loading");
      setError(null);
      audioQueueRef.current = [];
      isPlayingRef.current = false;

      try {
        // Initialize AudioContext
        if (!audioContextRef.current || audioContextRef.current.state === "closed") {
          console.log("[TTS Stream] creating new AudioContext");
          audioContextRef.current = new AudioContext();
        }
        if (audioContextRef.current.state === "suspended") {
          console.log("[TTS Stream] resuming suspended AudioContext");
          await audioContextRef.current.resume();
        }

        // Get Clerk token for authentication
        console.log("[TTS Stream] getting auth token...");
        const token = await getToken();
        if (!token) {
          throw new Error("No authentication token available");
        }

        // Construct WebSocket URL to backend proxy
        // The backend proxies to internal TTS service
        const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        const wsHost = API_CONFIG.BASE_URL.replace(/^https?:\/\//, "");
        const wsUrl = `${wsProtocol}//${wsHost}/api/v1/tts/stream?token=${encodeURIComponent(token)}`;

        console.log("[TTS Stream] connecting to WebSocket proxy...");
        // Create WebSocket connection to backend proxy
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        let firstChunkReceived = false;

        ws.onopen = () => {
          // Send synthesis request with sanitized text
          ws.send(JSON.stringify({
            text: sanitizedText,
            voice_id: selectedVoice,
            language: defaultLanguage,
            is_final: true,
          }));
          setStatus("streaming");
        };

        ws.onmessage = async (event) => {
          try {
            const data = JSON.parse(event.data);

            if (data.type === "ping") {
              // Respond to ping
              return;
            }

            if (data.error) {
              throw new Error(data.error);
            }

            if (data.audio_chunk && data.audio_chunk.length > 0) {
              const audioBuffer = await decodeAudioChunk(data.audio_chunk);
              if (audioBuffer) {
                audioQueueRef.current.push(audioBuffer);

                // Start playback on first chunk
                if (!firstChunkReceived) {
                  firstChunkReceived = true;
                  onFirstChunk?.();

                  if (autoPlay) {
                    isPlayingRef.current = true;
                    startTimeRef.current = audioContextRef.current?.currentTime || 0;
                    setStatus("playing");
                    onPlayStart?.();
                    playNextChunk();
                  }
                }
              }
            }

            if (data.is_final) {
              // All chunks received
              ws.close();
            }
          } catch (err) {
            console.error("Error processing WebSocket message:", err);
          }
        };

        ws.onerror = (event) => {
          console.error("WebSocket error:", event);
          setStatus("error");
          setError("WebSocket connection error");
          onError?.("WebSocket connection error");
        };

        ws.onclose = () => {
          wsRef.current = null;
        };

      } catch (err) {
        const errorMessage =
          err instanceof Error ? err.message : "TTS streaming failed";
        setStatus("error");
        setError(errorMessage);
        onError?.(errorMessage);
      }
    },
    [
      getToken,
      selectedVoice,
      defaultLanguage,
      autoPlay,
      decodeAudioChunk,
      playNextChunk,
      onPlayStart,
      onFirstChunk,
      onError,
    ]
  );

  /**
   * Synthesize text and play audio (batch mode)
   */
  const speak = useCallback(
    async (text: string) => {
      console.log("[TTS] speak() called with text length:", text?.length || 0);

      // Sanitize text - remove emojis and non-pronounceable characters
      const sanitizedText = sanitizeTextForTTS(text);

      if (!sanitizedText.trim()) {
        console.log("[TTS] speak() - empty text after sanitization, returning");
        return;
      }

      console.log("[TTS] speak() - sanitized text length:", sanitizedText.length);

      // If streaming is preferred and text is long, use streaming
      if (useStreaming && sanitizedText.length > 100) {
        console.log("[TTS] speak() - using streaming mode for long text");
        return speakStream(sanitizedText);
      }

      console.log("[TTS] speak() - using batch mode");
      setStatus("loading");
      setError(null);

      try {
        const response = await apiClient.post<{
          audio_base64: string;
          format: string;
          duration_ms: number;
          sample_rate: number;
          text_length: number;
        }>(API_CONFIG.ENDPOINTS.TTS_SYNTHESIZE, {
          text: sanitizedText,
          voice_id: selectedVoice,
          language: defaultLanguage,
          speed,
        });

        if (response.error) {
          throw new Error(response.error);
        }

        if (!response.data?.audio_base64) {
          throw new Error("No audio data received");
        }

        // Create audio from base64
        const audioBlob = base64ToBlob(response.data.audio_base64, "audio/wav");
        const audioUrl = URL.createObjectURL(audioBlob);

        // Create or reuse audio element
        if (!audioRef.current) {
          audioRef.current = new Audio();
        }

        const audio = audioRef.current;

        // Set up event handlers
        audio.onloadedmetadata = () => {
          setDuration(audio.duration);
        };

        audio.ontimeupdate = () => {
          setCurrentTime(audio.currentTime);
        };

        audio.onended = () => {
          setStatus("idle");
          setCurrentTime(0);
          onPlayEnd?.();
          URL.revokeObjectURL(audioUrl);
        };

        audio.onerror = () => {
          setStatus("error");
          setError("Audio playback error");
          onError?.("Audio playback error");
          URL.revokeObjectURL(audioUrl);
        };

        // Load and play
        audio.src = audioUrl;

        if (autoPlay) {
          await audio.play();
          setStatus("playing");
          onPlayStart?.();
        } else {
          setStatus("paused");
        }
      } catch (err) {
        const errorMessage =
          err instanceof Error ? err.message : "TTS synthesis failed";
        setStatus("error");
        setError(errorMessage);
        onError?.(errorMessage);
      }
    },
    [
      apiClient,
      selectedVoice,
      defaultLanguage,
      speed,
      autoPlay,
      useStreaming,
      speakStream,
      onPlayStart,
      onPlayEnd,
      onError,
    ]
  );

  /**
   * Stop audio playback
   */
  const stop = useCallback(() => {
    // Stop batch mode
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
    }

    // Stop streaming mode
    if (wsRef.current) {
      wsRef.current.close();
    }
    if (currentSourceRef.current) {
      try {
        currentSourceRef.current.stop();
      } catch {
        // Ignore if already stopped
      }
    }
    audioQueueRef.current = [];
    isPlayingRef.current = false;

    setStatus("idle");
    setCurrentTime(0);
  }, []);

  /**
   * Pause audio playback
   */
  const pause = useCallback(() => {
    if (audioRef.current && status === "playing") {
      audioRef.current.pause();
      setStatus("paused");
    }
    // Note: Streaming mode doesn't support pause well due to AudioContext limitations
    if (status === "playing" && audioContextRef.current) {
      audioContextRef.current.suspend();
      setStatus("paused");
    }
  }, [status]);

  /**
   * Resume audio playback
   */
  const resume = useCallback(async () => {
    if (audioRef.current && status === "paused") {
      await audioRef.current.play();
      setStatus("playing");
    }
    if (status === "paused" && audioContextRef.current) {
      await audioContextRef.current.resume();
      setStatus("playing");
    }
  }, [status]);

  /**
   * Toggle play/pause
   */
  const toggle = useCallback(() => {
    if (status === "playing") {
      pause();
    } else if (status === "paused") {
      resume();
    }
  }, [status, pause, resume]);

  /**
   * Set voice
   */
  const setVoice = useCallback((voiceId: string) => {
    setSelectedVoice(voiceId);
  }, []);

  return {
    status,
    error,
    isPlaying: status === "playing",
    isLoading: status === "loading",
    isStreaming: status === "streaming",
    duration,
    currentTime,
    voices,
    selectedVoice,
    speak,
    speakStream,
    stop,
    pause,
    resume,
    toggle,
    setVoice,
    loadVoices,
  };
}

/**
 * Convert base64 string to Blob
 */
function base64ToBlob(base64: string, mimeType: string): Blob {
  const byteCharacters = atob(base64);
  const byteNumbers = new Array(byteCharacters.length);

  for (let i = 0; i < byteCharacters.length; i++) {
    byteNumbers[i] = byteCharacters.charCodeAt(i);
  }

  const byteArray = new Uint8Array(byteNumbers);
  return new Blob([byteArray], { type: mimeType });
}

export default useTTS;
