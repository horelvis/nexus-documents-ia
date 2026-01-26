'use client'

/**
 * PresentationViewer - PowerPoint Presentation Viewer Component
 *
 * Compact presentation viewer for generated PPTX files with status display.
 */

import { useState, useEffect } from 'react'
import {
  IconPresentation,
  IconLoader2,
  IconAlertCircle,
  IconDownload,
  IconTrash,
  IconChevronDown,
  IconChevronRight
} from '@tabler/icons-react'
import { Button, Progress, Collapsible, CollapsibleContent, CollapsibleTrigger } from '@nexus/shared/ui'
import { cn } from '@/lib/utils'
import { NotebookPresentation, notebookService } from '@/lib/services/notebook.service'

interface PresentationViewerProps {
  presentation: NotebookPresentation
  notebookId: string
  onDeleted?: () => void
}

export function PresentationViewer({ presentation: initialPresentation, notebookId, onDeleted }: PresentationViewerProps) {
  const [presentation, setPresentation] = useState(initialPresentation)
  const [isDeleting, setIsDeleting] = useState(false)
  const [isDownloading, setIsDownloading] = useState(false)
  const [showOutline, setShowOutline] = useState(false)

  const handleDownload = async () => {
    if (isDownloading) return

    setIsDownloading(true)
    try {
      const result = await notebookService.downloadPresentation(
        notebookId,
        presentation.id,
        `${presentation.config?.template || 'presentation'}_${presentation.id.slice(0, 8)}.pptx`
      )
      if (!result.success) {
        console.error('Error downloading presentation:', result.error)
      }
    } catch (err) {
      console.error('Error downloading presentation:', err)
    } finally {
      setIsDownloading(false)
    }
  }

  const handleDelete = async () => {
    if (isDeleting) return

    setIsDeleting(true)
    try {
      const response = await notebookService.deletePresentation(notebookId, presentation.id)
      if (!response.error) {
        onDeleted?.()
      }
    } catch (err) {
      console.error('Error deleting presentation:', err)
    } finally {
      setIsDeleting(false)
    }
  }

  // Poll for status updates while generating
  useEffect(() => {
    if (
      presentation.status === 'pending' ||
      presentation.status === 'analyzing' ||
      presentation.status === 'generating_outline' ||
      presentation.status === 'generating_slides' ||
      presentation.status === 'uploading'
    ) {
      const interval = setInterval(async () => {
        try {
          const response = await notebookService.getPresentationStatus(notebookId, presentation.id)
          if (response.data) {
            setPresentation(prev => ({
              ...prev,
              status: response.data!.status,
              status_message: response.data!.status_message,
              progress_percent: response.data!.progress_percent,
              error_message: response.data!.error_message,
            }))

            // Stop polling if completed or failed
            if (response.data.status === 'completed' || response.data.status === 'failed') {
              clearInterval(interval)
              // Reload full presentation data to get URL
              const fullResponse = await notebookService.getPresentation(notebookId, presentation.id)
              if (fullResponse.data) {
                setPresentation(fullResponse.data)
              }
            }
          }
        } catch (err) {
          console.error('Error polling presentation status:', err)
        }
      }, 3000)

      return () => clearInterval(interval)
    }
  }, [presentation.status, presentation.id, notebookId])

  const getStatusMessage = () => {
    switch (presentation.status) {
      case 'pending':
        return 'En cola...'
      case 'analyzing':
        return 'Analizando fuentes...'
      case 'generating_outline':
        return 'Generando esquema...'
      case 'generating_slides':
        return 'Creando diapositivas...'
      case 'uploading':
        return 'Subiendo archivo...'
      case 'completed':
        return `${presentation.slide_count || 0} diapositivas`
      case 'failed':
        return 'Error'
      default:
        return presentation.status
    }
  }

  const getTemplateName = () => {
    switch (presentation.config?.template) {
      case 'corporate':
        return 'Corporativo'
      case 'educational':
        return 'Educativo'
      case 'minimal':
        return 'Minimalista'
      case 'creative':
        return 'Creativo'
      case 'nouxcube':
        return 'NouxCube'
      default:
        return 'Presentacion'
    }
  }

  const formatFileSize = (bytes: number | undefined) => {
    if (!bytes) return ''
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const isGenerating = [
    'pending',
    'analyzing',
    'generating_outline',
    'generating_slides',
    'uploading'
  ].includes(presentation.status)

  return (
    <div className={cn(
      "p-2 rounded-lg border",
      presentation.status === 'failed' && "border-destructive bg-destructive/5",
      presentation.status === 'completed' && "bg-muted/50"
    )}>
      {/* Header row with icon, title, and actions */}
      <div className="flex items-center gap-2">
        {/* Status Icon */}
        {presentation.status === 'completed' && presentation.pptx_url ? (
          <div className="h-6 w-6 rounded bg-blue-500/10 flex items-center justify-center shrink-0">
            <IconPresentation className="h-3.5 w-3.5 text-blue-500" />
          </div>
        ) : presentation.status === 'failed' ? (
          <div className="h-6 w-6 rounded bg-destructive/10 flex items-center justify-center shrink-0">
            <IconAlertCircle className="h-3.5 w-3.5 text-destructive" />
          </div>
        ) : (
          <div className="h-6 w-6 rounded bg-muted flex items-center justify-center shrink-0">
            <IconLoader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
          </div>
        )}

        {/* Title and status */}
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium truncate">
            {getTemplateName()}
          </p>
        </div>

        {/* Action buttons - always visible */}
        <div className="flex gap-0.5 shrink-0">
          {presentation.status === 'completed' && presentation.pptx_url && (
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              onClick={handleDownload}
              disabled={isDownloading}
            >
              {isDownloading ? (
                <IconLoader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <IconDownload className="h-3.5 w-3.5" />
              )}
            </Button>
          )}
          {(presentation.status === 'completed' || presentation.status === 'failed') && (
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 text-muted-foreground hover:text-destructive"
              onClick={handleDelete}
              disabled={isDeleting}
            >
              {isDeleting ? (
                <IconLoader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <IconTrash className="h-3.5 w-3.5" />
              )}
            </Button>
          )}
        </div>
      </div>

      {/* Status and progress - below header */}
      <div className="mt-1.5 pl-8">
        <span className="text-[10px] text-muted-foreground">
          {getStatusMessage()}
        </span>

        {/* Progress bar */}
        {isGenerating ? (
          <div className="mt-1">
            <Progress value={presentation.progress_percent} className="h-1" />
            {presentation.status_message && (
              <p className="text-[10px] text-muted-foreground mt-0.5 truncate">
                {presentation.status_message}
              </p>
            )}
          </div>
        ) : presentation.status === 'completed' ? (
          <div className="space-y-1">
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] text-muted-foreground">
                {formatFileSize(presentation.file_size_bytes)}
              </span>
              {presentation.outline && presentation.outline.length > 0 && (
                <button
                  onClick={() => setShowOutline(!showOutline)}
                  className="text-[10px] text-blue-500 hover:text-blue-600 flex items-center gap-0.5"
                >
                  {showOutline ? (
                    <IconChevronDown className="h-3 w-3" />
                  ) : (
                    <IconChevronRight className="h-3 w-3" />
                  )}
                  {presentation.outline.length} diapositivas
                </button>
              )}
            </div>
            {/* Slide outline preview */}
            {showOutline && presentation.outline && presentation.outline.length > 0 && (
              <div className="mt-2 space-y-1 border-l-2 border-blue-200 pl-2">
                {presentation.outline.map((slide: { slide_number?: number; title?: string }, index: number) => (
                  <div key={index} className="text-[10px] text-muted-foreground">
                    <span className="font-medium text-foreground">{slide.slide_number || index + 1}.</span>{' '}
                    {slide.title || 'Sin título'}
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : presentation.status === 'failed' && presentation.error_message ? (
          <p className="text-[10px] text-destructive truncate">
            {presentation.error_message}
          </p>
        ) : null}
      </div>
    </div>
  )
}
