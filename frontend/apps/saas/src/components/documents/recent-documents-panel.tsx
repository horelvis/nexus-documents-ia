"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { 
  IconEye, 
  IconClock, 
  IconFile,
  IconExternalLink,
  IconRefresh
} from "@tabler/icons-react"
import { useDocumentInsightsService, type RecentDocument } from "@/lib/services/document-insights.service"
import { getRelativeTime, formatFileSize } from "@/lib/document-utils"

interface RecentDocumentsPanelProps {
  tenantId: string
  limit?: number
  showHeader?: boolean
  className?: string
}

export function RecentDocumentsPanel({ 
  tenantId, 
  limit = 5, 
  showHeader = true,
  className = ""
}: RecentDocumentsPanelProps) {
  const router = useRouter()
  const insightsService = useDocumentInsightsService()
  
  const [recentDocuments, setRecentDocuments] = useState<RecentDocument[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadRecentDocuments = async () => {
    setIsLoading(true)
    setError(null)
    
    try {
      const response = await insightsService.getRecentlyViewedDocuments(limit, true)
      
      if (response.error) {
        setError(response.error)
      } else {
        setRecentDocuments(response.data || [])
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load recent documents')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadRecentDocuments()
  }, [limit])

  const handleDocumentClick = (document: RecentDocument) => {
    router.push(`/${tenantId}/documents/${document.id}/preview`)
  }

  const getFileIcon = (fileType: string) => {
    switch (fileType.toLowerCase()) {
      case 'pdf':
        return <IconFile className="h-4 w-4 text-red-500" />
      case 'docx':
      case 'doc':
        return <IconFile className="h-4 w-4 text-blue-500" />
      case 'xlsx':
      case 'xls':
        return <IconFile className="h-4 w-4 text-green-500" />
      case 'pptx':
      case 'ppt':
        return <IconFile className="h-4 w-4 text-orange-500" />
      case 'txt':
        return <IconFile className="h-4 w-4 text-gray-500" />
      default:
        return <IconFile className="h-4 w-4 text-purple-500" />
    }
  }

  if (isLoading) {
    return (
      <Card className={className}>
        {showHeader && (
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2">
              <IconEye className="h-5 w-5" />
              Recent Documents
            </CardTitle>
          </CardHeader>
        )}
        <CardContent className="space-y-3">
          {Array.from({ length: limit }).map((_, i) => (
            <div key={i} className="flex items-center space-x-3">
              <Skeleton className="h-4 w-4" />
              <div className="flex-1 space-y-2">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-3 w-2/3" />
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card className={className}>
        {showHeader && (
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2">
              <IconEye className="h-5 w-5" />
              Recent Documents
            </CardTitle>
          </CardHeader>
        )}
        <CardContent>
          <div className="text-center py-6">
            <p className="text-muted-foreground mb-4">Failed to load recent documents</p>
            <Button variant="outline" size="sm" onClick={loadRecentDocuments}>
              <IconRefresh className="h-4 w-4 mr-2" />
              Retry
            </Button>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (recentDocuments.length === 0) {
    return (
      <Card className={className}>
        {showHeader && (
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2">
              <IconEye className="h-5 w-5" />
              Recent Documents
            </CardTitle>
          </CardHeader>
        )}
        <CardContent>
          <div className="text-center py-8">
            <IconEye className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
            <p className="text-muted-foreground">No recent documents</p>
            <p className="text-sm text-muted-foreground mt-2">
              Documents you view will appear here
            </p>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className={className}>
      {showHeader && (
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <IconEye className="h-5 w-5" />
              Recent Documents
            </CardTitle>
            <Button 
              variant="ghost" 
              size="sm"
              onClick={loadRecentDocuments}
              className="h-8 w-8 p-0"
            >
              <IconRefresh className="h-4 w-4" />
            </Button>
          </div>
        </CardHeader>
      )}
      <CardContent className="space-y-3">
        {recentDocuments.map((document) => (
          <div
            key={document.id}
            onClick={() => handleDocumentClick(document)}
            className="flex items-center space-x-3 p-3 rounded-lg hover:bg-muted/50 cursor-pointer transition-colors group"
          >
            {/* File Icon */}
            <div className="flex-shrink-0">
              {getFileIcon(document.file_type)}
            </div>

            {/* Document Info */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <h4 className="font-medium text-sm truncate">
                  {document.title || document.filename}
                </h4>
              </div>
              
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <span className="flex items-center gap-1">
                  <IconClock className="h-3 w-3" />
                  {getRelativeTime(document.updated_at || document.created_at)}
                </span>
                <span>•</span>
                <span className="uppercase">{document.file_type}</span>
                <span>•</span>
                <span>{formatFileSize(document.file_size)}</span>
              </div>

              {/* Tags */}
              {document.tags && document.tags.length > 0 && (
                <div className="flex gap-1 mt-2">
                  {document.tags.slice(0, 2).map((tag, index) => (
                    <Badge key={index} variant="secondary" className="text-xs px-1.5 py-0">
                      {tag}
                    </Badge>
                  ))}
                  {document.tags.length > 2 && (
                    <Badge variant="outline" className="text-xs px-1.5 py-0">
                      +{document.tags.length - 2}
                    </Badge>
                  )}
                </div>
              )}
            </div>

            {/* External Link Icon */}
            <div className="flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
              <IconExternalLink className="h-4 w-4 text-muted-foreground" />
            </div>
          </div>
        ))}

        {/* View All Button */}
        {recentDocuments.length >= limit && (
          <div className="pt-2 border-t">
            <Button 
              variant="ghost" 
              className="w-full text-sm"
              onClick={() => router.push(`/${tenantId}/documents`)}
            >
              View all documents
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  )
}