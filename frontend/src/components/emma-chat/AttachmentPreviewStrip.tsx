'use client'

import { cn } from '@/lib/utils'
import { Attachment } from '@/lib/types/emma'
import { AttachmentChip } from './AttachmentChip'
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area'
import { Badge } from '@/components/ui/badge'
import { IconPaperclip } from '@tabler/icons-react'

interface AttachmentPreviewStripProps {
  attachments: Attachment[]
  onRemove: (id: string) => void
  maxVisible?: number  // Default: 5, then shows "+N more"
  className?: string
}

export function AttachmentPreviewStrip({
  attachments,
  onRemove,
  maxVisible = 5,
  className,
}: AttachmentPreviewStripProps) {
  if (attachments.length === 0) return null

  const visibleAttachments = attachments.slice(0, maxVisible)
  const hiddenCount = attachments.length - maxVisible

  return (
    <div className={cn('space-y-2', className)}>
      {/* Header */}
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <IconPaperclip className="h-3.5 w-3.5" />
        <span>Adjuntos: ({attachments.length})</span>
      </div>

      {/* Chips strip */}
      <ScrollArea className="w-full">
        <div className="flex items-center gap-2 pb-2">
          {visibleAttachments.map((attachment) => (
            <AttachmentChip
              key={attachment.id}
              attachment={attachment}
              onRemove={() => onRemove(attachment.id)}
              showProgress={attachment.type === 'upload' && attachment.uploadStatus === 'uploading'}
            />
          ))}

          {/* Hidden count badge */}
          {hiddenCount > 0 && (
            <Badge variant="secondary" className="text-xs shrink-0">
              +{hiddenCount} más
            </Badge>
          )}
        </div>
        <ScrollBar orientation="horizontal" />
      </ScrollArea>
    </div>
  )
}
