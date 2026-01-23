'use client'

import { IconX, IconFile, IconFileTypePdf, IconFileTypeDoc, IconFileTypeTxt, IconPhoto, IconFileSpreadsheet, IconLoader2 } from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import { Attachment, getFileTypeConfig } from '@/lib/types/emma'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

interface AttachmentChipProps {
  attachment: Attachment
  onRemove: () => void
  showProgress?: boolean
}

function getFileIcon(fileType?: string | null, extension?: string | null) {
  const config = getFileTypeConfig(fileType, extension)

  switch (config.icon) {
    case 'pdf':
      return IconFileTypePdf
    case 'doc':
    case 'docx':
      return IconFileTypeDoc
    case 'txt':
      return IconFileTypeTxt
    case 'image':
      return IconPhoto
    case 'xls':
    case 'xlsx':
      return IconFileSpreadsheet
    default:
      return IconFile
  }
}

function formatFileSize(bytes?: number): string {
  if (!bytes) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function truncateName(name: string, maxLength = 20): string {
  if (name.length <= maxLength) return name
  const ext = name.split('.').pop() || ''
  const baseName = name.slice(0, name.length - ext.length - 1)
  const truncatedBase = baseName.slice(0, maxLength - ext.length - 4)
  return `${truncatedBase}...${ext}`
}

export function AttachmentChip({ attachment, onRemove, showProgress = false }: AttachmentChipProps) {
  const fileType = attachment.fileType || (attachment.type === 'upload' ? attachment.file.type : null)
  const extension = attachment.name.split('.').pop()
  const config = getFileTypeConfig(fileType, extension)
  const Icon = getFileIcon(fileType, extension)

  const isUploading = attachment.type === 'upload' && attachment.uploadStatus === 'uploading'
  const hasError = attachment.type === 'upload' && attachment.uploadStatus === 'error'

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <div
            className={cn(
              'group relative inline-flex items-center gap-1.5 pl-2 pr-1 py-1 rounded-md border text-sm transition-colors',
              'bg-muted/50 border-border hover:bg-muted',
              hasError && 'border-destructive/50 bg-destructive/10',
              isUploading && 'opacity-70'
            )}
          >
            {/* File type badge */}
            <span className={cn('flex items-center gap-1', config.color)}>
              {isUploading ? (
                <IconLoader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Icon className="h-3.5 w-3.5" />
              )}
              <span className="text-[10px] font-semibold uppercase">{config.label}</span>
            </span>

            {/* File name */}
            <span className="text-xs text-foreground max-w-[120px] truncate">
              {truncateName(attachment.name)}
            </span>

            {/* Remove button */}
            <button
              onClick={(e) => {
                e.preventDefault()
                e.stopPropagation()
                onRemove()
              }}
              className={cn(
                'ml-0.5 p-0.5 rounded hover:bg-destructive/20 transition-colors',
                'text-muted-foreground hover:text-destructive'
              )}
              aria-label={`Eliminar ${attachment.name}`}
            >
              <IconX className="h-3 w-3" />
            </button>

            {/* Upload progress bar */}
            {showProgress && isUploading && (
              <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-muted overflow-hidden rounded-b">
                <div className="h-full bg-primary animate-pulse w-1/2" />
              </div>
            )}
          </div>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-xs">
          <div className="space-y-1">
            <p className="font-medium">{attachment.name}</p>
            {attachment.size && (
              <p className="text-xs text-muted-foreground">{formatFileSize(attachment.size)}</p>
            )}
            {attachment.type === 'indexed' && attachment.connectorType && (
              <p className="text-xs text-muted-foreground">Fuente: {attachment.connectorType}</p>
            )}
            {hasError && (
              <p className="text-xs text-destructive">Error al subir el archivo</p>
            )}
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}
