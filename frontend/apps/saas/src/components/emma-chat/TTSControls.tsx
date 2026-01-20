/**
 * TTS Controls Component
 *
 * Audio playback controls for Text-to-Speech in Emma Chat.
 * Displays play/pause button with loading and error states.
 */

"use client";

import { useCallback, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Volume2,
  Pause,
  Loader2,
  AlertCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useTTS, TTSStatus } from "@/hooks/use-tts";

interface TTSControlsProps {
  /** Text to synthesize */
  text: string;
  /** Additional CSS classes */
  className?: string;
  /** Size variant */
  size?: "sm" | "md" | "lg";
  /** Whether to show as icon-only button */
  iconOnly?: boolean;
  /** Voice ID to use */
  voiceId?: string;
  /** Language code */
  language?: string;
  /** Disabled state */
  disabled?: boolean;
  /** Auto-play on mount (for new messages) */
  autoPlayOnMount?: boolean;
}

/**
 * TTS Controls - Play/Pause button for text-to-speech
 *
 * @example
 * ```tsx
 * <TTSControls
 *   text="Hello, this is Emma speaking."
 *   size="sm"
 *   iconOnly
 * />
 * ```
 */
export function TTSControls({
  text,
  className,
  size = "sm",
  iconOnly = true,
  voiceId,
  language = "es-ES",
  disabled = false,
  autoPlayOnMount = false,
}: TTSControlsProps) {
  const {
    status,
    error,
    isPlaying,
    isLoading,
    isStreaming,
    speak,
    stop,
    toggle,
  } = useTTS({
    defaultVoiceId: voiceId,
    defaultLanguage: language,
    autoPlay: true,
    // Streaming enabled - uses WebSocket proxy through main backend API
    useStreaming: true,
  });

  // Track which text has been auto-played to avoid repeats
  const autoPlayedTextRef = useRef<string | null>(null);
  const pendingTimerRef = useRef<NodeJS.Timeout | null>(null);

  // Auto-play on mount if enabled - only for new unique text
  useEffect(() => {
    // Debug logging for autoplay
    if (autoPlayOnMount) {
      console.log("[TTS AutoPlay] Checking conditions:", {
        autoPlayOnMount,
        hasText: !!text,
        textLength: text?.trim().length || 0,
        status,
        alreadyPlayed: autoPlayedTextRef.current === text,
      });
    }

    // Only auto-play if:
    // - autoPlayOnMount is enabled
    // - we have text
    // - status is idle (not already playing/loading)
    // - this exact text hasn't been auto-played yet
    if (
      autoPlayOnMount &&
      text &&
      text.trim().length > 0 &&
      status === "idle" &&
      autoPlayedTextRef.current !== text
    ) {
      console.log("[TTS AutoPlay] Triggering autoplay for text:", text.substring(0, 50) + "...");
      autoPlayedTextRef.current = text;

      // Clear any pending timer
      if (pendingTimerRef.current) {
        clearTimeout(pendingTimerRef.current);
      }

      // Small delay to ensure component is fully mounted and audio context is ready
      pendingTimerRef.current = setTimeout(() => {
        console.log("[TTS AutoPlay] Calling speak()");
        speak(text);
        pendingTimerRef.current = null;
      }, 300);
    }

    // Cleanup only the timer, not a mounted flag
    return () => {
      if (pendingTimerRef.current) {
        clearTimeout(pendingTimerRef.current);
        pendingTimerRef.current = null;
      }
    };
  }, [autoPlayOnMount, text, status, speak]);

  // Handle click - speak or toggle
  const handleClick = useCallback(async () => {
    if (isPlaying) {
      stop();
    } else if (status === "paused") {
      toggle();
    } else {
      await speak(text);
    }
  }, [isPlaying, status, stop, toggle, speak, text]);

  // Icon based on status
  const Icon = getIcon(status);
  const iconSize = getIconSize(size);

  // Tooltip text based on status
  const tooltipText = getTooltipText(status, error);

  // Button variant based on status
  const variant = status === "error" ? "destructive" : "ghost";

  if (!text || text.trim().length === 0) {
    return null;
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant={variant}
          size={size === "lg" ? "default" : "icon"}
          className={cn(
            "relative",
            size === "sm" && "h-7 w-7",
            size === "md" && "h-8 w-8",
            size === "lg" && "h-9 w-9",
            isPlaying && "text-primary",
            isLoading && "animate-pulse",
            className
          )}
          onClick={handleClick}
          disabled={disabled || (isLoading && !isStreaming)}
          aria-label={tooltipText}
        >
          <Icon className={iconSize} />
          {!iconOnly && (
            <span className="ml-2">
              {isPlaying ? "Detener" : "Escuchar"}
            </span>
          )}
        </Button>
      </TooltipTrigger>
      <TooltipContent side="top">
        <p>{tooltipText}</p>
      </TooltipContent>
    </Tooltip>
  );
}

/**
 * Get icon component based on TTS status
 */
function getIcon(status: TTSStatus) {
  switch (status) {
    case "loading":
    case "streaming":
      return Loader2;
    case "playing":
      return Pause;
    case "error":
      return AlertCircle;
    case "paused":
    case "idle":
    default:
      return Volume2;
  }
}

/**
 * Get icon size class based on button size
 */
function getIconSize(size: "sm" | "md" | "lg"): string {
  switch (size) {
    case "sm":
      return "h-3.5 w-3.5";
    case "md":
      return "h-4 w-4";
    case "lg":
      return "h-5 w-5";
  }
}

/**
 * Get tooltip text based on status
 */
function getTooltipText(status: TTSStatus, error: string | null): string {
  switch (status) {
    case "loading":
      return "Generando audio...";
    case "streaming":
      return "Recibiendo audio en tiempo real...";
    case "playing":
      return "Detener lectura";
    case "paused":
      return "Continuar lectura";
    case "error":
      return error || "Error al generar audio";
    case "idle":
    default:
      return "Escuchar respuesta";
  }
}

/**
 * TTS Status Indicator - Shows current TTS status as a badge
 */
export function TTSStatusIndicator({
  status,
  className,
}: {
  status: TTSStatus;
  className?: string;
}) {
  if (status === "idle") {
    return null;
  }

  const statusConfig = {
    loading: {
      text: "Generando...",
      className: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200",
    },
    streaming: {
      text: "Streaming...",
      className: "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200",
    },
    playing: {
      text: "Reproduciendo",
      className: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
    },
    paused: {
      text: "Pausado",
      className: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
    },
    error: {
      text: "Error",
      className: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
    },
  };

  const config = statusConfig[status as keyof typeof statusConfig];
  if (!config) return null;

  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded text-xs font-medium",
        config.className,
        className
      )}
    >
      {config.text}
    </span>
  );
}

export default TTSControls;
