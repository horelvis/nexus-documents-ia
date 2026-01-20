"use client"

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

interface SearchResultsProps {
  results: any[]
  loading?: boolean
  onDocumentClick?: (document: any) => void
  onDownload?: (document: any) => void
  onDelete?: (document: any) => void
  onShare?: (document: any) => void
  onSignature?: (document: any) => void
  emptyMessage?: string
}

// Helper functions specific to search results
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

function SearchResultItem({ 
  result,
  onDocumentClick,
  onDownload,
  onDelete,
  onShare,
  onSignature
}: {
  result: any
  onDocumentClick?: (document: any) => void
  onDownload?: (document: any) => void
  onDelete?: (document: any) => void
  onShare?: (document: any) => void
  onSignature?: (document: any) => void
}) {
  const handleClick = () => {
    if (onDocumentClick) {
      onDocumentClick(result)
    }
  }

  const handleAction = (action: string, e: React.MouseEvent) => {
    e.stopPropagation()
    
    switch (action) {
      case 'download':
        onDownload?.(result)
        break
      case 'delete':
        onDelete?.(result)
        break
      case 'share':
        onShare?.(result)
        break
      case 'signature':
        onSignature?.(result)
        break
    }
  }

  return (
    <Card className="hover:shadow-lg transition-shadow cursor-pointer group">
      <CardContent className="p-4" onClick={handleClick}>
        <div className="flex items-start gap-3">
          {/* File Icon */}
          <div className="flex-shrink-0">
            {getFileIcon(result.file_type, result.mime_type, result.filename)}
          </div>
          
          {/* Document Info */}
          <div className="flex-grow min-w-0">
            <div className="flex items-start justify-between gap-2 mb-2">
              <div className="min-w-0 flex-1">
                <h3 className="text-base font-medium truncate" title={result.title || result.filename}>
                  {result.title || result.filename}
                </h3>
                {result.description && (
                  <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                    {result.description}
                  </p>
                )}
              </div>
              
              <div className="flex items-center gap-2">
                {/* Score */}
                {result.score && result.score > 0 && (
                  <div className="flex items-center gap-1 bg-blue-50 px-2 py-1 rounded-full">
                    <IconWeight className="h-3 w-3 text-blue-600" />
                    <span className="text-xs text-blue-600 font-medium">
                      {Math.round(result.score * 100)}%
                    </span>
                  </div>
                )}
                
                {/* Status Badge */}
                {result.indexed && (
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Badge 
                          className={getStatusColor(result.indexed)} 
                          variant="secondary" 
                          onClick={(e) => e.stopPropagation()}
                        >
                          {getStatusLabel(result.indexed)}
                        </Badge>
                      </TooltipTrigger>
                      <TooltipContent>
                        <p>Processing status: {getStatusLabel(result.indexed)}</p>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                )}
              </div>
            </div>

            {/* Highlights - More prominent for search */}
            {result.matches && Array.isArray(result.matches) && result.matches.length > 0 && (
              <div className="mb-3">
                <p className="text-xs text-muted-foreground mb-2 font-medium">Matches found:</p>
                <div className="space-y-1">
                  {result.matches.slice(0, 3).map((match: any, idx: number) => {
                    const textContent = typeof match === 'string' ? match : (match.text || match);
                    return (
                      <div key={idx} className="bg-yellow-50 border-l-4 border-yellow-300 p-2 rounded-r">
                        <p 
                          className="text-sm text-gray-700 line-clamp-2"
                          dangerouslySetInnerHTML={{ __html: textContent }}
                        />
                      </div>
                    );
                  })}
                  {result.matches.length > 3 && (
                    <p className="text-xs text-muted-foreground font-medium">
                      +{result.matches.length - 3} more matches
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
                  {result.created_at ? formatDistanceToNow(new Date(result.created_at), { addSuffix: true }) : 'Unknown date'}
                </span>
                {result.file_size && result.file_size > 0 && (
                  <span>{formatFileSize(result.file_size)}</span>
                )}
                {result.category && result.category !== 'Uncategorized' && (
                  <span>{result.category}</span>
                )}
              </div>
              
              {/* Actions */}
              <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7"
                  onClick={(e) => {
                    e.stopPropagation()
                    onDocumentClick?.(result)
                  }}
                  title="View"
                >
                  <IconEye className="h-3 w-3" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7"
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
                      className="h-7 w-7"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <IconDotsVertical className="h-3 w-3" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={(e) => { e.stopPropagation(); onDocumentClick?.(result) }}>
                      <IconEye className="h-4 w-4 mr-2" />
                      View Details
                    </DropdownMenuItem>
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
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            </div>
            
            {/* Tags */}
            {(result.tags || []).length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2">
                {(result.tags || []).map((tag: string) => (
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

export function SearchResults({
  results,
  loading,
  onDocumentClick,
  onDownload,
  onDelete,
  onShare,
  onSignature,
  emptyMessage = "No search results found"
}: SearchResultsProps) {
  if (loading) {
    return (
      <div className="flex justify-center items-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
        <span className="ml-2 text-muted-foreground">Searching documents...</span>
      </div>
    )
  }

  if (!results || results.length === 0) {
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
    <div className="space-y-4">
      {results.map((result, index) => (
        <SearchResultItem
          key={result.id || index}
          result={result}
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