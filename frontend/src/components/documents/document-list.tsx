"use client"

import { useState } from "react"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import {
  IconFile,
  IconFileText,
  IconFileTypePdf,
  IconFileTypeDocx,
  IconFileSpreadsheet,
  IconPhoto,
  IconClock,
  IconEye,
  IconDownload,
  IconTrash,
  IconEdit,
  IconShare2,
  IconSignature,
  IconDotsVertical,
  IconAlertTriangle,
  IconWeight
} from "@tabler/icons-react"
import { formatDistanceToNow } from "date-fns"

interface DocumentListProps {
  documents: any[]
  loading?: boolean
  viewMode?: 'grid' | 'table'
  showScore?: boolean
  showHighlights?: boolean
  useDetailedView?: boolean
  onDocumentClick?: (document: any) => void
  onDownload?: (document: any) => void
  onDelete?: (document: any) => void
  onShare?: (document: any) => void
  onSignature?: (document: any) => void
  emptyMessage?: string
}

interface DocumentItemProps {
  document: any
  showScore?: boolean
  showHighlights?: boolean
  useDetailedView?: boolean
  onDocumentClick?: (document: any) => void
  onDownload?: (document: any) => void
  onDelete?: (document: any) => void
  onShare?: (document: any) => void
  onSignature?: (document: any) => void
}

// Helper functions
const getFileIcon = (fileType: string, mimeType?: string, filename?: string) => {
  let type = fileType?.toLowerCase()

  // Fallback: extract from mime_type or filename
  if (!type && mimeType) {
    if (mimeType.includes('pdf')) type = 'pdf'
    else if (mimeType.includes('word') || mimeType.includes('document')) type = 'docx'
    else if (mimeType.includes('sheet') || mimeType.includes('excel')) type = 'xlsx'
    else if (mimeType.includes('image')) type = 'image'
    else if (mimeType.includes('text')) type = 'txt'
  }

  if (!type && filename) {
    const ext = filename.split('.').pop()?.toLowerCase()
    type = ext || 'unknown'
  }

  switch (type) {
    case 'pdf':
      return <IconFileTypePdf className="h-6 w-6 text-red-500" />
    case 'docx':
    case 'doc':
    case 'document':
      return <IconFileTypeDocx className="h-6 w-6 text-blue-500" />
    case 'xlsx':
    case 'xls':
    case 'csv':
    case 'sheet':
      return <IconFileSpreadsheet className="h-6 w-6 text-green-500" />
    case 'jpg':
    case 'jpeg':
    case 'png':
    case 'gif':
    case 'bmp':
    case 'image':
      return <IconPhoto className="h-6 w-6 text-purple-500" />
    case 'txt':
    case 'text':
      return <IconFileText className="h-6 w-6 text-gray-500" />
    default:
      return <IconFile className="h-6 w-6 text-gray-500" />
  }
}

const getStatusColor = (status: string) => {
  switch (status?.toLowerCase()) {
    case 'indexed':
      return 'bg-green-100 text-green-800 border-green-200'
    case 'processing':
    case 'indexing':
      return 'bg-yellow-100 text-yellow-800 border-yellow-200'
    case 'pending':
      return 'bg-blue-100 text-blue-800 border-blue-200'
    case 'error':
    case 'indexing_error':
      return 'bg-red-100 text-red-800 border-red-200'
    default:
      return 'bg-gray-100 text-gray-800 border-gray-200'
  }
}

const getStatusLabel = (status: string) => {
  switch (status?.toLowerCase()) {
    case 'indexed': return 'Indexed'
    case 'processing': return 'Processing'
    case 'indexing': return 'Indexing'
    case 'pending': return 'Pending'
    case 'error': return 'Error'
    case 'indexing_error': return 'Index Error'
    default: return status || 'Unknown'
  }
}

