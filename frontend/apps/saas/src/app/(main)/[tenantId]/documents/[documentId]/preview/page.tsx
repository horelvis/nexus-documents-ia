"use client"

import { useState, useEffect, useRef } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { ArrowLeft, Download, RefreshCw, Eye, Trash2, Share2 } from 'lucide-react'
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
import PDFEntityViewer, { DocumentEntity as PdfDocumentEntity } from '@/components/documents/pdf-entity-viewer'
import { ShareDocumentDialog } from '@/components/documents/share-document-dialog'
import { ImagePreview } from '@/components/documents/image-preview'
import { API_CONFIG } from '@/lib/config'
import { DocumentStatusIndicator } from '@/components/documents/document-status-indicator'
import { useTranslation } from '@/lib/i18n/hooks'
import { useDocumentEvents } from '@/contexts/document-events-context'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"

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
  const [isLoadingPdf, setIsLoadingPdf] = useState(false)
  const [isLoadingImage, setIsLoadingImage] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [viewStartTime, setViewStartTime] = useState<number | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)
  const [shareDialogOpen, setShareDialogOpen] = useState(false)
  const [isExtractingEntities, setIsExtractingEntities] = useState(false)
  const [focusedEntity, setFocusedEntity] = useState<PdfDocumentEntity | null>(null)

  const documentService = useDocumentService()
  const insightsService = useDocumentInsightsService()
  const { t } = useTranslation()
  const { emitDocumentEvent } = useDocumentEvents()
  const pdfViewerRef = useRef<HTMLDivElement | null>(null)

  const normalizeEntityForPdf = (entity: any): PdfDocumentEntity => ({
    class: entity.class || entity.type || 'otros',
    text: entity.text || entity.name || '',
    attributes: entity.attributes || entity.metadata || {},
    source_indices: entity.source_indices || entity.metadata?.source_indices || null,
    page: entity.page || entity.metadata?.page
  })

  const handleEntitySelect = (entity: any) => {
    const normalized = normalizeEntityForPdf(entity)
    if (!normalized.text) return

    setFocusedEntity(normalized)
    if (pdfViewerRef.current) {
      pdfViewerRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }

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

    setIsLoadingPdf(true)
    try {
      let result

      if (document.file_type === 'pdf' || document.mime_type === 'application/pdf') {
        result = await documentService.downloadDocument(document.id)
      } else {
        // For non-PDFs (like ODT), fetch the converted PDF
        result = await documentService.downloadConvertedDocument(document.id)
      }

      if ('blob' in result && result.blob) {
        const localUrl = URL.createObjectURL(result.blob)
        setPdfUrl(localUrl)
      } else {
        setError('Failed to load PDF preview')
      }
    } catch (err) {
      setError('An unexpected error occurred while loading PDF')
    } finally {
      setIsLoadingPdf(false)
    }
  }

  const loadImageUrl = async () => {
    if (!document) return

    setIsLoadingImage(true)
    try {
      // Use authenticated download service for images
      const downloadResult = await documentService.downloadDocument(document.id)
      if ('blob' in downloadResult && downloadResult.blob) {
        const localUrl = URL.createObjectURL(downloadResult.blob)
        setImageUrl(localUrl)
      } else {
        console.error('Failed to fetch image:', 'error' in downloadResult ? downloadResult.error : 'Unknown error')
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
    if (!document) return

    try {
      toast.info(t('documentsPage.notifications.downloading.title'), {
        description: t('documentsPage.notifications.downloading.message', { filename: document.filename })
      })

      const result = await documentService.downloadDocument(document.id)

      if ('error' in result) {
        toast.error(t('documentsPage.notifications.downloadFailed.title'), {
          description: t('documentsPage.notifications.downloadFailed.message', { error: result.error })
        })
        return
      }

      if (!result.blob || !(result.blob instanceof Blob)) {
        toast.error(t('documentsPage.notifications.invalidFile.title'), {
          description: t('documentsPage.notifications.invalidFile.message')
        })
        return
      }

      const url = URL.createObjectURL(result.blob)
      const a = window.document.createElement('a')
      a.href = url
      a.download = result.filename || document.filename || 'document'
      a.style.display = 'none'
      window.document.body.appendChild(a)
      a.click()

      setTimeout(() => {
        window.document.body.removeChild(a)
        URL.revokeObjectURL(url)
      }, 100)

      toast.success(t('documentsPage.notifications.downloadComplete.title'), {
        description: t('documentsPage.notifications.downloadComplete.message', { filename: document.filename })
      })
    } catch (error) {
      toast.error(t('documentsPage.notifications.downloadFailed.title'), {
        description: t('documentsPage.notifications.downloadFailed.message', { error: error instanceof Error ? error.message : 'Unknown error' })
      })
    }
  }

  const handleDelete = async () => {
    if (!document) return

    setIsDeleting(true)
    try {
      const response = await documentService.deleteDocument(document.id)
      if (response.error) {
        toast.error(t('documentsPage.notifications.deleteFailed.title'), {
          description: t('documentsPage.notifications.deleteFailed.message', { error: response.error })
        })
      } else {
        toast.success(t('documentsPage.notifications.deleteSuccess.title'), {
          description: t('documentsPage.notifications.deleteSuccess.message')
        })
        emitDocumentEvent("documents:updated", {
          tenantId,
          source: "delete"
        })
        router.push(`/${tenantId}/documents`)
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error'
      toast.error(t('documentsPage.notifications.deleteFailed.title'), {
        description: t('documentsPage.notifications.deleteFailed.message', { error: errorMessage })
      })
    } finally {
      setIsDeleting(false)
    }
  }

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 Bytes'
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
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

  // Load PDF URL - for native PDFs load immediately, for others wait for conversion
  useEffect(() => {
    const isNativePdf = document?.file_type === 'pdf' || document?.mime_type === 'application/pdf'

    // For native PDFs, load immediately without waiting for preview
    if (document && isNativePdf && !pdfUrl && !isLoadingPdf) {
      loadPdfUrl()
      return
    }

    // For converted PDFs, wait until preview confirms it's available
    if (preview && preview.pdf_available && !pdfUrl && !isLoadingPdf) {
      loadPdfUrl()
    }
  }, [document, preview, pdfUrl, isLoadingPdf, loadPdfUrl])

  // Track polling attempts to stop infinite polling
  const [pollingAttempts, setPollingAttempts] = useState(0)
  const MAX_POLLING_ATTEMPTS = 5

  useEffect(() => {
    // Poll for preview if conversion is not yet complete (max 5 attempts)
    const isPending = preview?.conversion_method === 'none' || !preview?.conversion_method
    if (preview && !preview.pdf_available && isPending && pollingAttempts < MAX_POLLING_ATTEMPTS) {
      const timer = setTimeout(() => {
        setPollingAttempts(prev => prev + 1)
        generatePreview(false)
      }, 3000)
      return () => clearTimeout(timer)
    }
  }, [preview, pollingAttempts])

  // Poll for entities if document is processing (no entities yet)
  const [entityPollingAttempts, setEntityPollingAttempts] = useState(0)
  const MAX_ENTITY_POLLING_ATTEMPTS = 10

  useEffect(() => {
    const hasNoEntities = !document?.extracted_entities || document.extracted_entities.length === 0
    const isProcessing = document && Number(document.indexed) < 1

    // Start polling if document has no entities and might still be processing
    if (document && hasNoEntities && entityPollingAttempts < MAX_ENTITY_POLLING_ATTEMPTS) {
      setIsExtractingEntities(true)
      const timer = setTimeout(async () => {
        setEntityPollingAttempts(prev => prev + 1)
        // Refresh document to check for entities
        const response = await documentService.getDocument(documentId)
        if (response.data) {
          setDocument(response.data)
          // Stop polling if entities found
          if (response.data.extracted_entities && response.data.extracted_entities.length > 0) {
            setIsExtractingEntities(false)
          }
        }
      }, 10000)
      return () => clearTimeout(timer)
    } else if (document?.extracted_entities && document.extracted_entities.length > 0) {
      setIsExtractingEntities(false)
    } else if (entityPollingAttempts >= MAX_ENTITY_POLLING_ATTEMPTS) {
      setIsExtractingEntities(false)
    }
  }, [document, entityPollingAttempts, documentId])

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
    // Reset polling attempts for new document
    setPollingAttempts(0)
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
            {searchParams.get('returnTo') === 'search' ? t('documentPreview.backToSearch') : t('documentPreview.backToDocuments')}
          </Button>
        </div>

        <div className="flex items-center gap-2">
          {document && (
            <Button variant="outline" size="sm" onClick={handleDownload}>
              <Download className="h-4 w-4 mr-2" />
              {t('common.download')}
            </Button>
          )}

          {document && (
            <Button variant="outline" size="sm" onClick={() => setShareDialogOpen(true)}>
              <Share2 className="h-4 w-4 mr-2" />
              {t('documentPreview.share')}
            </Button>
          )}

          {document && (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="outline" size="sm" disabled={isDeleting}>
                  <Trash2 className="h-4 w-4 mr-2" />
                  {t('common.delete')}
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>{t('documentPreview.deleteConfirm.title')}</AlertDialogTitle>
                  <AlertDialogDescription>
                    {t('documentPreview.deleteConfirm.description')}
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
                  <AlertDialogAction
                    onClick={handleDelete}
                    className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                  >
                    {isDeleting ? t('common.loading') : t('common.delete')}
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}

          {/* Only show Regenerate for non-native PDFs that need conversion */}
          {document?.file_type !== 'pdf' && document?.mime_type !== 'application/pdf' && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => generatePreview(true)}
              disabled={isLoadingPreview || !preview?.conversion_method}
            >
              <RefreshCw className={`h-4 w-4 mr-2 ${isLoadingPreview || !preview?.conversion_method ? 'animate-spin' : ''}`} />
              {t('documentPreview.regenerate')}
            </Button>
          )}
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
          <div className="lg:col-span-3 flex flex-col min-h-0">
            {/* Show loading skeleton only for non-native PDFs that need conversion */}
            {(() => {
              const isNativePdf = document.file_type === 'pdf' || document.mime_type === 'application/pdf'
              if (isNativePdf) return false
              const isPending = !preview?.conversion_method || preview?.conversion_method === 'none'
              if (pollingAttempts >= MAX_POLLING_ATTEMPTS) return false
              return isLoadingPreview || (preview && !preview.pdf_available && isPending)
            })() && (
              <div className="space-y-4">
                <div className="flex items-center gap-2">
                  <RefreshCw className="h-4 w-4 animate-spin" />
                  <span className="text-sm text-muted-foreground">
                    {isLoadingPreview
                      ? 'Checking preview status...'
                      : `Generating preview in background... (${pollingAttempts + 1}/${MAX_POLLING_ATTEMPTS})`}
                  </span>
                </div>
                <Skeleton className="h-32 w-full" />
                <Skeleton className="h-48 w-full" />
              </div>
            )}

            {/* Show message when conversion failed/timed out */}
            {(() => {
              const isNativePdf = document.file_type === 'pdf' || document.mime_type === 'application/pdf'
              if (isNativePdf) return false
              const isPending = !preview?.conversion_method || preview?.conversion_method === 'none'
              return preview && !preview.pdf_available && isPending && pollingAttempts >= MAX_POLLING_ATTEMPTS
            })() && (
              <div className="text-center py-12 space-y-4">
                <div className="w-16 h-16 mx-auto bg-muted rounded-full flex items-center justify-center">
                  <Eye className="h-8 w-8 text-muted-foreground" />
                </div>
                <div className="space-y-2">
                  <h3 className="text-lg font-semibold">Preview Not Available</h3>
                  <p className="text-muted-foreground max-w-md mx-auto">
                    The document conversion is taking longer than expected. You can download the original file or try regenerating the preview.
                  </p>
                  <div className="flex justify-center gap-2 mt-4">
                    <Button variant="outline" size="sm" onClick={handleDownload}>
                      <Download className="h-4 w-4 mr-2" />
                      Download Original
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => {
                      setPollingAttempts(0)
                      generatePreview(true)
                    }}>
                      <RefreshCw className="h-4 w-4 mr-2" />
                      Try Again
                    </Button>
                  </div>
                </div>
              </div>
            )}

            {/* Show PDF viewer for native PDFs or when converted PDF is available */}
            {(() => {
              const isNativePdf = document.file_type === 'pdf' || document.mime_type === 'application/pdf'
              const shouldShowPdfSection = isNativePdf || (preview && preview.pdf_available)
              return shouldShowPdfSection
            })() && (
              <div ref={pdfViewerRef} className="flex-1 flex flex-col min-h-0">
                {pdfUrl ? (
                  <div className="flex-1 bg-card rounded-lg border overflow-hidden">
                    <PDFEntityViewer
                      url={pdfUrl}
                      fileName={document.filename}
                      focusedEntity={focusedEntity}
                      showToolbar={true}
                      initialScale={0.9}
                      height="100%"
                      className="h-full"
                    />
                  </div>
                ) : (
                  <div className="flex-1 flex items-center justify-center bg-card rounded-lg border">
                    <div className="text-center">
                      <RefreshCw className="h-8 w-8 animate-spin mx-auto mb-4" />
                      <p className="text-muted-foreground">Loading PDF...</p>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Image Preview */}
            {preview?.type === 'image_preview' && document && (
              <div className="flex-1 flex flex-col min-h-0 bg-card rounded-lg border">
                {isLoadingImage && (
                  <div className="flex-1 flex items-center justify-center">
                    <div className="text-center">
                      <RefreshCw className="h-8 w-8 animate-spin mx-auto mb-4" />
                      <p className="text-muted-foreground">Loading image...</p>
                    </div>
                  </div>
                )}
                {imageUrl && !isLoadingImage && (
                  <div className="flex-1 min-h-0 p-4">
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
                )}
                {!imageUrl && !isLoadingImage && error && (
                  <div className="flex-1 flex items-center justify-center">
                    <p className="text-red-600">Failed to load image</p>
                  </div>
                )}
              </div>
            )}

            {/* Text Preview */}
            {preview?.text_preview && (
              <div className="flex-1 bg-card rounded-lg border">
                <ScrollArea className="h-full w-full">
                  <div className="p-4">
                    <pre className="text-sm whitespace-pre-wrap font-mono">
                      {preview.text_preview}
                    </pre>
                  </div>
                </ScrollArea>
              </div>
            )}

            {/* Unsupported Format */}
            {preview?.type === 'unsupported_fallback' && (
              <div className="flex-1 bg-card rounded-lg border flex items-center justify-center">
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
              </div>
            )}
          </div>

          {/* Sidebar with Document Info and Entities */}
          <div className="lg:col-span-1 space-y-4">
            {/* Document Information Card */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">{t('documentPreview.documentInfo.title')}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {/* Document Name */}
                <div className="pb-2 border-b">
                  <h3 className="font-semibold text-sm truncate" title={document.title || document.filename}>
                    {document.title || document.filename}
                  </h3>
                </div>

                {/* File Details */}
                <div className="text-sm space-y-2">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">{t('documentPreview.documentInfo.type')}:</span>
                    <span className="font-medium">{document.file_type.toUpperCase()}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">{t('documentPreview.documentInfo.size')}:</span>
                    <span>{formatFileSize(document.file_size)}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-muted-foreground">{t('documentPreview.documentInfo.status')}:</span>
                    <DocumentStatusIndicator
                      status={document.indexed}
                      showDescription={true}
                      size="sm"
                    />
                  </div>
                  {document.category && (
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">{t('documentPreview.documentInfo.category')}:</span>
                      <Badge variant="secondary" className="text-xs">
                        {document.category}
                      </Badge>
                    </div>
                  )}
                </div>

                {/* Tags */}
                {document.tags.length > 0 && (
                  <>
                    <Separator />
                    <div className="space-y-2">
                      <span className="text-sm text-muted-foreground">{t('documentPreview.documentInfo.tags')}:</span>
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

              </CardContent>
            </Card>

            {/* Entities Card - Below Document Info */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center justify-between">
                  <span>{t('documentPreview.extractedEntities.title')}</span>
                  {document.extracted_entities && document.extracted_entities.length > 0 && (
                    <Badge variant="secondary" className="text-xs">
                      {document.extracted_entities.length}
                    </Badge>
                  )}
                  {isExtractingEntities && (
                    <RefreshCw className="h-4 w-4 animate-spin text-muted-foreground" />
                  )}
                </CardTitle>
              </CardHeader>
              <CardContent>
                {/* Extracting state */}
                {isExtractingEntities && (!document.extracted_entities || document.extracted_entities.length === 0) && (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground py-4">
                    <RefreshCw className="h-4 w-4 animate-spin" />
                    <span>{t('documentPreview.extractedEntities.extracting')}</span>
                  </div>
                )}

                {/* No entities found */}
                {!isExtractingEntities && (!document.extracted_entities || document.extracted_entities.length === 0) && (
                  <div className="text-sm text-muted-foreground py-4 text-center">
                    {t('documentPreview.extractedEntities.noEntities')}
                  </div>
                )}

                {/* Entities list */}
                {document.extracted_entities && document.extracted_entities.length > 0 && (
                  <ScrollArea className="max-h-[400px]">
                    <div className="space-y-3">
                      {(() => {
                        // Group entities by type
                        const grouped: Record<string, any[]> = {}
                        document.extracted_entities.forEach((e: any) => {
                          const type = e.type || e.class || 'other'
                          if (!grouped[type]) grouped[type] = []
                          grouped[type].push(e)
                        })

                        const typeLabels: Record<string, string> = {
                          trabajador: 'Trabajador',
                          person: 'Persona',
                          empresa: 'Empresa',
                          organization: 'Organización',
                          amount: 'Importe',
                          liquido: 'Líquido',
                          devengo: 'Devengo',
                          deduccion: 'Deducción',
                          fecha: 'Fecha',
                          date: 'Fecha',
                          periodo: 'Período',
                          invoice_number: 'Nº Factura',
                          iban: 'IBAN',
                          cliente: 'Cliente'
                        }

                        const typeColors: Record<string, string> = {
                          trabajador: 'bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300',
                          person: 'bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300',
                          empresa: 'bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300',
                          organization: 'bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300',
                          amount: 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300',
                          liquido: 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300',
                          devengo: 'bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300',
                          deduccion: 'bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-300',
                          fecha: 'bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300',
                          date: 'bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300',
                          periodo: 'bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300'
                        }

                        return Object.entries(grouped).map(([type, entities]) => (
                          <div key={type} className="space-y-1.5">
                            <div className={`text-xs font-medium uppercase px-2 py-1 rounded ${typeColors[type] || 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400'}`}>
                              {typeLabels[type] || type}
                            </div>
                            <div className="pl-2 space-y-1">
                              {entities.map((entity: any, idx: number) => {
                                const entityText = entity.name || entity.text
                                return (
                                  <div
                                    key={idx}
                                    className="text-sm py-1 px-2 rounded hover:bg-muted cursor-pointer transition-colors"
                                    onClick={() => handleEntitySelect(entity)}
                                  >
                                    <span className="font-medium">{entityText}</span>
                                    {(
                                      entity.metadata?.role || entity.attributes?.role
                                    ) && (
                                      <span className="text-xs text-muted-foreground ml-2">
                                        ({entity.metadata?.role || entity.attributes?.role})
                                      </span>
                                    )}
                                  </div>
                                )
                              })}
                            </div>
                          </div>
                        ))
                      })()}
                    </div>
                  </ScrollArea>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      {/* Share Dialog */}
      <ShareDocumentDialog
        document={document}
        open={shareDialogOpen}
        onOpenChange={setShareDialogOpen}
      />
    </div>
  )
}
