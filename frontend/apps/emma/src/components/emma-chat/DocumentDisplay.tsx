'use client'

import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { File, ExternalLink, Calendar, User, Eye } from 'lucide-react'
import { cn } from '@/lib/utils'
import { DocumentInfo } from '@/lib/types/emma'

interface DocumentDisplayProps {
  documents: DocumentInfo[]
  onDocumentClick?: (doc: DocumentInfo) => void
  onPreviewClick?: (doc: DocumentInfo) => void
  className?: string
}

export function DocumentDisplay({
  documents,
  onDocumentClick,
  onPreviewClick,
  className,
}: DocumentDisplayProps) {
  if (!documents || documents.length === 0) return null

  return (
    <div className={cn('w-full space-y-2', className)}>
      <div className="flex items-center gap-2 text-xs text-muted-foreground mb-2">
        <File className="h-3 w-3" />
        <span>Documentos relacionados ({documents.length})</span>
      </div>

      <div className="space-y-2">
        {documents.map((doc, index) => (
          <Card
            key={doc.id || doc.name || index}
            className={cn(
              'p-3 hover:shadow-md transition-all duration-200 cursor-pointer',
              'border-l-4 border-l-blue-500'
            )}
            onClick={() => onDocumentClick?.(doc)}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <File className="h-4 w-4 text-blue-500 shrink-0" />
                  <span className="text-sm font-medium truncate">{doc.name}</span>
                  {doc.relevanceScore && (
                    <Badge variant="secondary" className="text-[10px] shrink-0">
                      {Math.round(doc.relevanceScore * 100)}%
                    </Badge>
                  )}
                </div>

                {(doc.collection || doc.fileType) && (
                  <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
                    {doc.collection && <span>{doc.collection}</span>}
                    {doc.fileType && (
                      <Badge variant="outline" className="text-[10px] px-1 py-0">
                        {doc.fileType.toUpperCase()}
                      </Badge>
                    )}
                  </div>
                )}

                <div className="flex items-center gap-3 mt-1.5 text-[10px] text-muted-foreground">
                  {doc.createdAt && (
                    <div className="flex items-center gap-1">
                      <Calendar className="h-2.5 w-2.5" />
                      <span>{doc.createdAt}</span>
                    </div>
                  )}
                  {doc.author && (
                    <div className="flex items-center gap-1">
                      <User className="h-2.5 w-2.5" />
                      <span>{doc.author}</span>
                    </div>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-1 shrink-0">
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 px-2"
                  onClick={(e) => {
                    e.stopPropagation()
                    onPreviewClick?.(doc)
                  }}
                  title="Vista previa"
                >
                  <Eye className="h-3.5 w-3.5" />
                </Button>
                {doc.url && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 px-2"
                    onClick={(e) => {
                      e.stopPropagation()
                      window.open(doc.url, '_blank')
                    }}
                    title="Abrir en nueva pestaña"
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                  </Button>
                )}
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}
