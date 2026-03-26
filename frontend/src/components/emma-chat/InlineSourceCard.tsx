'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import dynamic from 'next/dynamic'
import { IconLoader2, IconExternalLink, IconMaximize } from '@tabler/icons-react'
import { Button } from '@/components/ui/button'
import { useDocumentService } from '@/lib/services/document.service'
import type { DocumentInfo } from '@/lib/types/emma'
import { cn } from '@/lib/utils'
import { EmmaMarkdown } from './EmmaMarkdown'

// Lazy-load the PDF viewer in compact mode (avoid SSR issues with react-pdf)
const PDFViewer = dynamic(() => import('./PDFViewer'), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center w-full py-16">
      <IconLoader2 className="h-6 w-6 animate-spin text-muted-foreground" />
    </div>
  ),
})

// ── Source type detection ──

type SourceType = 'pdf' | 'image' | 'boe' | 'markdown' | 'doc' | 'text'

function detectSourceType(doc: DocumentInfo): SourceType {
  const ft = (doc.fileType || '').toLowerCase()
  const name = (doc.name || '').toLowerCase()
  const st = (doc.source_type || '').toLowerCase()

  if (st === 'public_knowledge' || st === 'legislation') return 'boe'
  if (ft.includes('pdf') || name.endsWith('.pdf')) return 'pdf'
  if (
    ft.includes('image') ||
    /\.(jpe?g|png|webp|gif|bmp|svg)$/.test(name)
  ) return 'image'
  if (ft === 'md' || ft.includes('markdown') || /\.(md|mdx|markdown)$/.test(name)) return 'markdown'
  if (
    ft.includes('word') || ft.includes('officedocument') || ft.includes('msword') ||
    /\.(docx?|odt|rtf)$/.test(name)
  ) return 'doc'
  return 'text'
}

const TYPE_CONFIG: Record<SourceType, { badge: string; color: string; bgColor: string; borderColor: string }> = {
  pdf:      { badge: 'PDF', color: 'text-white', bgColor: 'bg-red-600',    borderColor: 'border-red-600' },
  image:    { badge: 'IMG', color: 'text-white', bgColor: 'bg-green-600',  borderColor: 'border-green-600' },
  boe:      { badge: 'BOE', color: 'text-white', bgColor: 'bg-purple-600', borderColor: 'border-purple-600' },
  markdown: { badge: 'MD',  color: 'text-white', bgColor: 'bg-amber-600',  borderColor: 'border-amber-600' },
  doc:      { badge: 'DOC', color: 'text-white', bgColor: 'bg-blue-600',   borderColor: 'border-blue-600' },
  text:     { badge: 'TXT', color: 'text-white', bgColor: 'bg-slate-600',  borderColor: 'border-slate-600' },
}

// ── Blob fetching hook ──

function useBlobUrl(doc: DocumentInfo, shouldFetch: boolean) {
  const documentService = useDocumentService()
  const [blobUrl, setBlobUrl] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const blobUrlRef = useRef<string | null>(null)

  useEffect(() => {
    if (!shouldFetch) return

    if (blobUrlRef.current) {
      URL.revokeObjectURL(blobUrlRef.current)
      blobUrlRef.current = null
    }
    setBlobUrl(null)
    setError(null)

    const fetchBlob = async () => {
      setIsLoading(true)
      try {
        let documentId = doc.id || null

        if (documentId?.startsWith('gen_')) {
          setError('Documento generado — solo descarga disponible')
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
        setError(err instanceof Error ? err.message : 'Error al cargar')
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
  }, [doc.id, doc.name, shouldFetch, documentService])

  return { blobUrl, isLoading, error }
}

// ── Markdown text fetching hook ──

function useMarkdownText(doc: DocumentInfo, shouldFetch: boolean) {
  const documentService = useDocumentService()
  const [text, setText] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!shouldFetch) return
    setText(null)
    setError(null)

    const fetchText = async () => {
      setIsLoading(true)
      try {
        let documentId = doc.id || null
        if (!documentId) {
          const searchResult = await documentService.searchDocuments(doc.name, 1)
          documentId = searchResult.data?.results?.[0]?.id || null
        }
        if (!documentId) { setError('Documento no encontrado'); return }

        const result = await documentService.downloadDocument(documentId)
        if ('error' in result) throw new Error(result.error)

        const content = await result.blob.text()
        setText(content)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Error al cargar')
      } finally {
        setIsLoading(false)
      }
    }

    fetchText()
  }, [doc.id, doc.name, shouldFetch, documentService])

  return { text, isLoading, error }
}

// ── Main component ──

interface InlineSourceCardProps {
  document: DocumentInfo
  onOpenFullscreen?: (doc: DocumentInfo) => void
  className?: string
}

