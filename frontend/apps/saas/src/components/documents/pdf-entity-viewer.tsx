'use client'

import React, { useState, useCallback, useRef, useEffect } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import 'react-pdf/dist/Page/AnnotationLayer.css'
import 'react-pdf/dist/Page/TextLayer.css'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { Card } from '@/components/ui/card'
import {
  ChevronLeft,
  ChevronRight,
  ZoomIn,
  ZoomOut,
  RotateCw,
  Download,
  Maximize2,
  Loader2
} from 'lucide-react'
import { cn } from '@/lib/utils'

pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`

// CSS para resaltado de texto en el PDF
const highlightStyles = `
  .pdf-entity-viewer .react-pdf__Page__textContent span.entity-highlight {
    background-color: rgba(59, 130, 246, 0.3) !important;
    border-radius: 2px;
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.5);
    animation: pulse-highlight 1.5s ease-in-out;
  }

  .pdf-entity-viewer .react-pdf__Page__textContent span.entity-highlight-active {
    background-color: rgba(234, 179, 8, 0.4) !important;
    box-shadow: 0 0 0 3px rgba(234, 179, 8, 0.6);
  }

  @keyframes pulse-highlight {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.6; }
  }
`

export interface DocumentEntity {
  id?: string
  class: string
  text: string
  attributes?: Record<string, any>
  source_indices?: [number, number] | null
  page?: number
}

interface PDFEntityViewerProps {
  url: string
  fileName?: string
  focusedEntity?: DocumentEntity | null
  className?: string
  showToolbar?: boolean
  initialScale?: number
  height?: string | number
}

export default function PDFEntityViewer({
  url,
  fileName = 'document.pdf',
  focusedEntity,
  className,
  showToolbar = true,
  initialScale = 1.0,
  height = '700px'
}: PDFEntityViewerProps) {
  const [numPages, setNumPages] = useState<number>(0)
  const [pageNumber, setPageNumber] = useState<number>(1)
  const [scale, setScale] = useState<number>(initialScale)
  const [rotation, setRotation] = useState<number>(0)
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // Inject highlight styles once
  useEffect(() => {
    const styleId = 'pdf-entity-highlight-styles'
    if (!document.getElementById(styleId)) {
      const style = document.createElement('style')
      style.id = styleId
      style.textContent = highlightStyles
      document.head.appendChild(style)
    }
  }, [])

  // Highlight helper
  const highlightTextInPdf = useCallback((searchText: string, isActive: boolean = true) => {
    if (!containerRef.current || !searchText) return 0

    const existingHighlights = containerRef.current.querySelectorAll('.entity-highlight, .entity-highlight-active')
    existingHighlights.forEach(el => el.classList.remove('entity-highlight', 'entity-highlight-active'))

    const textLayer = containerRef.current.querySelector('.react-pdf__Page__textContent')
    if (!textLayer) return 0

    const spans = textLayer.querySelectorAll('span')
    const searchLower = searchText.toLowerCase().trim()
    const searchWords = searchLower.split(/\s+/)
    let matchCount = 0
    let firstMatch: Element | null = null

    spans.forEach((span) => {
      const text = span.textContent?.toLowerCase() || ''
      const matches = searchWords.some(word => word.length > 2 && text.includes(word)) || text.includes(searchLower)

      if (matches) {
        span.classList.add(isActive ? 'entity-highlight-active' : 'entity-highlight')
        matchCount++
        if (!firstMatch) firstMatch = span
      }
    })

    if (firstMatch) {
      firstMatch.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }

    return matchCount
  }, [])

  const resolvedHeight = typeof height === 'number' ? `${height}px` : height

  const onDocumentLoadSuccess = useCallback(({ numPages }: { numPages: number }) => {
    setNumPages(numPages)
    setIsLoading(false)
    setError(null)
  }, [])

  const onDocumentLoadError = useCallback((loadError: Error) => {
    console.error('Error loading PDF:', loadError)
    setError('Error loading PDF document')
    setIsLoading(false)
  }, [])

  const goToPrevPage = useCallback(() => setPageNumber(prev => Math.max(1, prev - 1)), [])
  const goToNextPage = useCallback(() => setPageNumber(prev => Math.min(numPages || 1, prev + 1)), [numPages])
  const goToPage = useCallback((page: number) => {
    if (page >= 1 && (numPages === 0 || page <= numPages)) {
      setPageNumber(page)
    }
  }, [numPages])

  const zoomIn = useCallback(() => setScale(prev => Math.min(3.0, prev + 0.2)), [])
  const zoomOut = useCallback(() => setScale(prev => Math.max(0.5, prev - 0.2)), [])
  const resetZoom = useCallback(() => setScale(1.0), [])
  const rotate = useCallback(() => setRotation(prev => (prev + 90) % 360), [])

  const downloadPDF = useCallback(() => {
    const link = document.createElement('a')
    link.href = url
    link.download = fileName
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }, [url, fileName])

  const openFullscreen = useCallback(() => window.open(url, '_blank'), [url])

  useEffect(() => {
    if (!focusedEntity || isLoading) return

    const timeout = setTimeout(() => {
      highlightTextInPdf(focusedEntity.text, true)
    }, 150)

    return () => clearTimeout(timeout)
  }, [focusedEntity, highlightTextInPdf, isLoading])

  if (error) {
    return (
      <Card className={cn('h-full flex items-center justify-center p-6', className)}>
        <div className="text-center">
          <p className="text-red-500 mb-4">Error loading PDF</p>
          <Button onClick={() => window.location.reload()} variant="outline">
            Try Again
          </Button>
        </div>
      </Card>
    )
  }

  const totalPagesLabel = numPages > 0 ? numPages : '—'
  const currentPageLabel = numPages > 0 ? Math.min(pageNumber, numPages) : pageNumber

  return (
    <div
      ref={containerRef}
      className={cn('pdf-entity-viewer flex flex-col bg-background border rounded-lg overflow-hidden', className)}
      style={{ height: resolvedHeight }}
    >
      {showToolbar && (
        <div className="flex items-center justify-between p-3 border-b bg-muted/30">
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={goToPrevPage} disabled={pageNumber <= 1}>
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <div className="flex items-center gap-1">
              <Input
                type="number"
                value={pageNumber}
                onChange={(e) => goToPage(parseInt(e.target.value) || 1)}
                className="w-14 h-8 text-center text-sm"
                min={1}
                max={Math.max(numPages, 1)}
              />
              <span className="text-sm text-muted-foreground">/ {totalPagesLabel}</span>
            </div>
            <Button variant="outline" size="sm" onClick={goToNextPage} disabled={numPages !== 0 && pageNumber >= numPages}>
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>

          <div className="flex items-center gap-1">
            <Button variant="outline" size="sm" onClick={zoomOut} disabled={scale <= 0.5}>
              <ZoomOut className="h-4 w-4" />
            </Button>
            <Badge variant="secondary" className="cursor-pointer px-2 h-8" onClick={resetZoom}>
              {Math.round(scale * 100)}%
            </Badge>
            <Button variant="outline" size="sm" onClick={zoomIn} disabled={scale >= 3.0}>
              <ZoomIn className="h-4 w-4" />
            </Button>
            <Separator orientation="vertical" className="h-6 mx-1" />
            <Button variant="outline" size="sm" onClick={rotate}>
              <RotateCw className="h-4 w-4" />
            </Button>
            <Button variant="outline" size="sm" onClick={downloadPDF}>
              <Download className="h-4 w-4" />
            </Button>
            <Button variant="outline" size="sm" onClick={openFullscreen}>
              <Maximize2 className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}

      <div className="flex-1 overflow-auto bg-muted/50 flex justify-center p-4">
        {isLoading && (
          <div className="flex items-center justify-center h-full text-muted-foreground">
            <Loader2 className="h-8 w-8 animate-spin" />
            <span className="ml-2 text-sm">Loading PDF...</span>
          </div>
        )}

        <div className="relative">
          <Document
            file={url}
            onLoadSuccess={onDocumentLoadSuccess}
            onLoadError={onDocumentLoadError}
            loading={null}
          >
            <Page
              pageNumber={pageNumber}
              scale={scale}
              rotate={rotation}
              className="shadow-lg"
              loading={
                <div className="flex items-center justify-center h-96 bg-white border">
                  <Loader2 className="h-6 w-6 animate-spin" />
                </div>
              }
            />
          </Document>
        </div>
      </div>

      {showToolbar && (
        <div className="flex items-center justify-between px-3 py-1.5 border-t bg-muted/30 text-xs text-muted-foreground">
          <span className="truncate">{fileName}</span>
          <span>
            Página {currentPageLabel} de {totalPagesLabel}
          </span>
        </div>
      )}
    </div>
  )
}
