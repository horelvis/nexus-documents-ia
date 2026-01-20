'use client'

/**
 * AudioPlayer - Podcast Player Component
 *
 * Compact audio player for generated podcasts with status display.
 */

import { useState, useRef, useEffect } from 'react'
import { IconPlayerPlay, IconPlayerPause, IconLoader2, IconAlertCircle, IconDownload } from '@tabler/icons-react'
import { Button, Progress } from '@nexus/shared/ui'
import { cn } from '@/lib/utils'
import { NotebookAudio, notebookService } from '@/lib/services/notebook.service'

interface AudioPlayerProps {
  audio: NotebookAudio
  notebookId: string
}

export function AudioPlayer({ audio: initialAudio, notebookId }: AudioPlayerProps) {
  const [audio, setAudio] = useState(initialAudio)
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  // Poll for status updates while generating
  useEffect(() => {
    if (audio.status === 'pending' || audio.status === 'generating_script' ||
        audio.status === 'generating_audio' || audio.status === 'stitching') {
      const interval = setInterval(async () => {
        try {
          const response = await notebookService.getAudioStatus(notebookId, audio.id)
          if (response.data) {
            setAudio(prev => ({
              ...prev,
              status: response.data!.status,
              status_message: response.data!.status_message,
              progress_percent: response.data!.progress_percent,
              error_message: response.data!.error_message,
            }))

            // Stop polling if completed or failed
            if (response.data.status === 'completed' || response.data.status === 'failed') {
              clearInterval(interval)
              // Reload full audio data to get URL
              const fullResponse = await notebookService.getAudio(notebookId, audio.id)
              if (fullResponse.data) {
                setAudio(fullResponse.data)
              }
            }
          }
        } catch (err) {
          console.error('Error polling audio status:', err)
        }
      }, 3000)

      return () => clearInterval(interval)
    }
  }, [audio.status, audio.id, notebookId])

  const togglePlay = () => {
    if (!audioRef.current || !audio.audio_url) return

    if (isPlaying) {
      audioRef.current.pause()
    } else {
      audioRef.current.play()
    }
    setIsPlaying(!isPlaying)
  }

  const handleTimeUpdate = () => {
    if (audioRef.current) {
      setCurrentTime(audioRef.current.currentTime)
    }
  }

  const handleLoadedMetadata = () => {
    if (audioRef.current) {
      setDuration(audioRef.current.duration)
    }
  }

  const handleEnded = () => {
    setIsPlaying(false)
    setCurrentTime(0)
  }

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }

  const getStatusMessage = () => {
    switch (audio.status) {
      case 'pending':
        return 'En cola...'
      case 'generating_script':
        return 'Generando guión...'
      case 'generating_audio':
        return 'Sintetizando voz...'
      case 'stitching':
        return 'Procesando audio...'
      case 'completed':
        return audio.duration_formatted || formatTime((audio.duration_ms || 0) / 1000)
      case 'failed':
        return 'Error'
      default:
        return audio.status
    }
  }

  const isGenerating = ['pending', 'generating_script', 'generating_audio', 'stitching'].includes(audio.status)

  return (
    <div className={cn(
      "p-3 rounded-lg border",
      audio.status === 'failed' && "border-destructive bg-destructive/5",
      audio.status === 'completed' && "bg-muted/50"
    )}>
      {/* Hidden audio element */}
      {audio.audio_url && (
        <audio
          ref={audioRef}
          src={audio.audio_url}
          onTimeUpdate={handleTimeUpdate}
          onLoadedMetadata={handleLoadedMetadata}
          onEnded={handleEnded}
        />
      )}

      <div className="flex items-center gap-3">
        {/* Play/Pause or Status Icon */}
        {audio.status === 'completed' && audio.audio_url ? (
          <Button
            variant="outline"
            size="icon"
            className="h-8 w-8 shrink-0"
            onClick={togglePlay}
          >
            {isPlaying ? (
              <IconPlayerPause className="h-4 w-4" />
            ) : (
              <IconPlayerPlay className="h-4 w-4" />
            )}
          </Button>
        ) : audio.status === 'failed' ? (
          <div className="h-8 w-8 rounded-lg bg-destructive/10 flex items-center justify-center shrink-0">
            <IconAlertCircle className="h-4 w-4 text-destructive" />
          </div>
        ) : (
          <div className="h-8 w-8 rounded-lg bg-muted flex items-center justify-center shrink-0">
            <IconLoader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          </div>
        )}

        {/* Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium truncate">
              {audio.config?.tone === 'conversational' ? 'Conversacional' :
               audio.config?.tone === 'formal' ? 'Formal' : 'Educativo'}
            </p>
            <span className="text-xs text-muted-foreground">
              {getStatusMessage()}
            </span>
          </div>

          {/* Progress bar */}
          {isGenerating ? (
            <Progress value={audio.progress_percent} className="h-1 mt-2" />
          ) : audio.status === 'completed' && duration > 0 ? (
            <div className="mt-2">
              <Progress value={(currentTime / duration) * 100} className="h-1" />
              <div className="flex justify-between text-xs text-muted-foreground mt-1">
                <span>{formatTime(currentTime)}</span>
                <span>{formatTime(duration)}</span>
              </div>
            </div>
          ) : audio.status === 'failed' && audio.error_message ? (
            <p className="text-xs text-destructive mt-1 truncate">
              {audio.error_message}
            </p>
          ) : null}
        </div>

        {/* Download button */}
        {audio.status === 'completed' && audio.audio_url && (
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0"
            asChild
          >
            <a href={audio.audio_url} download>
              <IconDownload className="h-4 w-4" />
            </a>
          </Button>
        )}
      </div>
    </div>
  )
}