const formatFileSize = (bytes: number) => {
  if (!bytes || bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

function DocumentItem({
  document,
  showScore,
  showHighlights,
  useDetailedView = false,
  onDocumentClick,
  onDownload,
  onDelete,
  onShare,
  onSignature
}: DocumentItemProps) {
  const handleClick = () => {
    if (onDocumentClick) {
      onDocumentClick(document)
    }
  }

  const handleAction = (action: string, e: React.MouseEvent) => {
    e.stopPropagation()

    switch (action) {
      case 'download':
        onDownload?.(document)
        break
      case 'delete':
        onDelete?.(document)
        break
      case 'share':
        onShare?.(document)
        break
      case 'signature':
        onSignature?.(document)
        break
    }
  }

  if (useDetailedView) {
    // Detailed view matching Document Library design
    return (
      <Card className="hover:shadow-lg transition-shadow cursor-pointer group">
        <CardContent className="p-4" onClick={handleClick}>
          <div className="flex items-start gap-3">
            {/* File Icon */}
            <div className="flex-shrink-0">
              {getFileIcon(document.file_type, document.mime_type, document.filename)}
            </div>

            {/* Document Info */}
            <div className="flex-grow min-w-0">
              <div className="flex items-start justify-between gap-2 mb-1">
                <div className="min-w-0 flex-1">
                  <h3 className="text-base font-medium truncate" title={document.title || document.filename}>
                    {document.title || document.filename}
                  </h3>
                  {document.description && (
                    <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">
                      {document.description}
                    </p>
                  )}
                </div>

                {/* Status Badge */}
                {document.indexed && (
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Badge
                          className={getStatusColor(document.indexed)}
                          variant="secondary"
                          onClick={(e) => e.stopPropagation()}
                        >
                          {getStatusLabel(document.indexed)}
                        </Badge>
                      </TooltipTrigger>
                      <TooltipContent>
                        <p>Processing status: {getStatusLabel(document.indexed)}</p>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                )}
              </div>

              {/* Score */}
              {showScore && document.score && (
                <div className="flex items-center gap-2 mb-2">
                  <IconWeight className="h-3 w-3 text-muted-foreground" />
                  <span className="text-xs text-muted-foreground">
                    Match: {Math.round(document.score * 100)}%
                  </span>
                </div>
              )}

              {/* Highlights */}
              {showHighlights && (document.search_matches || document.matches) && (document.search_matches || document.matches).length > 0 && (
                <div className="mb-2">
                  <p className="text-xs text-muted-foreground mb-1">Relevant content:</p>
                  <div className="space-y-1">
                    {(document.search_matches || document.matches).slice(0, 2).map((match: any, idx: number) => (
                      <div
                        key={idx}
                        className="text-xs bg-yellow-50 dark:bg-yellow-900/20 p-1 rounded border-l-2 border-yellow-200 dark:border-yellow-700 line-clamp-2 [&>mark]:bg-yellow-200 [&>mark]:text-yellow-900 [&>mark]:px-0.5 [&>mark]:rounded-sm dark:[&>mark]:bg-yellow-900/40 dark:[&>mark]:text-yellow-100"
                        dangerouslySetInnerHTML={{ __html: match.text || match }}
                      />
                    ))}
                    {(document.search_matches || document.matches).length > 2 && (
                      <p className="text-xs text-muted-foreground">
                        +{(document.search_matches || document.matches).length - 2} more matches
                      </p>
                    )}
                  </div>
                </div>
              )}

              {/* Metadata and Actions */}
              <div className="flex items-center justify-between gap-2 mb-1">
                <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <span>Size: {formatFileSize(document.file_size)}</span>
                  <span>•</span>
                  <span>Uploaded: {new Date(document.created_at).toLocaleDateString()}</span>
                  <span>•</span>
                  <span>{document.category || 'Sin Categoría'}</span>
                </div>

                {/* Actions */}
                <div className="flex gap-0.5 flex-shrink-0" onClick={(e) => e.stopPropagation()}>
                  {/* 3 Main Actions */}
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={(e) => {
                      e.stopPropagation()
                      onDocumentClick?.(document)
                    }}
                    title="Full Preview"
                    className="h-7 w-7 p-0 opacity-80 group-hover:opacity-100"
                  >
                    <IconEye className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={(e) => handleAction('download', e)}
                    title="Download"
                    className="h-7 w-7 p-0 opacity-80 group-hover:opacity-100"
                  >
                    <IconDownload className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={(e) => handleAction('share', e)}
                    title="Share"
                    className="h-7 w-7 p-0 opacity-80 group-hover:opacity-100"
                  >
                    <IconShare2 className="h-3.5 w-3.5" />
                  </Button>

                  {/* More Actions Dropdown */}
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={(e) => e.stopPropagation()}
                        title="More actions"
                        className="h-7 w-7 p-0 opacity-80 group-hover:opacity-100"
                      >
                        <IconDotsVertical className="h-3.5 w-3.5" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem onClick={(e) => { e.stopPropagation(); onDocumentClick?.(document) }}>
                        <IconEye className="mr-2 h-4 w-4" />
                        View Details
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={(e) => handleAction('download', e)}>
                        <IconDownload className="mr-2 h-4 w-4" />
                        Download
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={(e) => handleAction('signature', e)}>
                        <IconSignature className="mr-2 h-4 w-4" />
                        Request Signature
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={(e) => handleAction('share', e)}>
                        <IconShare2 className="mr-2 h-4 w-4" />
                        Share
                      </DropdownMenuItem>
                      {onDelete && (
                        <>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            onClick={(e) => handleAction('delete', e)}
                            className="text-red-600 focus:text-red-600"
                          >
                            <IconTrash className="mr-2 h-4 w-4" />
                            Delete
                          </DropdownMenuItem>
                        </>
                      )}
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              </div>

              {/* Tags */}
              {(document.tags || []).length > 0 && (
                <div className="flex flex-wrap gap-0.5">
                  {(document.tags || []).map((tag: string) => (
                    <Badge key={tag} variant="outline" className="text-xs px-1.5 py-0 h-5">
                      {tag}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          </div>
        </CardContent>
      </Card>
    )
  }

  // Simple view (original design)
  return (
    <Card className="hover:shadow-lg transition-shadow cursor-pointer group">
      <CardContent className="p-4" onClick={handleClick}>
        <div className="flex items-start gap-3">
          {/* File Icon */}
          <div className="flex-shrink-0">
            {getFileIcon(document.file_type, document.mime_type, document.filename)}
          </div>

          {/* Document Info */}
          <div className="flex-grow min-w-0">
            <div className="flex items-start justify-between gap-2 mb-1">
              <div className="min-w-0 flex-1">
                <h3 className="text-base font-medium truncate" title={document.title || document.filename}>
                  {document.title || document.filename}
                </h3>
                {document.description && (
                  <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                    {document.description}
                  </p>
                )}
              </div>

              {/* Status Badge */}
              {document.indexed && (
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Badge
                        className={getStatusColor(document.indexed)}
                        variant="secondary"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {getStatusLabel(document.indexed)}
                      </Badge>
                    </TooltipTrigger>
                    <TooltipContent>
                      <p>Processing status: {getStatusLabel(document.indexed)}</p>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              )}
            </div>

            {/* Score */}
            {showScore && document.score && (
              <div className="flex items-center gap-2 mb-2">
                <IconWeight className="h-3 w-3 text-muted-foreground" />
                <span className="text-xs text-muted-foreground">
                  Match: {Math.round(document.score * 100)}%
                </span>
              </div>
            )}

            {/* Highlights */}
            {showHighlights && (document.search_matches || document.matches) && (document.search_matches || document.matches).length > 0 && (
              <div className="mb-2">
                <p className="text-xs text-muted-foreground mb-1">Relevant content:</p>
                <div className="space-y-1">
                  {(document.search_matches || document.matches).slice(0, 2).map((match: any, idx: number) => (
                    <div
                      key={idx}
                      className="text-xs bg-yellow-50 dark:bg-yellow-900/20 p-1 rounded border-l-2 border-yellow-200 dark:border-yellow-700 line-clamp-2 [&>mark]:bg-yellow-200 [&>mark]:text-yellow-900 [&>mark]:px-0.5 [&>mark]:rounded-sm dark:[&>mark]:bg-yellow-900/40 dark:[&>mark]:text-yellow-100"
                      dangerouslySetInnerHTML={{ __html: match.text || match }}
                    />
                  ))}
                  {(document.search_matches || document.matches).length > 2 && (
                    <p className="text-xs text-muted-foreground">
                      +{(document.search_matches || document.matches).length - 2} more matches
                    </p>
                  )}
                </div>
              </div>
            )}

            {/* Metadata */}
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <div className="flex items-center gap-3">
                <span className="flex items-center gap-1">
                  <IconClock className="h-3 w-3" />
                  {document.created_at ? formatDistanceToNow(new Date(document.created_at), { addSuffix: true }) : 'Unknown'}
                </span>
                {document.file_size && (
                  <span>{formatFileSize(document.file_size)}</span>
                )}
                {document.tags && document.tags.length > 0 && (
                  <div className="flex gap-1">
                    {document.tags.slice(0, 2).map((tag: string, idx: number) => (
                      <Badge key={idx} variant="outline" className="text-xs h-4 px-1">
                        {tag}
                      </Badge>
                    ))}
                  </div>
                )}
              </div>

              {/* Actions */}
              <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6"
                  onClick={(e) => handleAction('download', e)}
                  title="Download"
                >
                  <IconDownload className="h-3 w-3" />
                </Button>

                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <IconDotsVertical className="h-3 w-3" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={(e) => handleAction('download', e)}>
                      <IconDownload className="h-4 w-4 mr-2" />
                      Download
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={(e) => handleAction('share', e)}>
                      <IconShare2 className="h-4 w-4 mr-2" />
                      Share
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={(e) => handleAction('signature', e)}>
                      <IconSignature className="h-4 w-4 mr-2" />
                      Request Signature
                    </DropdownMenuItem>
                    {onDelete && (
                      <>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem
                          onClick={(e) => handleAction('delete', e)}
                          className="text-red-600 focus:text-red-600"
                        >
                          <IconTrash className="h-4 w-4 mr-2" />
                          Delete
                        </DropdownMenuItem>
                      </>
                    )}
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export function DocumentList({
  documents,
  loading,
  viewMode = 'grid',
  showScore = false,
  showHighlights = false,
  useDetailedView = false,
  onDocumentClick,
  onDownload,
  onDelete,
  onShare,
  onSignature,
  emptyMessage = "No documents found"
}: DocumentListProps) {
  if (loading) {
    return (
      <div className="flex justify-center items-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
        <span className="ml-2 text-muted-foreground">Loading documents...</span>
      </div>
    )
  }

  if (!documents || documents.length === 0) {
    return (
      <Card className="text-center py-12">
        <CardContent>
          <IconAlertTriangle className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
          <p className="text-muted-foreground">{emptyMessage}</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-3">
      {documents.map((document, index) => (
        <DocumentItem
          key={document.id || index}
          document={document}
          showScore={showScore}
          showHighlights={showHighlights}
          useDetailedView={useDetailedView}
          onDocumentClick={onDocumentClick}
          onDownload={onDownload}
          onDelete={onDelete}
          onShare={onShare}
          onSignature={onSignature}
        />
      ))}
    </div>
  )
}