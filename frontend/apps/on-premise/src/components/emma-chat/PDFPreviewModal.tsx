'use client'

import { useCallback, useState, useEffect, useRef } from 'react'
import dynamic from 'next/dynamic'
import {
  Dialog,
  DialogContent,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import {
  IconX,
  IconLoader2,
  IconDownload,
  IconAlertCircle,
  IconEye,
} from '@tabler/icons-react'
import { useDocumentService } from '@/lib/services/document.service'
import { DocumentInfo } from '@/lib/types/emma'

// Lazy load PDFViewer to avoid SSR issues
const PDFViewer = dynamic(
  () => import('./PDFViewer'),
  {
    ssr: false,
    loading: () => (
      <div className="flex items-center justify-center h-96 bg-muted/30 rounded-lg">
        <div className="text-center">
          <IconLoader2 className="h-8 w-8 animate-spin mx-auto mb-4 text-primary" />
          <p className="text-sm text-muted-foreground">Cargando visor PDF...</p>
        </div>
      </div>
    ),
  }
)

interface PDFPreviewModalProps {
  document: DocumentInfo | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function PDFPreviewModal({
  document,
  open,
  onOpenChange,
}: PDFPreviewModalProps) {
  const documentService = useDocumentService()
  const [blobUrl, setBlobUrl] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const blobUrlRef = useRef<string | null>(null)

  // Cleanup blob URL when component unmounts or modal closes
  useEffect(() => {
    return () => {
      if (blobUrlRef.current) {
        URL.revokeObjectURL(blobUrlRef.current)
        blobUrlRef.current = null
      }
    }
  }, [])

  // Fetch PDF as blob with authentication when document changes
  useEffect(() => {
    if (!document || !open) {
      // Cleanup previous blob URL
      if (blobUrlRef.current) {
        URL.revokeObjectURL(blobUrlRef.current)
        blobUrlRef.current = null
      }
      setBlobUrl(null)
      setError(null)
      return
    }

    const fetchPdfAsBlob = async () => {
      setIsLoading(true)
      setError(null)

      try {
        let documentId: string | null = document.id || null

        // If no document ID, try to search by name
        if (!documentId) {
          const searchResult = await documentService.searchDocuments(document.name, 1)
          documentId = searchResult.data?.results?.[0]?.id || null
        }

        if (!documentId) {
          setError('No se encontró el documento')
          return
        }

        // Use document service to download blob (goes through proxy, avoids CORS)
        const result = await documentService.downloadDocument(documentId)

        if ('error' in result) {
          throw new Error(result.error)
        }

        // Create blob URL
        const url = URL.createObjectURL(result.blob)

        // Store for cleanup
        blobUrlRef.current = url
        setBlobUrl(url)
      } catch (err) {
        console.error('Error fetching PDF:', err)
        setError(err instanceof Error ? err.message : 'Error al cargar el documento')
      } finally {
        setIsLoading(false)
      }
    }

    fetchPdfAsBlob()
  }, [document, open, documentService])

  const handleClose = useCallback(() => {
    onOpenChange(false)
  }, [onOpenChange])

  const handleDownload = useCallback(() => {
    if (!blobUrl || !document) return

    const link = window.document.createElement('a')
    link.href = blobUrl
    link.download = document.name || 'document.pdf'
    window.document.body.appendChild(link)
    link.click()
    window.document.body.removeChild(link)
  }, [blobUrl, document])

  // Detect if document is a PDF (check MIME type, extension, or file type string)
  const fileTypeLower = document?.fileType?.toLowerCase() || ''
  const nameLower = document?.name?.toLowerCase() || ''
  const isPdf = fileTypeLower === 'pdf' ||
    fileTypeLower === 'application/pdf' ||
    fileTypeLower.includes('pdf') ||
    nameLower.endsWith('.pdf') ||
    document?.previewUrl?.toLowerCase().includes('.pdf')

  if (!document) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl w-[95vw] h-[90vh] flex flex-col p-0 gap-0">
        {/* Close button - positioned over PDFViewer toolbar */}
        <Button
          variant="ghost"
          size="icon"
          onClick={handleClose}
          className="absolute right-2 top-2 z-50 h-8 w-8 bg-background/80 backdrop-blur-sm hover:bg-background"
        >
          <IconX className="h-4 w-4" />
          <span className="sr-only">Cerrar</span>
        </Button>

        {/* Content */}
        <div className="flex-1 overflow-hidden bg-muted/30">
          {isLoading && (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <IconLoader2 className="h-10 w-10 animate-spin mx-auto mb-4 text-primary" />
                <p className="text-muted-foreground">Cargando documento...</p>
              </div>
            </div>
          )}

          {error && (
            <div className="flex items-center justify-center h-full">
              <div className="text-center max-w-md mx-auto p-6">
                <div className="flex items-center justify-center h-16 w-16 rounded-full bg-destructive/10 mx-auto mb-4">
                  <IconAlertCircle className="h-8 w-8 text-destructive" />
                </div>
                <h3 className="font-semibold mb-2">Error al cargar documento</h3>
                <p className="text-sm text-muted-foreground mb-4">{error}</p>
                <Button variant="outline" onClick={handleClose}>
                  Cerrar
                </Button>
              </div>
            </div>
          )}

          {!isLoading && !error && blobUrl && (
            <>
              {isPdf ? (
                <PDFViewer
                  url={blobUrl}
                  fileName={document.name}
                  height="100%"
                  showToolbar={true}
                  className="h-full"
                />
              ) : (
                // For non-PDF files, show a message
                <div className="flex flex-col items-center justify-center h-full p-6">
                  <div className="flex items-center justify-center h-20 w-20 rounded-full bg-muted mb-4">
                    <IconEye className="h-10 w-10 text-muted-foreground" />
                  </div>
                  <h3 className="font-semibold mb-2">Vista previa no disponible</h3>
                  <p className="text-sm text-muted-foreground text-center mb-4">
                    La vista previa en línea solo está disponible para archivos PDF.
                  </p>
                  <Button variant="outline" onClick={handleDownload}>
                    <IconDownload className="h-4 w-4 mr-2" />
                    Descargar archivo
                  </Button>
                </div>
              )}
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
