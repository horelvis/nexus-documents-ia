'use client'

import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  IconFile,
  IconExternalLink,
  IconCalendar,
  IconUser,
  IconEye,
  IconFileTypePdf,
  IconFileTypeDoc,
  IconFileTypeDocx,
  IconFileTypeTxt,
  IconFileTypeXls,
  IconPhoto,
  IconScale,
  IconTopologyRing,
} from '@tabler/icons-react'
import Link from 'next/link'
import { cn } from '@/lib/utils'
import { DocumentInfo, getFileTypeConfig } from '@/lib/types/emma'

// Get icon component based on file type
function getFileTypeIcon(fileType?: string, className?: string) {
  const config = getFileTypeConfig(fileType, fileType)
  const iconClass = cn('h-4 w-4 shrink-0', config.color, className)

  switch (config.icon) {
    case 'pdf':
      return <IconFileTypePdf className={iconClass} />
    case 'doc':
    case 'docx':
      return <IconFileTypeDocx className={iconClass} />
    case 'txt':
      return <IconFileTypeTxt className={iconClass} />
    case 'xls':
    case 'xlsx':
      return <IconFileTypeXls className={iconClass} />
    case 'image':
      return <IconPhoto className={iconClass} />
    default:
      return <IconFile className={iconClass} />
  }
}

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
  // Helper to determine if a string looks like a UUID
  const isUUID = (str: string) => /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(str)

  // Filter out documents that only have UUID names (no real document name)
  const validDocuments = documents?.filter(doc => doc.name && !isUUID(doc.name)) || []

  if (validDocuments.length === 0) return null

  // Get display name for document
  const getDisplayName = (doc: DocumentInfo) => {
    // If name is a UUID, try to show a friendlier name
    if (doc.name && !isUUID(doc.name)) {
      return doc.name
    }
    // If we have a file type, show "Documento.ext"
    if (doc.fileType) {
      const config = getFileTypeConfig(doc.fileType, doc.fileType)
      return `Documento.${config.label.toLowerCase()}`
    }
    // Fallback: shorten the UUID
    if (doc.name && isUUID(doc.name)) {
      return `Documento ${doc.name.slice(0, 8)}...`
    }
    return doc.name || 'Documento'
  }

  // Get border color based on file type or source type
  const getBorderColor = (doc: DocumentInfo) => {
    // Legal/public knowledge sources get a special purple/gold border
    if (doc.source_type === 'public_knowledge' || doc.boe_id || doc.graph_link) {
      return 'border-l-amber-500'
    }
    const config = getFileTypeConfig(doc.fileType, doc.fileType)
    if (config.icon === 'pdf') return 'border-l-red-500'
    if (config.icon === 'doc' || config.icon === 'docx') return 'border-l-blue-500'
    if (config.icon === 'xls' || config.icon === 'xlsx') return 'border-l-emerald-500'
    if (config.icon === 'image') return 'border-l-green-500'
    if (config.icon === 'txt') return 'border-l-gray-500'
    return 'border-l-blue-500'
  }

  // Check if document is a legal/legislation source
  const isLegalSource = (doc: DocumentInfo) => {
    return doc.source_type === 'public_knowledge' || doc.boe_id || doc.graph_link
  }

  return (
    <div className={cn('w-full space-y-2', className)}>
      <div className="flex items-center gap-2 text-xs text-muted-foreground mb-2">
        <IconFile className="h-3 w-3" />
        <span>Fuentes ({validDocuments.length})</span>
      </div>

      <div className="space-y-2">
        {validDocuments.map((doc, index) => {
          const displayName = getDisplayName(doc)
          const config = getFileTypeConfig(doc.fileType, doc.fileType)

          const isLegal = isLegalSource(doc)

          return (
            <Card
              key={doc.id || doc.name || index}
              className={cn(
                'p-3 hover:shadow-md transition-all duration-200 cursor-pointer',
                'border-l-4',
                getBorderColor(doc)
              )}
              onClick={() => onDocumentClick?.(doc)}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    {isLegal ? (
                      <IconScale className="h-4 w-4 shrink-0 text-amber-500" />
                    ) : (
                      getFileTypeIcon(doc.fileType)
                    )}
                    <span className="text-sm font-medium truncate">{displayName}</span>
                    {isLegal && (
                      <Badge variant="outline" className="text-[10px] px-1.5 py-0 text-amber-600 border-amber-300">
                        BOE
                      </Badge>
                    )}
                    {!isLegal && doc.fileType && (
                      <Badge variant="outline" className={cn('text-[10px] px-1.5 py-0', config.color)}>
                        {config.label}
                      </Badge>
                    )}
                    {doc.relevanceScore && (
                      <Badge variant="secondary" className="text-[10px] shrink-0">
                        {Math.round(doc.relevanceScore * 100)}%
                      </Badge>
                    )}
                  </div>

                  {/* Show BOE ID for legal sources */}
                  {doc.boe_id && (
                    <div className="flex items-center gap-2 mt-1 text-xs text-amber-600">
                      <span>{doc.boe_id}</span>
                    </div>
                  )}

                  {doc.collection && !isLegal && (
                    <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
                      <span>{doc.collection}</span>
                    </div>
                  )}

                  <div className="flex items-center gap-3 mt-1.5 text-[10px] text-muted-foreground">
                    {doc.createdAt && (
                      <div className="flex items-center gap-1">
                        <IconCalendar className="h-2.5 w-2.5" />
                        <span>{doc.createdAt}</span>
                      </div>
                    )}
                    {doc.author && (
                      <div className="flex items-center gap-1">
                        <IconUser className="h-2.5 w-2.5" />
                        <span>{doc.author}</span>
                      </div>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-1 shrink-0">
                  {/* Legal Graph Link Button */}
                  {doc.graph_link && (
                    <Link href={doc.graph_link} onClick={(e) => e.stopPropagation()}>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 px-2 text-amber-600 hover:text-amber-700 hover:bg-amber-50"
                        title="Ver en Grafo Legal"
                      >
                        <IconTopologyRing className="h-3.5 w-3.5" />
                      </Button>
                    </Link>
                  )}
                  {!isLegal && (
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
                      <IconEye className="h-3.5 w-3.5" />
                    </Button>
                  )}
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
                      <IconExternalLink className="h-3.5 w-3.5" />
                    </Button>
                  )}
                </div>
              </div>
            </Card>
          )
        })}
      </div>
    </div>
  )
}