export function InlineSourceCard({ document: doc, onOpenFullscreen, className }: InlineSourceCardProps) {
  const sourceType = detectSourceType(doc)
  const config = TYPE_CONFIG[sourceType]
  const needsBlob = sourceType === 'pdf' || sourceType === 'image'
  const { blobUrl, isLoading, error } = useBlobUrl(doc, needsBlob)
  const { text: mdText, isLoading: mdLoading, error: mdError } = useMarkdownText(doc, sourceType === 'markdown')

  const pageLabel = doc.page ? `— Pg. ${doc.page}` : ''
  const actionLabel = sourceType === 'pdf' ? 'Abrir PDF'
    : sourceType === 'image' ? 'Abrir imagen'
    : sourceType === 'boe' ? 'Ver en BOE'
    : sourceType === 'markdown' ? 'Abrir markdown'
    : sourceType === 'doc' ? 'Abrir documento'
    : 'Descargar'

  const handleAction = () => {
    if (sourceType === 'boe' && doc.url) {
      window.open(doc.url, '_blank', 'noopener')
    } else if (onOpenFullscreen) {
      onOpenFullscreen(doc)
    }
  }

  return (
    <div className={cn('border border-border rounded-lg overflow-hidden bg-card', className)}>
      {/* Header bar */}
      <div className="flex items-center justify-between px-3 py-2.5 border-b border-border bg-muted/40">
        <div className="flex items-center gap-2 min-w-0">
          <span className={cn('text-[10px] font-bold px-1.5 py-0.5 rounded tracking-wider shrink-0', config.bgColor, config.color)}>
            {config.badge}
          </span>
          <span className="text-sm font-semibold text-foreground truncate">{doc.name}</span>
          {pageLabel && <span className="text-xs text-muted-foreground shrink-0">{pageLabel}</span>}
        </div>
        <Button
          variant="outline"
          size="sm"
          className="h-7 text-xs shrink-0 ml-2"
          onClick={handleAction}
        >
          {sourceType === 'boe' ? (
            <IconExternalLink className="h-3 w-3 mr-1" />
          ) : (
            <IconMaximize className="h-3 w-3 mr-1" />
          )}
          {actionLabel}
        </Button>
      </div>

      {/* Content — type-specific */}
      {sourceType === 'pdf' && (
        <div className="bg-muted/30 p-3">
          {isLoading && (
            <div className="flex items-center justify-center w-full py-16">
              <div className="text-center">
                <IconLoader2 className="h-8 w-8 animate-spin mx-auto mb-2 text-muted-foreground" />
                <p className="text-xs text-muted-foreground">Cargando documento...</p>
              </div>
            </div>
          )}
          {error && (
            <div className="flex items-center justify-center w-full py-8">
              <p className="text-xs text-muted-foreground">{error}</p>
            </div>
          )}
          {!isLoading && !error && blobUrl && (
            <PDFViewer url={blobUrl} compact pageNumber={doc.page || 1} />
          )}
        </div>
      )}

      {sourceType === 'image' && (
        <div className="bg-muted/30 p-3 flex justify-center">
          {isLoading && (
            <div className="flex items-center justify-center w-full py-12">
              <IconLoader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          )}
          {error && (
            <div className="flex items-center justify-center w-full py-8">
              <p className="text-xs text-muted-foreground">{error}</p>
            </div>
          )}
          {!isLoading && !error && blobUrl && (
            <img
              src={blobUrl}
              alt={doc.name}
              className="max-w-full rounded border border-border shadow-sm"
              loading="lazy"
            />
          )}
        </div>
      )}

      {sourceType === 'markdown' && (
        <div className="bg-muted/30 p-3 flex justify-center">
          {mdLoading && (
            <div className="flex items-center justify-center w-full py-12">
              <div className="text-center">
                <IconLoader2 className="h-6 w-6 animate-spin mx-auto mb-2 text-muted-foreground" />
                <p className="text-xs text-muted-foreground">Cargando documento...</p>
              </div>
            </div>
          )}
          {mdError && (
            <div className="flex items-center justify-center w-full py-4">
              <p className="text-xs text-muted-foreground">{mdError}</p>
            </div>
          )}
          {!mdLoading && !mdError && mdText != null && (
            <div className="relative overflow-hidden bg-white shadow-lg border border-neutral-200/60 w-full max-w-[500px] max-h-[250px]">
              <div className="origin-top-left scale-[0.55] w-[182%] px-12 py-8">
                <EmmaMarkdown content={mdText} forceLight />
              </div>
              <div className="absolute inset-x-0 bottom-0 h-12 bg-gradient-to-t from-white to-transparent pointer-events-none" />
            </div>
          )}
        </div>
      )}

      {(sourceType === 'doc' || sourceType === 'text' || sourceType === 'boe') && doc.excerpt && (
        <div className="px-4 py-3">
          <div className={cn('border-l-[3px] pl-3 text-sm text-muted-foreground italic leading-relaxed', config.borderColor)}>
            &ldquo;{doc.excerpt}&rdquo;
          </div>
        </div>
      )}
    </div>
  )
}
