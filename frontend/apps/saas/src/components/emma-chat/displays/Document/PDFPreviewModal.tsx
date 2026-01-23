'use client'

import { useCallback, useState, useEffect } from 'react'
import dynamic from 'next/dynamic'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  X,
  Loader2,
  Download,
  ExternalLink,
  FileText,
  AlertCircle,
  Eye,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useDocumentService } from '@/lib/services/document.service'
import { DocumentInfo } from '../../types'

// Lazy load PDFViewer to avoid SSR issues
const PDFViewer = dynamic(
  () => import('./PDFViewer'),
  {
    ssr: false,
    loading: () => (
      <div className="flex items-center justify-center h-96 bg-muted/30 rounded-lg">
        <div className="text-center">
          <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4 text-primary" />
          <p className="text-sm text-muted-foreground">Cargando visor PDF...</p>
        </div>
      </div>
    ),
  }
)

// PreviewDocument interface for internal use
export interface PreviewDocument {
  name: string
  id?: string
  url?: string
  previewUrl?: string
  fileType?: string
  relevanceScore?: number
}

interface PDFPreviewModalProps {
  document: PreviewDocument | null
  open: boolean
  onOpenChange: (open: boolean) => void
  tenantId?: string
}

export function PDFPreviewModal({
  document,
  open,
  onOpenChange,
  tenantId,
}: PDFPreviewModalProps) {
  const documentService = useDocumentService()
  const [pdfUrl, setPdfUrl] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Resolve the PDF URL when document changes
  useEffect(() => {
    if (!document || !open) {
      setPdfUrl(null)
      setError(null)
      return
    }

    const resolvePdfUrl = async () => {
      setIsLoading(true)
      setError(null)

      try {
        // If we already have a preview URL, use it
        if (document.previewUrl) {
          setPdfUrl(document.previewUrl)
          setIsLoading(false)
          return
        }

        // If we have a direct URL, use it
        if (document.url) {
          setPdfUrl(document.url)
          setIsLoading(false)
          return
        }

        // If we have a document ID, use the stream URL
        if (document.id) {
          const streamUrl = documentService.getDocumentStreamUrl(document.id)
          setPdfUrl(streamUrl)
        } else {
          // Try to search by name to get the ID
          const searchResult = await documentService.searchDocuments(document.name, 1)
          if (searchResult.data?.results?.[0]?.id) {
            const streamUrl = documentService.getDocumentStreamUrl(searchResult.data.results[0].id)
            setPdfUrl(streamUrl)
          } else {
            setError('No se encontro el documento')
          }
        }
      } catch (err) {
        console.error('Error resolving PDF URL:', err)
        setError(err instanceof Error ? err.message : 'Error al cargar el documento')
      } finally {
        setIsLoading(false)
      }
    }

    resolvePdfUrl()
  }, [document, open, documentService])

  const handleClose = useCallback(() => {
    onOpenChange(false)
  }, [onOpenChange])

  const handleOpenExternal = useCallback(() => {
    if (pdfUrl) {
      window.open(pdfUrl, '_blank')
    }
  }, [pdfUrl])

  const handleDownload = useCallback(() => {
    if (!pdfUrl || !document) return

    const link = window.document.createElement('a')
    link.href = pdfUrl
    link.download = document.name || 'document.pdf'
    window.document.body.appendChild(link)
    link.click()
    window.document.body.removeChild(link)
  }, [pdfUrl, document])

  const isPdf = document?.fileType?.toLowerCase() === 'pdf' ||
    document?.name?.toLowerCase().endsWith('.pdf') ||
    document?.previewUrl?.toLowerCase().includes('.pdf')

  if (!document) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl w-[95vw] h-[90vh] flex flex-col p-0 gap-0">
        {/* Header */}
        <DialogHeader className="flex-shrink-0 px-4 py-3 border-b bg-card">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3 min-w-0">
              <div className="flex items-center justify-center h-10 w-10 rounded-lg bg-primary/10">
                <FileText className="h-5 w-5 text-primary" />
              </div>
              <div className="min-w-0">
                <DialogTitle className="text-base font-semibold truncate">
                  {document.name}
                </DialogTitle>
                <div className="flex items-center gap-2 mt-0.5">
                  {document.fileType && (
                    <Badge variant="secondary" className="text-xs">
                      {document.fileType.toUpperCase()}
                    </Badge>
                  )}
                  {document.relevanceScore && (
                    <Badge variant="outline" className="text-xs">
                      {Math.round(document.relevanceScore * 100)}% relevancia
                    </Badge>
                  )}
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2">
              {pdfUrl && (
                <>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleDownload}
                    className="hidden sm:flex"
                  >
                    <Download className="h-4 w-4 mr-2" />
                    Descargar
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleOpenExternal}
                  >
                    <ExternalLink className="h-4 w-4 mr-2" />
                    <span className="hidden sm:inline">Abrir completo</span>
                  </Button>
                </>
              )}
              <Button
                variant="ghost"
                size="icon"
                onClick={handleClose}
                className="h-8 w-8"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </DialogHeader>

        {/* Content */}
        <div className="flex-1 overflow-hidden bg-muted/30">
          {isLoading && (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <Loader2 className="h-10 w-10 animate-spin mx-auto mb-4 text-primary" />
                <p className="text-muted-foreground">Cargando documento...</p>
              </div>
            </div>
          )}

          {error && (
            <div className="flex items-center justify-center h-full">
              <div className="text-center max-w-md mx-auto p-6">
                <div className="flex items-center justify-center h-16 w-16 rounded-full bg-destructive/10 mx-auto mb-4">
                  <AlertCircle className="h-8 w-8 text-destructive" />
                </div>
                <h3 className="font-semibold mb-2">Error al cargar documento</h3>
                <p className="text-sm text-muted-foreground mb-4">{error}</p>
                <Button variant="outline" onClick={handleClose}>
                  Cerrar
                </Button>
              </div>
            </div>
          )}

          {!isLoading && !error && pdfUrl && (
            <>
              {isPdf ? (
                <PDFViewer
                  url={pdfUrl}
                  fileName={document.name}
                  height="100%"
                  showToolbar={true}
                  className="h-full"
                />
              ) : (
                // For non-PDF files, show a message
                <div className="flex flex-col items-center justify-center h-full p-6">
                  <div className="flex items-center justify-center h-20 w-20 rounded-full bg-muted mb-4">
                    <Eye className="h-10 w-10 text-muted-foreground" />
                  </div>
                  <h3 className="font-semibold mb-2">Vista previa no disponible</h3>
                  <p className="text-sm text-muted-foreground text-center mb-4">
                    La vista previa en linea solo esta disponible para archivos PDF.
                  </p>
                  <div className="flex gap-2">
                    <Button variant="outline" onClick={handleDownload}>
                      <Download className="h-4 w-4 mr-2" />
                      Descargar archivo
                    </Button>
                    <Button onClick={handleOpenExternal}>
                      <ExternalLink className="h-4 w-4 mr-2" />
                      Abrir en nueva pestana
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
