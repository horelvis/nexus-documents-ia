"use client"

import Link from "next/link"
import { useState, useEffect } from "react"
import { useParams } from "next/navigation"
import { 
  IconPlus, 
  IconClock,
  IconFile,
  IconFileText,
  IconFileTypePdf,
  IconEye,
  IconDownload,
  IconEdit,
  IconLoader2
} from "@tabler/icons-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { useDocumentInsightsService, RecentDocument } from "@/lib/services/document-insights.service"
import { getFileIcon, formatFileSize, getRelativeTime } from "@/lib/document-utils"

export default function RecentDocumentsPage() {
  const params = useParams()
  const tenantId = params.tenantId as string
  const [documents, setDocuments] = useState<RecentDocument[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const documentInsightsService = useDocumentInsightsService()

  // Load recent documents from API - simple pattern
  const loadRecentDocuments = async () => {
    setIsLoading(true)
    setError(null)
    
    try {
      // Get recently viewed documents from document-insights service
      const response = await documentInsightsService.getRecentlyViewedDocuments(20, true)
      
      if (response.error) {
        setError(response.error)
      } else {
        setDocuments(response.data || [])
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load recent documents')
    } finally {
      setIsLoading(false)
    }
  }

  // Load on mount
  useEffect(() => {
    loadRecentDocuments()
  }, [])


  return (
    <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6">
      <div className="px-4 lg:px-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-8 gap-4">
          <div>
            <h1 className="text-3xl font-bold mb-2">Recent Documents</h1>
            <p className="text-muted-foreground">
              Documents you've accessed recently
            </p>
          </div>
          <div className="flex gap-2">
            <Link href={`/${tenantId}/documents`}>
              <Button variant="outline">All Documents</Button>
            </Link>
            <Link href={`/${tenantId}/documents/upload`}>
              <Button>
                <IconPlus className="mr-2 h-4 w-4" />
                Upload Document
              </Button>
            </Link>
          </div>
        </div>

        {/* Recent Activity Summary */}
        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <IconClock className="h-5 w-5" />
              Recent Activity
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="text-center">
                <p className="text-2xl font-bold text-blue-600">
                  {isLoading ? <IconLoader2 className="h-6 w-6 animate-spin mx-auto" /> : documents.length}
                </p>
                <p className="text-sm text-muted-foreground">Recent documents</p>
              </div>
              <div className="text-center">
                <p className="text-2xl font-bold text-green-600">
                  {isLoading ? <IconLoader2 className="h-6 w-6 animate-spin mx-auto" /> : documents.filter(doc => doc.indexed).length}
                </p>
                <p className="text-sm text-muted-foreground">Indexed</p>
              </div>
              <div className="text-center">
                <p className="text-2xl font-bold text-purple-600">
                  {isLoading ? <IconLoader2 className="h-6 w-6 animate-spin mx-auto" /> : '24h'}
                </p>
                <p className="text-sm text-muted-foreground">Last activity</p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Loading State */}
        {isLoading && (
          <div className="flex justify-center items-center py-12">
            <IconLoader2 className="h-8 w-8 animate-spin" />
            <span className="ml-2">Loading recent documents...</span>
          </div>
        )}

        {/* Error State */}
        {error && (
          <Card className="text-center py-12">
            <CardContent>
              <p className="text-red-600 mb-4">{error}</p>
              <Button onClick={loadRecentDocuments} variant="outline">
                Try Again
              </Button>
            </CardContent>
          </Card>
        )}

        {/* Recent Documents List */}
        {!isLoading && !error && (
          <div className="space-y-4">
            {documents.map((document: RecentDocument) => (
              <Card key={document.id} className="hover:shadow-md transition-shadow">
                <CardContent className="p-6">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4 min-w-0 flex-1">
                      {getFileIcon(document.file_type, document.mime_type, document.filename)}
                      <div className="min-w-0 flex-1">
                        <h3 className="font-semibold truncate" title={document.filename}>
                          {document.title || document.filename}
                        </h3>
                        <div className="flex items-center gap-4 text-sm text-muted-foreground mt-1">
                          <span>{formatFileSize(document.file_size)}</span>
                          <span>•</span>
                          <span>Uploaded {getRelativeTime(document.created_at)}</span>
                          {document.last_viewed_at && (
                            <>
                              <span>•</span>
                              <span>Last viewed {getRelativeTime(document.last_viewed_at)}</span>
                            </>
                          )}
                        </div>
                        <div className="flex flex-wrap gap-1 mt-2">
                          {document.tags.map((tag: string) => (
                            <Badge key={tag} variant="outline" className="text-xs">
                              {tag}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    </div>
                    
                    <div className="flex gap-2 ml-4">
                      <Button size="sm" variant="outline">
                        <IconEye className="h-4 w-4" />
                      </Button>
                      <Button size="sm" variant="outline">
                        <IconDownload className="h-4 w-4" />
                      </Button>
                      <Button size="sm" variant="outline">
                        <IconEdit className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        {!isLoading && !error && documents.length === 0 && (
          <Card className="text-center py-12">
            <CardContent>
              <IconClock className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
              <h3 className="text-lg font-semibold mb-2">No recent activity</h3>
              <p className="text-muted-foreground mb-4">
                Start viewing documents to see them appear here.
              </p>
              <Link href={`/${tenantId}/documents`}>
                <Button>
                  Browse Documents
                </Button>
              </Link>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}