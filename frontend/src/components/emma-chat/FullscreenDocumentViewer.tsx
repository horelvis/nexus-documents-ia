'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import dynamic from 'next/dynamic'
import { IconX, IconDownload, IconLoader2, IconAlertCircle } from '@tabler/icons-react'
import { Button } from '@/components/ui/button'
import { useDocumentService } from '@/lib/services/document.service'
import type { DocumentInfo } from '@/lib/types/emma'
import { cn } from '@/lib/utils'

const PDFViewer = dynamic(() => import('./PDFViewer'), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-full">
      <IconLoader2 className="h-10 w-10 animate-spin text-muted-foreground" />
    </div>
  ),
})

// ── Source type detection (shared logic) ──

function isPdf(doc: DocumentInfo): boolean {
  const ft = (doc.fileType || '').toLowerCase()
  const name = (doc.name || '').toLowerCase()
  return ft.includes('pdf') || name.endsWith('.pdf')
}

function isImage(doc: DocumentInfo): boolean {
  const ft = (doc.fileType || '').toLowerCase()
  const name = (doc.name || '').toLowerCase()
  return ft.includes('image') || /\.(jpe?g|png|webp|gif|bmp|svg)$/.test(name)
}

// ── Badge config ──

function getBadge(doc: DocumentInfo): { label: string; className: string } {
  const st = (doc.source_type || '').toLowerCase()
  if (st === 'public_knowledge' || st === 'legislation') return { label: 'BOE', className: 'bg-purple-600' }
  if (isPdf(doc)) return { label: 'PDF', className: 'bg-red-600' }
  if (isImage(doc)) return { label: 'IMG', className: 'bg-green-600' }
  return { label: 'DOC', className: 'bg-blue-600' }
}

// ── Component ──

interface FullscreenDocumentViewerProps {
  document: DocumentInfo
  onClose: () => void
}

export function FullscreenDocumentViewer({ document: doc, onClose }: FullscreenDocumentViewerProps) {
  const documentService = useDocumentService()
  const [blobUrl, setBlobUrl] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const blobUrlRef = useRef<string | null>(null)

  const badge = getBadge(doc)
  const docIsPdf = isPdf(doc)
  const docIsImage = isImage(doc)

  // Fetch blob
  useEffect(() => {
    if (blobUrlRef.current) {
      URL.revokeObjectURL(blobUrlRef.current)
      blobUrlRef.current = null
    }

    const fetchBlob = async () => {
      setIsLoading(true)
      setError(null)
      try {
        let documentId = doc.id || null

        if (documentId?.startsWith('gen_')) {
          setError('Documento generado — solo disponible para descarga')
          return
        }

        if (!documentId) {
          const searchResult = await documentService.searchDocuments(doc.name, 1)
          documentId = searchResult.data?.results?.[0]?.id || null
        }

        if (!documentId) {
          setError('Documento no encontrado')
          return
        }

        const result = await documentService.downloadDocument(documentId)
        if ('error' in result) throw new Error(result.error)

        const url = URL.createObjectURL(result.blob)
        blobUrlRef.current = url
        setBlobUrl(url)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Error al cargar el documento')
      } finally {
        setIsLoading(false)
      }
    }

    fetchBlob()

    return () => {
      if (blobUrlRef.current) {
        URL.revokeObjectURL(blobUrlRef.current)
        blobUrlRef.current = null
      }
    }
  }, [doc.id, doc.name, documentService])

  // Escape key closes
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [onClose])

  // Prevent body scroll
  useEffect(() => {
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = '' }
  }, [])

  const handleDownload = useCallback(() => {
    if (!blobUrl) return
    const link = window.document.createElement('a')
    link.href = blobUrl
    link.download = doc.name || 'document'
    window.document.body.appendChild(link)
    link.click()
    window.document.body.removeChild(link)
  }, [blobUrl, doc.name])

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-background/95 backdrop-blur-sm">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-card shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <span className={cn('text-[10px] font-bold px-1.5 py-0.5 rounded tracking-wider text-white shrink-0', badge.className)}>
            {badge.label}
          </span>
          <span className="text-sm font-semibold text-foreground truncate">{doc.name}</span>
          {doc.page && (
            <span className="text-xs text-muted-foreground shrink-0">— Pg. {doc.page}</span>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {blobUrl && (
            <Button variant="outline" size="sm" onClick={handleDownload}>
              <IconDownload className="h-4 w-4 mr-1.5" />
              Descargar
            </Button>
          )}
          <Button variant="destructive" size="sm" onClick={onClose}>
            <IconX className="h-4 w-4 mr-1.5" />
            Cerrar
          </Button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto min-h-0">
        {isLoading && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <IconLoader2 className="h-10 w-10 animate-spin mx-auto mb-3 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">Cargando documento...</p>
            </div>
          </div>
        )}

        {error && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center max-w-md p-6">
              <IconAlertCircle className="h-12 w-12 text-destructive mx-auto mb-3" />
              <h3 className="font-semibold mb-2">Error al cargar</h3>
              <p className="text-sm text-muted-foreground mb-4">{error}</p>
              <Button variant="outline" onClick={onClose}>Cerrar</Button>
            </div>
          </div>
        )}

        {!isLoading && !error && blobUrl && (
          <>
            {docIsPdf && (
              <PDFViewer
                url={blobUrl}
                fileName={doc.name}
                showToolbar={true}
                height="100%"
                className="h-full"
              />
            )}
            {docIsImage && (
              <div className="flex items-center justify-center p-8 h-full">
                <img
                  src={blobUrl}
                  alt={doc.name}
                  className="max-w-full max-h-full object-contain rounded shadow-lg"
                />
              </div>
            )}
            {!docIsPdf && !docIsImage && (
              <div className="flex items-center justify-center h-full p-6">
                <div className="text-center">
                  <p className="text-sm text-muted-foreground mb-4">
                    Vista previa no disponible para este tipo de archivo.
                  </p>
                  <Button variant="outline" onClick={handleDownload}>
                    <IconDownload className="h-4 w-4 mr-2" />
                    Descargar archivo
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
