'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
import { IconSend, IconLoader2, IconPlus, IconUpload, IconFolder, IconFileCheck } from '@tabler/icons-react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'
import { Attachment, UploadedAttachment, ATTACHMENT_LIMITS } from '@/lib/types/emma'
import { IndexedDocsPicker } from './IndexedDocsPicker'
import { AttachmentPreviewStrip } from './AttachmentPreviewStrip'

interface EmmaQueryInputProps {
  onSendQuery: (query: string, attachments?: Attachment[]) => Promise<void>
  onVerifiedGeneration?: (topic: string, attachments?: Attachment[]) => void
  isLoading?: boolean
  disabled?: boolean
  placeholder?: string
  className?: string
  maxAttachments?: number
}

export function EmmaQueryInput({
  onSendQuery,
  onVerifiedGeneration,
  isLoading = false,
  disabled = false,
  placeholder = 'Pregúntame sobre tus documentos...',
  className,
  maxAttachments = ATTACHMENT_LIMITS.maxAttachments,
}: EmmaQueryInputProps) {
  const [query, setQuery] = useState('')
  const [attachments, setAttachments] = useState<Attachment[]>([])
  const [isIndexedPickerOpen, setIsIndexedPickerOpen] = useState(false)
  const [isDropdownOpen, setIsDropdownOpen] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Focus textarea when loading completes
  useEffect(() => {
    if (textareaRef.current && !disabled && !isLoading) {
      // Small delay to ensure DOM is ready after state updates
      const timer = setTimeout(() => {
        textareaRef.current?.focus()
        console.log('[EmmaQueryInput] Focus restored after loading')
      }, 50)
      return () => clearTimeout(timer)
    }
  }, [disabled, isLoading])

  const isVerificarCommand = query.trimStart().startsWith('/verificar ')

  const handleSubmit = async () => {
    if ((!query.trim() && attachments.length === 0) || isLoading || disabled) return

    const queryToSend = query.trim()
    const attachmentsToSend = [...attachments]

    setQuery('')
    setAttachments([])

    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }

    // Detect /verificar command
    if (queryToSend.startsWith('/verificar ') && onVerifiedGeneration) {
      const topic = queryToSend.slice('/verificar '.length).trim()
      if (topic) {
        Promise.resolve(onVerifiedGeneration(topic, attachmentsToSend.length > 0 ? attachmentsToSend : undefined)).catch((err) => {
          console.error('[EmmaQueryInput] Verified generation error:', err)
        })
        return
      }
    }

    await onSendQuery(queryToSend, attachmentsToSend.length > 0 ? attachmentsToSend : undefined)
  }

  const handleVerifiedClick = () => {
    if (isLoading || disabled || !onVerifiedGeneration) return
    const topic = query.trim() || 'Genera un documento verificado basado en los documentos adjuntos'
    const attachmentsToSend = [...attachments]
    setQuery('')
    setAttachments([])
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
    // Call as void but catch any promise rejection to prevent unhandled errors
    Promise.resolve(onVerifiedGeneration(topic, attachmentsToSend.length > 0 ? attachmentsToSend : undefined)).catch((err) => {
      console.error('[EmmaQueryInput] Verified generation error:', err)
    })
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setQuery(e.target.value)
    const textarea = e.target
    textarea.style.height = 'auto'
    const newHeight = Math.min(Math.max(textarea.scrollHeight, 52), 200)
    textarea.style.height = `${newHeight}px`
  }

  const handleLocalUpload = () => {
    // Close dropdown first, then trigger file input
    setIsDropdownOpen(false)
    setTimeout(() => {
      fileInputRef.current?.click()
    }, 50)
  }

  const handleOpenIndexedPicker = () => {
    // Close dropdown first, then open dialog
    setIsDropdownOpen(false)
    setTimeout(() => {
      setIsIndexedPickerOpen(true)
    }, 50)
  }

  const handleFilesChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files) return
    setUploadError(null)

    const files = Array.from(e.target.files)
    const remainingSlots = maxAttachments - attachments.length

    const validFiles: UploadedAttachment[] = []
    for (const file of files) {
      if (validFiles.length >= remainingSlots) {
        setUploadError(`Solo puedes agregar ${remainingSlots} archivos más`)
        break
      }

      if (file.size > ATTACHMENT_LIMITS.maxFileSizeBytes) {
        setUploadError(`"${file.name}" excede ${ATTACHMENT_LIMITS.maxFileSizeMB}MB`)
        continue
      }

      const ext = '.' + file.name.split('.').pop()?.toLowerCase()
      if (!ATTACHMENT_LIMITS.allowedExtensions.includes(ext)) {
        setUploadError(`"${file.name}" no es un tipo permitido`)
        continue
      }

      validFiles.push({
        id: `upload_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`,
        name: file.name,
        type: 'upload',
        file,
        fileType: file.type,
        size: file.size,
        uploadStatus: 'ready',
      })
    }

    if (validFiles.length > 0) {
      setAttachments((prev) => [...prev, ...validFiles])
    }

    e.target.value = ''
    // Restore focus to textarea after file selection
    setTimeout(() => {
      textareaRef.current?.focus()
    }, 100)
  }, [attachments.length, maxAttachments])

  const handleIndexedDocsSelect = (newAttachments: Attachment[]) => {
    setAttachments((prev) => {
      const existingIds = new Set(prev.map((a) => a.id))
      const unique = newAttachments.filter((a) => !existingIds.has(a.id))
      return [...prev, ...unique].slice(0, maxAttachments)
    })
    setIsIndexedPickerOpen(false)
    // Restore focus to textarea after dialog closes
    setTimeout(() => {
      textareaRef.current?.focus()
    }, 100)
  }

  const handleRemoveAttachment = (id: string) => {
    setAttachments((prev) => prev.filter((a) => a.id !== id))
    setUploadError(null)
  }

  const existingAttachmentIds = attachments.map((a) => a.id)
  const hasContent = query.trim().length > 0 || attachments.length > 0
  const canAddMore = attachments.length < maxAttachments

  return (
    <div className={cn('space-y-3', className)}>
      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept={ATTACHMENT_LIMITS.allowedExtensions.join(',')}
        onChange={handleFilesChange}
        className="hidden"
      />

      {/* Attachment preview strip */}
      {attachments.length > 0 && (
        <AttachmentPreviewStrip
          attachments={attachments}
          onRemove={handleRemoveAttachment}
          maxVisible={5}
          className="px-1"
        />
      )}

      {/* Upload error */}
      {uploadError && (
        <p className="text-xs text-destructive px-1">{uploadError}</p>
      )}

      {/* Input container */}
      <div className="relative">
        <Textarea
          ref={textareaRef}
          value={query}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled || isLoading}
          className="pl-10 pr-14 py-3.5 min-h-[52px] max-h-[200px] resize-none rounded-xl border border-border/50 bg-background focus-visible:ring-1 focus-visible:ring-primary/30 focus-visible:border-primary/50"
          rows={1}
        />

        {/* Plus icon with dropdown - INSIDE INPUT LEFT */}
        <DropdownMenu open={isDropdownOpen} onOpenChange={setIsDropdownOpen}>
          <DropdownMenuTrigger
            disabled={disabled || isLoading || !canAddMore}
            className={cn(
              'absolute left-3 top-1/2 -translate-y-1/2 p-0.5 rounded transition-colors',
              'text-muted-foreground hover:text-foreground focus:outline-none',
              attachments.length > 0 && 'text-primary',
              (disabled || isLoading || !canAddMore) && 'opacity-50 cursor-not-allowed'
            )}
            aria-label="Adjuntar archivos"
          >
            <IconPlus className="h-5 w-5" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" side="top" className="w-48">
            <DropdownMenuItem onClick={handleLocalUpload} className="gap-2 cursor-pointer">
              <IconUpload className="h-4 w-4" />
              <span>Subir archivo</span>
            </DropdownMenuItem>
            <DropdownMenuItem onClick={handleOpenIndexedPicker} className="gap-2 cursor-pointer">
              <IconFolder className="h-4 w-4" />
              <span>Mis documentos</span>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        {/* Verified generation button - shown when attachments present */}
        {attachments.length > 0 && onVerifiedGeneration && (
          <Button
            type="button"
            onClick={handleVerifiedClick}
            disabled={disabled || isLoading}
            size="icon"
            variant="outline"
            title="Generar documento verificado"
            className="absolute right-12 top-1/2 -translate-y-1/2 h-9 w-9 rounded-lg border-emerald-500/50 text-emerald-600 hover:bg-emerald-50 hover:text-emerald-700"
          >
            <IconFileCheck className="h-4 w-4" />
          </Button>
        )}

        {/* Send button - INSIDE INPUT RIGHT */}
        <Button
          type="button"
          onClick={handleSubmit}
          disabled={!hasContent || disabled || isLoading}
          size="icon"
          className="absolute right-2 top-1/2 -translate-y-1/2 h-9 w-9 rounded-lg"
        >
          {isLoading ? (
            <IconLoader2 className="h-4 w-4 animate-spin" />
          ) : (
            <IconSend className="h-4 w-4" />
          )}
        </Button>
      </div>

      <div className="flex justify-between text-xs text-muted-foreground px-1">
        <span>
          {query.length > 0 && `${query.length} caracteres`}
          {query.length > 0 && attachments.length > 0 && ' • '}
          {attachments.length > 0 && `${attachments.length} adjunto${attachments.length > 1 ? 's' : ''}`}
        </span>
        <span>
          {isVerificarCommand
            ? '/verificar activo — se generará documento verificado'
            : 'Enter para enviar • Shift+Enter para nueva línea'}
        </span>
      </div>

      {/* Indexed Documents Picker Dialog */}
      <IndexedDocsPicker
        open={isIndexedPickerOpen}
        onOpenChange={(open) => {
          setIsIndexedPickerOpen(open)
          // Restore focus when dialog closes
          if (!open) {
            setTimeout(() => {
              textareaRef.current?.focus()
            }, 100)
          }
        }}
        onSelect={handleIndexedDocsSelect}
        existingIds={existingAttachmentIds}
        maxSelectable={maxAttachments - attachments.length}
      />
    </div>
  )
}
