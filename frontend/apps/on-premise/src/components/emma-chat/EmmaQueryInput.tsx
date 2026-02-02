'use client'

import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { IconSend, IconLoader2, IconPlus, IconUpload, IconFolder, IconFileCheck, IconChartBar } from '@tabler/icons-react'
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

const SLASH_COMMANDS = [
  { command: '/verificar ', label: 'Verificar documento', description: 'Verifica cada afirmación contra tus documentos', icon: IconFileCheck, color: 'emerald' as const },
  { command: '/predecir ', label: 'Análisis predictivo', description: 'Analiza un documento y predice posibles resultados', icon: IconChartBar, color: 'blue' as const },
]

interface EmmaQueryInputProps {
  onSendQuery: (query: string, attachments?: Attachment[]) => Promise<void>
  onVerifiedGeneration?: (topic: string, attachments?: Attachment[]) => void
  onPredictiveAnalysis?: (caseDescription: string, attachments?: Attachment[]) => void
  isLoading?: boolean
  disabled?: boolean
  placeholder?: string
  className?: string
  maxAttachments?: number
}

export function EmmaQueryInput({
  onSendQuery,
  onVerifiedGeneration,
  onPredictiveAnalysis,
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
  const [slashMenuOpen, setSlashMenuOpen] = useState(false)
  const [slashMenuIndex, setSlashMenuIndex] = useState(0)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Filtered slash commands based on current input
  const filteredCommands = useMemo(() => {
    if (!query.startsWith('/')) return []
    return SLASH_COMMANDS.filter(c => c.command.startsWith(query))
  }, [query])

  // Focus textarea when loading completes
  useEffect(() => {
    if (textareaRef.current && !disabled && !isLoading) {
      const timer = setTimeout(() => {
        textareaRef.current?.focus()
      }, 50)
      return () => clearTimeout(timer)
    }
  }, [disabled, isLoading])

  const handleSubmit = async () => {
    if ((!query.trim() && attachments.length === 0) || isLoading || disabled) return

    const queryToSend = query.trim()
    const attachmentsToSend = [...attachments]

    setQuery('')
    setAttachments([])
    setSlashMenuOpen(false)

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

    // Detect /predecir command
    if (queryToSend.startsWith('/predecir ') && onPredictiveAnalysis) {
      const caseDesc = queryToSend.slice('/predecir '.length).trim()
      if (caseDesc) {
        Promise.resolve(onPredictiveAnalysis(caseDesc, attachmentsToSend.length > 0 ? attachmentsToSend : undefined)).catch((err) => {
          console.error('[EmmaQueryInput] Predictive analysis error:', err)
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
    Promise.resolve(onVerifiedGeneration(topic, attachmentsToSend.length > 0 ? attachmentsToSend : undefined)).catch((err) => {
      console.error('[EmmaQueryInput] Verified generation error:', err)
    })
  }

  const handlePredictiveClick = () => {
    if (isLoading || disabled || !onPredictiveAnalysis) return
    const caseDesc = query.trim() || 'Analiza los documentos adjuntos y genera una predicción'
    const attachmentsToSend = [...attachments]
    setQuery('')
    setAttachments([])
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
    Promise.resolve(onPredictiveAnalysis(caseDesc, attachmentsToSend.length > 0 ? attachmentsToSend : undefined)).catch((err) => {
      console.error('[EmmaQueryInput] Predictive analysis error:', err)
    })
  }

  const selectSlashCommand = (cmd: typeof SLASH_COMMANDS[0]) => {
    setQuery(cmd.command)
    setSlashMenuOpen(false)
    textareaRef.current?.focus()
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    // Slash menu navigation
    if (slashMenuOpen && filteredCommands.length > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setSlashMenuIndex(i => Math.min(i + 1, filteredCommands.length - 1))
        return
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setSlashMenuIndex(i => Math.max(i - 1, 0))
        return
      }
      if (e.key === 'Enter') {
        e.preventDefault()
        selectSlashCommand(filteredCommands[slashMenuIndex])
        return
      }
      if (e.key === 'Escape') {
        e.preventDefault()
        setSlashMenuOpen(false)
        return
      }
    }

    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const text = e.target.value
    setQuery(text)

    // Slash menu logic
    if (text.startsWith('/') && text.length <= 12) {
      const filtered = SLASH_COMMANDS.filter(c => c.command.startsWith(text))
      setSlashMenuOpen(filtered.length > 0)
      setSlashMenuIndex(0)
    } else {
      setSlashMenuOpen(false)
    }

    const textarea = e.target
    textarea.style.height = 'auto'
    const newHeight = Math.min(Math.max(textarea.scrollHeight, 52), 200)
    textarea.style.height = `${newHeight}px`
  }

  const handleLocalUpload = () => {
    setIsDropdownOpen(false)
    setTimeout(() => {
      fileInputRef.current?.click()
    }, 50)
  }

  const handleOpenIndexedPicker = () => {
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
  const actionsDisabled = isLoading || disabled

  return (
    <div className={cn('space-y-2', className)}>
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
        {/* Slash command menu */}
        {slashMenuOpen && filteredCommands.length > 0 && (
          <div className="absolute bottom-full left-0 right-0 mb-1 z-50 rounded-lg border border-border bg-popover shadow-md overflow-hidden">
            {filteredCommands.map((cmd, idx) => {
              const Icon = cmd.icon
              return (
                <button
                  key={cmd.command}
                  type="button"
                  className={cn(
                    'flex items-center gap-3 w-full px-3 py-2 text-sm text-left transition-colors',
                    idx === slashMenuIndex ? 'bg-accent text-accent-foreground' : 'hover:bg-accent/50'
                  )}
                  onMouseDown={(e) => {
                    e.preventDefault()
                    selectSlashCommand(cmd)
                  }}
                  onMouseEnter={() => setSlashMenuIndex(idx)}
                >
                  <Icon className={cn(
                    'h-4 w-4 shrink-0',
                    cmd.color === 'emerald' ? 'text-emerald-500' : 'text-blue-500'
                  )} />
                  <span className="font-mono font-medium">{cmd.command.trim()}</span>
                  <span className="text-muted-foreground">{cmd.description}</span>
                </button>
              )
            })}
          </div>
        )}

        <Textarea
          ref={textareaRef}
          value={query}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled || isLoading}
          className="pl-10 pr-12 py-3.5 min-h-[52px] max-h-[200px] resize-none rounded-xl border border-border/50 bg-background focus-visible:ring-1 focus-visible:ring-primary/30 focus-visible:border-primary/50"
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

      {/* Action toolbar */}
      <div className="flex items-center justify-between px-1">
        <div className="flex items-center gap-1.5">
          {onPredictiveAnalysis && (
            <button
              type="button"
              onClick={handlePredictiveClick}
              disabled={actionsDisabled}
              className={cn(
                'inline-flex items-center gap-1.5 h-7 px-2.5 text-xs font-medium rounded-full border transition-colors',
                'border-blue-300 text-blue-600 hover:bg-blue-50 hover:border-blue-400',
                'dark:border-blue-500/40 dark:text-blue-400 dark:hover:bg-blue-950/30',
                actionsDisabled && 'opacity-50 cursor-not-allowed'
              )}
            >
              <IconChartBar className="h-3.5 w-3.5" />
              Predecir
            </button>
          )}
          {onVerifiedGeneration && (
            <button
              type="button"
              onClick={handleVerifiedClick}
              disabled={actionsDisabled}
              className={cn(
                'inline-flex items-center gap-1.5 h-7 px-2.5 text-xs font-medium rounded-full border transition-colors',
                'border-emerald-300 text-emerald-600 hover:bg-emerald-50 hover:border-emerald-400',
                'dark:border-emerald-500/40 dark:text-emerald-400 dark:hover:bg-emerald-950/30',
                actionsDisabled && 'opacity-50 cursor-not-allowed'
              )}
            >
              <IconFileCheck className="h-3.5 w-3.5" />
              Verificar
            </button>
          )}
        </div>
        <span className="text-xs text-muted-foreground">
          Enter · Shift+Enter
        </span>
      </div>

      {/* Indexed Documents Picker Dialog */}
      <IndexedDocsPicker
        open={isIndexedPickerOpen}
        onOpenChange={(open) => {
          setIsIndexedPickerOpen(open)
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
