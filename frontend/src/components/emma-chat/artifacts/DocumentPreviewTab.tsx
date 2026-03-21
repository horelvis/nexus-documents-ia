'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import dynamic from 'next/dynamic'
import { Button } from '@/components/ui/button'
import {
  IconLoader2,
  IconDownload,
  IconAlertCircle,
  IconEye,
} from '@tabler/icons-react'
import { useDocumentService } from '@/lib/services/document.service'
import { DocumentInfo } from '@/lib/types/emma'

// Lazy load PDFViewer to avoid SSR issues
const PDFViewer = dynamic(
  () => import('../PDFViewer'),
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

interface DocumentPreviewTabProps {
  document: DocumentInfo
  onClose?: () => void
}

export function DocumentPreviewTab({ document, onClose }: DocumentPreviewTabProps) {
  const documentService = useDocumentService()
  const [blobUrl, setBlobUrl] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const blobUrlRef = useRef<string | null>(null)

  // Cleanup blob URL when component unmounts
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
    // Cleanup previous blob URL
    if (blobUrlRef.current) {
      URL.revokeObjectURL(blobUrlRef.current)
      blobUrlRef.current = null
    }
    setBlobUrl(null)
    setError(null)

    const fetchPdfAsBlob = async () => {
      setIsLoading(true)
      setError(null)

      try {
        let documentId: string | null = document.id || null

        // Generated documents (gen_*) are DOCX stored in Redis on emma-agent-service.
        // They can't be previewed as PDF — offer download instead.
        if (documentId && documentId.startsWith('gen_')) {
          setError('Este documento generado solo está disponible para descarga en formato DOCX.')
          return
        }

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
  }, [document, documentService])

  const handleDownload = useCallback(() => {
    if (!blobUrl) return

    const link = window.document.createElement('a')
    link.href = blobUrl
    link.download = document.name || 'document.pdf'
    window.document.body.appendChild(link)
    link.click()
    window.document.body.removeChild(link)
  }, [blobUrl, document])

  // Detect if document is a PDF
  const fileTypeLower = document.fileType?.toLowerCase() || ''
  const nameLower = document.name?.toLowerCase() || ''
  const isPdf = fileTypeLower === 'pdf' ||
    fileTypeLower === 'application/pdf' ||
    fileTypeLower.includes('pdf') ||
    nameLower.endsWith('.pdf') ||
    document.previewUrl?.toLowerCase().includes('.pdf')

  return (
    <div className="flex flex-col h-full">
      {/* Document name header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border shrink-0 bg-muted/30">
        <span className="text-xs font-medium text-foreground truncate" title={document.name}>
          {document.name}
        </span>
        {blobUrl && (
          <Button variant="ghost" size="icon" className="h-6 w-6 shrink-0" onClick={handleDownload}>
            <IconDownload className="h-3.5 w-3.5" />
            <span className="sr-only">Descargar</span>
          </Button>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden bg-muted/30 min-h-0">
        {isLoading && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <IconLoader2 className="h-10 w-10 animate-spin mx-auto mb-4 text-primary" />
              <p className="text-sm text-muted-foreground">Cargando documento...</p>
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
              {onClose && (
                <Button variant="outline" onClick={onClose}>
                  Cerrar
                </Button>
              )}
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
    </div>
  )
}
