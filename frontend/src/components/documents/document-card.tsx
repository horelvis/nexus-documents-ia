"use client"

import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { 
  IconFile, 
  IconDownload, 
  IconEye,
  IconTag,
  IconCalendar,
  IconFileTypePdf,
  IconFileTypeDocx,
  IconFileSpreadsheet,
  IconPhoto,
  IconFileText
} from "@tabler/icons-react"
import { formatDistanceToNow } from "date-fns"

interface DocumentCardProps {
  document: any
  score?: number
  highlights?: string[]
  onView?: () => void
  onDownload?: () => void
}

export function DocumentCard({ 
  document, 
  score, 
  highlights,
  onView,
  onDownload 
}: DocumentCardProps) {
  
  const getFileIcon = (fileType: string) => {
    const type = fileType?.toLowerCase()
    if (type === 'pdf') return <IconFileTypePdf className="h-5 w-5 text-red-500" />
    if (type === 'docx' || type === 'doc') return <IconFileTypeDocx className="h-5 w-5 text-blue-500" />
    if (type === 'xlsx' || type === 'xls' || type === 'csv') return <IconFileSpreadsheet className="h-5 w-5 text-green-500" />
    if (['jpg', 'jpeg', 'png', 'gif', 'bmp'].includes(type)) return <IconPhoto className="h-5 w-5 text-purple-500" />
    if (type === 'txt') return <IconFileText className="h-5 w-5 text-gray-500" />
    return <IconFile className="h-5 w-5 text-gray-500" />
  }

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 Bytes'
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  return (
    <Card className="hover:shadow-lg transition-shadow">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-start gap-3 flex-1 min-w-0">
            {getFileIcon(document.file_type)}
            <div className="flex-1 min-w-0">
              <h3 className="font-semibold text-base truncate" title={document.title}>
                {document.title}
              </h3>
              <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
                <span className="flex items-center gap-1">
                  <IconCalendar className="h-3 w-3" />
                  {formatDistanceToNow(new Date(document.created_at), { addSuffix: true })}
                </span>
                <span>{formatFileSize(document.file_size)}</span>
                {score && (
                  <Badge variant="secondary" className="text-xs">
                    {Math.round(score * 100)}% match
                  </Badge>
                )}
              </div>
            </div>
          </div>
          <div className="flex gap-1">
            <Button
              variant="ghost"
              size="icon"
              onClick={onView}
              className="h-8 w-8"
            >
              <IconEye className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={onDownload}
              className="h-8 w-8"
            >
              <IconDownload className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardHeader>
      
      <CardContent className="pt-0">
        {document.description && (
          <p className="text-sm text-muted-foreground line-clamp-2 mb-3">
            {document.description}
          </p>
        )}
        
        {highlights && highlights.length > 0 && (
          <div className="mb-3">
            <p className="text-xs font-medium mb-1">Relevant content:</p>
            <div className="space-y-1">
              {highlights.slice(0, 2).map((highlight, index) => (
                <p key={index} className="text-xs text-muted-foreground bg-yellow-50 dark:bg-yellow-900/20 p-2 rounded">
                  ...{highlight}...
                </p>
              ))}
            </div>
          </div>
        )}
        
        {document.tags && document.tags.length > 0 && (
          <div className="flex items-center gap-2 flex-wrap">
            <IconTag className="h-3 w-3 text-muted-foreground" />
            {document.tags.slice(0, 3).map((tag: any) => (
              <Badge key={tag.id} variant="outline" className="text-xs">
                {tag.name}
              </Badge>
            ))}
            {document.tags.length > 3 && (
              <span className="text-xs text-muted-foreground">
                +{document.tags.length - 3} more
              </span>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}