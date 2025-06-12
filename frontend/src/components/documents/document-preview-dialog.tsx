"use client"

import { useState, useEffect } from 'react'
import { 
  Dialog, 
  DialogContent, 
  DialogHeader, 
  DialogTitle, 
  DialogDescription,
  DialogFooter
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { 
  FileText, 
  Download, 
  RefreshCw, 
  Eye, 
  Image as ImageIcon,
  FileImage,
  AlertCircle,
  CheckCircle,
  Clock,
  Zap
} from 'lucide-react'
import { Document, DocumentPreviewResponse } from '@/lib/types'
import PDFViewer from './pdf-viewer'
import { useDocumentService } from '@/lib/services/document.service'
import { toast } from 'sonner'

interface DocumentPreviewDialogProps {
  document: Document | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function DocumentPreviewDialog({ 
  document, 
  open, 
  onOpenChange 
}: DocumentPreviewDialogProps) {
  const [preview, setPreview] = useState<DocumentPreviewResponse | null>(null)
  const [pdfUrl, setPdfUrl] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  
  const documentService = useDocumentService()

  const generatePreview = async (forceRegenerate = false) => {
    if (!document) return

    setIsLoading(true)
    setError(null)

    try {
      const response = await documentService.getDocumentPreview(document.id, forceRegenerate)
      
      if (response.error) {
        setError(response.error)
        toast.error('Failed to generate preview', {
          description: response.error
        })
      } else if (response.data) {
        setPreview(response.data)
        
        // For PDF files, get signed URL for PDF viewer
        if (response.data.pdf_available && document.file_type === 'pdf') {
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
      setIsLoading(false)
    }
  }

  const loadPdfUrl = async () => {
    if (!document) return
    
    try {
      const urlResponse = await documentService.getDocumentDownloadUrl(document.id)
      if (urlResponse.data?.download_url) {
        setPdfUrl(urlResponse.data.download_url)
      }
    } catch (err) {
      console.error('Failed to get PDF URL:', err)
    }
  }

  // Load preview when dialog opens
  useEffect(() => {
    if (open && document && !preview && !isLoading) {
      generatePreview()
    }
  }, [open, document])

  // Reset state when dialog closes or document changes
  useEffect(() => {
    if (!open || !document) {
      setPreview(null)
      setPdfUrl(null)
      setError(null)
    }
  }, [open, document?.id])

  const handleDownload = async () => {
    if (!document) return
    
    try {
      const result = await documentService.downloadDocument(document.id)
      
      if ('error' in result) {
        toast.error('Download failed', { description: result.error })
        return
      }

      // Create download link
      const url = URL.createObjectURL(result.blob)
      const a = document.createElement('a')
      a.href = url
      a.download = result.filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      
      toast.success('Document downloaded successfully')
    } catch (error) {
      toast.error('Download failed', {
        description: error instanceof Error ? error.message : 'Unknown error'
      })
    }
  }

  const getPreviewIcon = (type: string) => {
    switch (type) {
      case 'office_preview':
      case 'text_preview':
      case 'pdf_preview':
        return <FileText className="h-4 w-4" />
      case 'image_preview':
        return <ImageIcon className="h-4 w-4" />
      default:
        return <FileImage className="h-4 w-4" />
    }
  }

  const getPreviewStatusBadge = (preview: DocumentPreviewResponse) => {
    if (preview.conversion_method === 'gotenberg') {
      return (
        <Badge variant="default" className="bg-green-100 text-green-800 border-green-200">
          <Zap className="h-3 w-3 mr-1" />
          Gotenberg
        </Badge>
      )
    } else if (preview.conversion_method === 'fallback') {
      return (
        <Badge variant="secondary">
          <AlertCircle className="h-3 w-3 mr-1" />
          Fallback
        </Badge>
      )
    } else {
      return (
        <Badge variant="outline">
          <CheckCircle className="h-3 w-3 mr-1" />
          Native
        </Badge>
      )
    }
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

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Eye className="h-5 w-5" />
            Document Preview
          </DialogTitle>
          {document && (
            <DialogDescription>
              {document.filename} • {formatFileSize(document.file_size)} • {document.file_type}
            </DialogDescription>
          )}
        </DialogHeader>

        <div className="flex-1 min-h-0 flex flex-col gap-4">
          {/* Preview Info Bar */}
          {preview && (
            <div className="flex items-center justify-between p-3 bg-muted/50 rounded-lg">
              <div className="flex items-center gap-3">
                {getPreviewIcon(preview.type)}
                <div className="flex flex-col gap-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">
                      {preview.type.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())}
                    </span>
                    {getPreviewStatusBadge(preview)}
                    {preview.cached && (
                      <Badge variant="outline" className="bg-blue-50 text-blue-700 border-blue-200">
                        <Clock className="h-3 w-3 mr-1" />
                        Cached
                      </Badge>
                    )}
                  </div>
                  <span className="text-xs text-muted-foreground">
                    Generated {formatDate(preview.generated_at)}
                  </span>
                </div>
              </div>
              <Button 
                variant="outline" 
                size="sm" 
                onClick={() => generatePreview(true)}
                disabled={isLoading}
              >
                <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
                Regenerate
              </Button>
            </div>
          )}

          {/* Loading State */}
          {isLoading && (
            <div className="flex-1 space-y-4 p-4">
              <div className="flex items-center gap-2">
                <RefreshCw className="h-4 w-4 animate-spin" />
                <span className="text-sm text-muted-foreground">
                  Generating preview with Gotenberg...
                </span>
              </div>
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-32 w-full" />
              <Skeleton className="h-48 w-full" />
            </div>
          )}

          {/* Error State */}
          {error && !isLoading && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>
                {error}
              </AlertDescription>
            </Alert>
          )}

          {/* Preview Content */}
          {preview && !isLoading && (
            <ScrollArea className="flex-1 rounded-lg border">
              <div className="p-4 space-y-4">
                {/* PDF Viewer */}
                {preview.pdf_available && (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <h4 className="text-sm font-medium">
                        {document.file_type === 'pdf' ? 'PDF Preview' : 'Converted PDF Preview'}
                      </h4>
                      <Badge variant="secondary" className="text-xs">
                        Interactive PDF Viewer
                      </Badge>
                    </div>
                    <div className="h-[600px] border rounded-lg overflow-hidden">
                      {pdfUrl ? (
                        <PDFViewer
                          url={pdfUrl}
                          fileName={document.filename}
                          showToolbar={true}
                          initialScale={0.8}
                        />
                      ) : (
                        <div className="flex items-center justify-center h-full">
                          <div className="text-center">
                            <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4" />
                            <p className="text-muted-foreground">Loading PDF...</p>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* PDF Thumbnails (only show as additional content below PDF viewer) */}
                {preview.pdf_available && preview.thumbnails.length > 0 && (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <h4 className="text-sm font-medium">PDF Page Thumbnails</h4>
                      <Badge variant="outline" className="text-xs">
                        {preview.conversion_method}
                      </Badge>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                      {preview.thumbnails.map((thumbnail, index) => (
                        <div key={index} className="space-y-2">
                          <div className="aspect-[3/4] bg-muted rounded-lg overflow-hidden border cursor-pointer hover:bg-muted/80 transition-colors"
                               onClick={() => window.open(thumbnail, '_blank')}>
                            <img
                              src={thumbnail}
                              alt={`Page ${index + 1}`}
                              className="w-full h-full object-contain"
                              onError={(e) => {
                                const target = e.target as HTMLImageElement
                                target.style.display = 'none'
                                const parent = target.parentElement
                                if (parent) {
                                  parent.innerHTML = `
                                    <div class="w-full h-full flex items-center justify-center">
                                      <div class="text-center">
                                        <FileText class="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
                                        <span class="text-xs text-muted-foreground">Page ${index + 1}</span>
                                      </div>
                                    </div>
                                  `
                                }
                              }}
                            />
                          </div>
                          <p className="text-xs text-center text-muted-foreground">
                            Page {index + 1}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Image Preview */}
                {preview.type === 'image_preview' && preview.thumbnail_path && (
                  <div className="space-y-3">
                    <h4 className="text-sm font-medium">Image Preview</h4>
                    <div className="flex justify-center">
                      <div className="max-w-md">
                        <img
                          src={preview.thumbnail_path}
                          alt="Document preview"
                          className="w-full h-auto rounded-lg border"
                        />
                        {preview.original_dimensions && (
                          <p className="text-xs text-center text-muted-foreground mt-2">
                            {preview.original_dimensions[0]} × {preview.original_dimensions[1]} pixels
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                )}

                {/* Text Preview */}
                {preview.text_preview && (
                  <div className="space-y-3">
                    <h4 className="text-sm font-medium">Text Content</h4>
                    <div className="bg-muted/50 rounded-lg p-4">
                      <pre className="text-sm whitespace-pre-wrap font-mono">
                        {preview.text_preview}
                      </pre>
                    </div>
                  </div>
                )}

                {/* Unsupported Format */}
                {preview.type === 'unsupported_fallback' && (
                  <div className="text-center py-8 space-y-4">
                    <AlertCircle className="h-12 w-12 mx-auto text-muted-foreground" />
                    <div className="space-y-2">
                      <h4 className="text-sm font-medium">Preview Not Available</h4>
                      <p className="text-sm text-muted-foreground">
                        {preview.message}
                      </p>
                      {preview.supported_formats && (
                        <div className="text-xs text-muted-foreground">
                          <p>Supported formats:</p>
                          <div className="flex flex-wrap gap-1 justify-center mt-1">
                            {Object.entries(preview.supported_formats).map(([category, formats]) => (
                              <span key={category} className="bg-muted px-2 py-1 rounded">
                                {formats.join(', ')}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Preview Details */}
                {preview && (
                  <Separator />
                )}
                
                {preview && (
                  <div className="space-y-2">
                    <h4 className="text-sm font-medium">Preview Details</h4>
                    <div className="grid grid-cols-2 gap-4 text-xs">
                      <div>
                        <span className="text-muted-foreground">Type:</span>
                        <span className="ml-2">{preview.type}</span>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Method:</span>
                        <span className="ml-2">{preview.conversion_method}</span>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Format:</span>
                        <span className="ml-2">{preview.original_format}</span>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Size:</span>
                        <span className="ml-2">{formatFileSize(preview.file_size)}</span>
                      </div>
                      {preview.pdf_available && (
                        <div>
                          <span className="text-muted-foreground">PDF Available:</span>
                          <span className="ml-2">Yes</span>
                        </div>
                      )}
                      <div>
                        <span className="text-muted-foreground">Cached:</span>
                        <span className="ml-2">{preview.cached ? 'Yes' : 'No'}</span>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </ScrollArea>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
          {document && (
            <Button onClick={handleDownload}>
              <Download className="h-4 w-4 mr-2" />
              Download Original
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}