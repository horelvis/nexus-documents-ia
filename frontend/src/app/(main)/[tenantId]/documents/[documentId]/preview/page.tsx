"use client"

import { useState, useEffect, useCallback } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { ArrowLeft, Download, RefreshCw, Eye, Share2, ExternalLink } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Separator } from '@/components/ui/separator'
import { ScrollArea } from '@/components/ui/scroll-area'
import { toast } from 'sonner'
import { Document, DocumentPreviewResponse } from '@/lib/types'
import { useDocumentService } from '@/lib/services/document.service'
import { useDocumentInsightsService } from '@/lib/services/document-insights.service'
import PDFViewer from '@/components/documents/pdf-viewer'
import { ShareDocumentDialog } from '@/components/documents/share-document-dialog'
import { ImagePreview } from '@/components/documents/image-preview'
import { API_CONFIG } from '@/lib/config'
import { DocumentStatusIndicator } from '@/components/documents/document-status-indicator'

export default function DocumentPreviewPage() {
  const params = useParams()
  const router = useRouter()
  const searchParams = useSearchParams()
  const documentId = params.documentId as string
  const tenantId = params.tenantId as string

  const [document, setDocument] = useState<Document | null>(null)
  const [preview, setPreview] = useState<DocumentPreviewResponse | null>(null)
  const [pdfUrl, setPdfUrl] = useState<string | null>(null)
  const [imageUrl, setImageUrl] = useState<string | null>(null)
  const [isLoadingDocument, setIsLoadingDocument] = useState(true)
  const [isLoadingPreview, setIsLoadingPreview] = useState(false)
  const [isLoadingImage, setIsLoadingImage] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [shareDialogOpen, setShareDialogOpen] = useState(false)
  const [viewStartTime, setViewStartTime] = useState<number | null>(null)

  const documentService = useDocumentService()
  const insightsService = useDocumentInsightsService()

  // Helper function to construct full URLs for images (used for PDF thumbnails)
  const getFullImageUrl = (path: string) => {
    if (path.startsWith('http')) {
      return path // Already a full URL
    }
    
    // The path already includes /api/v1, so just use the base URL
    return `${API_CONFIG.BASE_URL}${path}`
  }

  const loadDocument = async () => {
    setIsLoadingDocument(true)
    setError(null)

    try {
      const response = await documentService.getDocument(documentId)
      
      if (response.error) {
        setError(response.error)
        toast.error('Failed to load document', {
          description: response.error
        })
      } else if (response.data) {
        setDocument(response.data)
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load document'
      setError(errorMessage)
      toast.error('Document loading failed', {
        description: errorMessage
      })
    } finally {
      setIsLoadingDocument(false)
    }
  }

  const generatePreview = async (forceRegenerate = false) => {
    setIsLoadingPreview(true)
    setError(null)

    try {
      const response = await documentService.getDocumentPreview(documentId, forceRegenerate)
      
      if (response.error) {
        setError(response.error)
        toast.error('Failed to generate preview', {
          description: response.error
        })
      } else if (response.data) {
        setPreview(response.data)
        
        // For PDF files, get signed URL for PDF viewer
        if (response.data.pdf_available && document?.file_type === 'pdf') {
          await loadPdfUrl()
        }
        
        if (forceRegenerate) {
          toast.success('Preview regenerated successfully')
        }
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to generate preview'
      setError(errorMessage)
      toast.error('Preview generation failed', {
        description: errorMessage
      })
    } finally {
      setIsLoadingPreview(false)
    }
  }

  const loadPdfUrl = async () => {
    if (!document) return
    
    try {
      // Use new streaming endpoint
      const downloadResult = await documentService.downloadDocument(document.id)
      if (downloadResult.blob) {
        const localUrl = URL.createObjectURL(downloadResult.blob)
        setPdfUrl(localUrl)
      } else {
        console.error('Failed to fetch PDF:', downloadResult.error)
      }
    } catch (err) {
      console.error('Failed to get PDF URL:', err)
    }
  }

  const loadImageUrl = async () => {
    if (!document) return
    
    setIsLoadingImage(true)
    try {
      // Use authenticated download service for images
      const downloadResult = await documentService.downloadDocument(document.id)
      if (downloadResult.blob) {
        const localUrl = URL.createObjectURL(downloadResult.blob)
        setImageUrl(localUrl)
      } else {
        console.error('Failed to fetch image:', downloadResult.error)
        setError('Failed to load image')
      }
    } catch (err) {
      console.error('Failed to get image URL:', err)
      setError('Failed to load image')
    } finally {
      setIsLoadingImage(false)
    }
  }

  const handleDownload = async () => {
    if (!document) {
      toast.error('No document selected')
      return
    }
    
    try {
      toast.info('Downloading document...')
      console.log('Downloading document:', document.id, document.filename)
      
      const result = await documentService.downloadDocument(document.id)
      console.log('Download result:', result)
      
      if ('error' in result) {
        console.error('Download error:', result.error)
        toast.error('Download failed', { description: result.error })
        return
      }

      // Verify we have a blob
      if (!result.blob || !(result.blob instanceof Blob)) {
        console.error('Invalid blob received:', result)
        toast.error('Download failed', { description: 'Invalid file data received' })
        return
      }

      console.log('Creating download link for:', result.filename, 'size:', result.blob.size)
      
      // Create download link
      const url = URL.createObjectURL(result.blob)
      const a = window.document.createElement('a')
      a.href = url
      a.download = result.filename || document.filename || 'document'
      a.style.display = 'none'
      window.document.body.appendChild(a)
      a.click()
      
      // Cleanup
      setTimeout(() => {
        window.document.body.removeChild(a)
        URL.revokeObjectURL(url)
      }, 100)
      
      toast.success('Document downloaded successfully')
    } catch (error) {
      console.error('Download exception:', error)
      toast.error('Download failed', {
        description: error instanceof Error ? error.message : 'Unknown error'
      })
    }
  }

  const handleShare = () => {
    setShareDialogOpen(true)
  }

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 Bytes'
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  const formatDate = (timestamp: number) => {
    return new Date(timestamp * 1000).toLocaleString()
  }

  const getPreviewStatusBadge = (preview: DocumentPreviewResponse) => {
    if (preview.conversion_method === 'gotenberg') {
      return (
        <Badge className="bg-green-100 text-green-800 border-green-200">
          Gotenberg Conversion
        </Badge>
      )
    } else if (preview.conversion_method === 'fallback') {
      return <Badge variant="secondary">Fallback Preview</Badge>
    } else {
      return <Badge variant="outline">Native Preview</Badge>
    }
  }

  // Load document and preview on mount
  useEffect(() => {
    loadDocument()
  }, [documentId])

  useEffect(() => {
    if (document && !preview && !isLoadingPreview) {
      generatePreview()
    }
  }, [document])

  // Track view start time for potential future metrics
  useEffect(() => {
    if (document?.id) {
      setViewStartTime(Date.now())
    }
  }, [document?.id])

  // Load image URL when preview indicates it's an image
  useEffect(() => {
    if (preview && preview.type === 'image_preview' && document && !imageUrl && !isLoadingImage) {
      loadImageUrl()
    }
  }, [preview?.type, document?.id, !!imageUrl])

  // Cleanup blob URLs on unmount
  useEffect(() => {
    return () => {
      if (pdfUrl && pdfUrl.startsWith('blob:')) {
        URL.revokeObjectURL(pdfUrl)
      }
      if (imageUrl && imageUrl.startsWith('blob:')) {
        URL.revokeObjectURL(imageUrl)
      }
    }
  }, [])

  useEffect(() => {
    // Cleanup when document changes
    if (pdfUrl && pdfUrl.startsWith('blob:')) {
      URL.revokeObjectURL(pdfUrl)
      setPdfUrl(null)
    }
    if (imageUrl && imageUrl.startsWith('blob:')) {
      URL.revokeObjectURL(imageUrl)
      setImageUrl(null)
    }
  }, [documentId])

  return (
    <div className="container mx-auto p-6 h-screen flex flex-col space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button 
            variant="outline" 
            size="sm"
            onClick={() => {
              const returnTo = searchParams.get('returnTo')
              if (returnTo === 'search') {
                // Return to search with preserved context
                const query = searchParams.get('query') || ''
                const tags = searchParams.get('tags') || ''
                const dateFrom = searchParams.get('dateFrom') || ''
                const dateTo = searchParams.get('dateTo') || ''
                
                const searchUrl = new URLSearchParams()
                if (query) searchUrl.set('q', query)
                if (tags) searchUrl.set('tags', tags)
                if (dateFrom) searchUrl.set('dateFrom', dateFrom)
                if (dateTo) searchUrl.set('dateTo', dateTo)
                
                router.push(`/${tenantId}/search?${searchUrl.toString()}`)
              } else {
                router.push(`/${tenantId}/documents`)
              }
            }}
          >
            <ArrowLeft className="h-4 w-4 mr-2" />
            {searchParams.get('returnTo') === 'search' ? 'Back to Search' : 'Back to Documents'}
          </Button>
          
          {document && (
            <div>
              <h1 className="text-2xl font-bold">{document.title || document.filename}</h1>
              <p className="text-muted-foreground">
                {formatFileSize(document.file_size)} • {document.file_type}
              </p>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={handleShare}>
            <Share2 className="h-4 w-4 mr-2" />
            Share
          </Button>
          
          {document && (
            <Button variant="outline" size="sm" onClick={handleDownload}>
              <Download className="h-4 w-4 mr-2" />
              Download
            </Button>
          )}
          
          <Button 
            variant="outline" 
            size="sm" 
            onClick={() => generatePreview(true)}
            disabled={isLoadingPreview}
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${isLoadingPreview ? 'animate-spin' : ''}`} />
            Regenerate
          </Button>
        </div>
      </div>

      {/* Loading States */}
      {isLoadingDocument && (
        <Card>
          <CardHeader>
            <Skeleton className="h-6 w-1/3" />
            <Skeleton className="h-4 w-1/2" />
          </CardHeader>
          <CardContent className="space-y-4">
            <Skeleton className="h-32 w-full" />
            <Skeleton className="h-48 w-full" />
          </CardContent>
        </Card>
      )}

      {/* Error State */}
      {error && !isLoadingDocument && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Preview Content */}
      {document && (
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 flex-1 min-h-0">
          {/* Main Preview Area */}
          <div className="lg:col-span-3 flex flex-col">
            <Card className="flex-1 flex flex-col">
              <CardHeader className="flex-shrink-0">
                <div className="flex items-center justify-between">
                  <CardTitle className="flex items-center gap-2">
                    <Eye className="h-5 w-5" />
                    Document Preview
                  </CardTitle>
                  {preview && getPreviewStatusBadge(preview)}
                </div>
              </CardHeader>
              <CardContent className="flex-1 flex flex-col min-h-[75vh]">
                {isLoadingPreview && (
                  <div className="space-y-4">
                    <div className="flex items-center gap-2">
                      <RefreshCw className="h-4 w-4 animate-spin" />
                      <span className="text-sm text-muted-foreground">
                        Generating preview with Gotenberg...
                      </span>
                    </div>
                    <Skeleton className="h-32 w-full" />
                    <Skeleton className="h-48 w-full" />
                  </div>
                )}

                {preview && !isLoadingPreview && (
                  <div className="space-y-6">
                    {/* PDF Viewer */}
                    {preview.pdf_available && document?.file_type === 'pdf' && (
                      <div className="space-y-4">
                        <h3 className="text-lg font-semibold">PDF Document</h3>
                        {pdfUrl ? (
                          <div className="border rounded-lg overflow-hidden">
                            <PDFViewer
                              url={pdfUrl}
                              fileName={document.filename}
                              showToolbar={true}
                              initialScale={0.9}
                              height="75vh"
                              className="bg-white"
                            />
                          </div>
                        ) : (
                          <div className="flex items-center justify-center h-[60vh] border rounded-lg">
                            <div className="text-center">
                              <RefreshCw className="h-8 w-8 animate-spin mx-auto mb-4" />
                              <p className="text-muted-foreground">Loading PDF...</p>
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                    {/* PDF Thumbnails */}
                    {preview.pdf_available && preview.thumbnails.length > 0 && (
                      <div className="space-y-4">
                        <h3 className="text-lg font-semibold">PDF Page Thumbnails</h3>
                        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                          {preview.thumbnails.map((thumbnail, index) => {
                            const thumbnailUrl = getFullImageUrl(thumbnail)
                            
                            return (
                              <div key={index} className="space-y-2">
                                <div className="aspect-[3/4] bg-muted rounded-lg overflow-hidden border-2 border-border hover:border-primary/50 transition-colors">
                                  <img
                                    src={thumbnailUrl}
                                    alt={`Page ${index + 1}`}
                                    className="w-full h-full object-contain cursor-pointer hover:scale-105 transition-transform"
                                    onClick={() => {
                                      // Open in new tab for full view
                                      window.open(thumbnailUrl, '_blank')
                                    }}
                                  />
                                </div>
                              <p className="text-sm text-center text-muted-foreground">
                                Page {index + 1}
                              </p>
                            </div>
                            )
                          })}
                        </div>
                      </div>
                    )}

                    {/* Image Preview */}
                    {preview.type === 'image_preview' && document && (
                      <div className="h-full flex flex-col">
                        <div className="flex items-center justify-between mb-4">
                          <h3 className="text-lg font-semibold">Image Preview</h3>
                        </div>
                        {isLoadingImage && (
                          <div className="flex-1 flex items-center justify-center">
                            <div className="text-center">
                              <RefreshCw className="h-8 w-8 animate-spin mx-auto mb-4" />
                              <p className="text-muted-foreground">Loading image...</p>
                            </div>
                          </div>
                        )}
                        {imageUrl && !isLoadingImage && (
                          <div className="flex-1 min-h-0">
                            <div className="relative w-full h-full">
                              <ImagePreview
                                src={imageUrl}
                                alt={document.title || document.filename}
                                fileName={document.filename}
                                originalDimensions={preview.original_dimensions}
                                fileSize={document.file_size}
                                mimeType={document.mime_type}
                                className="h-full"
                              />
                            </div>
                          </div>
                        )}
                        {!imageUrl && !isLoadingImage && error && (
                          <div className="flex-1 flex items-center justify-center">
                            <p className="text-red-600">Failed to load image</p>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Text Preview */}
                    {preview.text_preview && (
                      <div className="space-y-4">
                        <h3 className="text-lg font-semibold">Text Content</h3>
                        <ScrollArea className="h-96 w-full rounded-lg border">
                          <div className="p-4">
                            <pre className="text-sm whitespace-pre-wrap font-mono">
                              {preview.text_preview}
                            </pre>
                          </div>
                        </ScrollArea>
                      </div>
                    )}

                    {/* Unsupported Format */}
                    {preview.type === 'unsupported_fallback' && (
                      <div className="text-center py-12 space-y-4">
                        <div className="w-16 h-16 mx-auto bg-muted rounded-full flex items-center justify-center">
                          <Eye className="h-8 w-8 text-muted-foreground" />
                        </div>
                        <div className="space-y-2">
                          <h3 className="text-lg font-semibold">Preview Not Available</h3>
                          <p className="text-muted-foreground max-w-md mx-auto">
                            {preview.message}
                          </p>
                          {preview.supported_formats && (
                            <div className="text-sm text-muted-foreground">
                              <p className="mb-2">Supported formats:</p>
                              <div className="flex flex-wrap gap-2 justify-center">
                                {Object.entries(preview.supported_formats).map(([category, formats]) => (
                                  <Badge key={category} variant="outline">
                                    {formats.join(', ')}
                                  </Badge>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Sidebar with Document Info */}
          <div className="lg:col-span-1">
            <Card>
              <CardHeader>
                <CardTitle>Document Information</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <h4 className="font-medium">File Details</h4>
                  <div className="text-sm space-y-1">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Type:</span>
                      <span>{document.file_type}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Size:</span>
                      <span>{formatFileSize(document.file_size)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Estado:</span>
                      <DocumentStatusIndicator 
                        status={document.indexed}
                        showDescription={true}
                        size="md"
                      />
                    </div>
                  </div>
                </div>

                {document.tags.length > 0 && (
                  <>
                    <Separator />
                    <div className="space-y-2">
                      <h4 className="font-medium">Tags</h4>
                      <div className="flex flex-wrap gap-1">
                        {document.tags.map((tag, index) => (
                          <Badge key={index} variant="outline" className="text-xs">
                            {tag}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  </>
                )}

                {document.description && (
                  <>
                    <Separator />
                    <div className="space-y-2">
                      <h4 className="font-medium">Description</h4>
                      <p className="text-sm text-muted-foreground">
                        {document.description}
                      </p>
                    </div>
                  </>
                )}

                {preview && (
                  <>
                    <Separator />
                    <div className="space-y-2">
                      <h4 className="font-medium">Preview Details</h4>
                      <div className="text-sm space-y-1">
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Method:</span>
                          <span className="capitalize">{preview.conversion_method}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">PDF Available:</span>
                          <span>{preview.pdf_available ? 'Yes' : 'No'}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Cached:</span>
                          <span>{preview.cached ? 'Yes' : 'No'}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Generated:</span>
                          <span className="text-xs">{formatDate(preview.generated_at)}</span>
                        </div>
                      </div>
                    </div>
                  </>
                )}

                <Separator />
                <div className="space-y-2">
                  <h4 className="font-medium">Actions</h4>
                  <div className="space-y-2">
                    <Button 
                      variant="outline" 
                      size="sm" 
                      className="w-full justify-start" 
                      onClick={handleDownload}
                    >
                      <Download className="h-4 w-4 mr-2" />
                      Download Original
                    </Button>
                    <Button 
                      variant="outline" 
                      size="sm" 
                      className="w-full justify-start"
                      onClick={() => router.push(`/${tenantId}/documents/${documentId}`)}
                    >
                      <ExternalLink className="h-4 w-4 mr-2" />
                      View Details
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      {/* Share Dialog */}
      {document && (
        <ShareDocumentDialog
          documentId={document.id}
          documentTitle={document.title || document.filename}
          open={shareDialogOpen}
          onOpenChange={setShareDialogOpen}
        />
      )}
    </div>
  )
}
