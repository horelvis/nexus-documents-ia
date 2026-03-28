'use client'

import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { Document, Page as RawPage, pdfjs } from 'react-pdf'

// Cast to any — react-pdf PageProps has a known type conflict with React 18
const Page = RawPage as any
import 'react-pdf/dist/Page/AnnotationLayer.css'
import 'react-pdf/dist/Page/TextLayer.css'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { Card } from '@/components/ui/card'
import {
  IconChevronLeft,
  IconChevronRight,
  IconZoomIn,
  IconZoomOut,
  IconRotateClockwise,
  IconDownload,
  IconMaximize,
  IconLoader2,
} from '@tabler/icons-react'
import { cn } from '@/lib/utils'

// Configure PDF.js worker from CDN (matches react-pdf version)
pdfjs.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`

const DOC_OPTIONS = {
  cMapUrl: `https://unpkg.com/pdfjs-dist@${pdfjs.version}/cmaps/`,
  cMapPacked: true,
}

interface PDFViewerProps {
  url: string
  fileName?: string
  className?: string
  /** Compact mode: single page, auto-width, no toolbar (for inline source cards) */
  compact?: boolean
  /** Initial page to display (compact mode stays on this page) */
  pageNumber?: number
  showToolbar?: boolean
  initialScale?: number
  height?: string | number
}

export default function PDFViewer({
  url,
  fileName = 'document.pdf',
  className,
  compact = false,
  pageNumber: initialPage = 1,
  showToolbar = true,
  initialScale = 1.0,
  height = '600px',
}: PDFViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [containerWidth, setContainerWidth] = useState<number>(0)
  const [numPages, setNumPages] = useState<number>(0)
  const [pageNumber, setPageNumber] = useState<number>(initialPage)
  const [scale, setScale] = useState<number>(initialScale)
  const [rotation, setRotation] = useState<number>(0)
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)
  const [docLoaded, setDocLoaded] = useState(false)

  // In compact mode, auto-measure container width
  useEffect(() => {
    if (!compact) return
    const el = containerRef.current
    if (!el) return

    const measure = () => setContainerWidth(Math.min(el.clientWidth, 500))
    measure()

    const observer = new ResizeObserver(measure)
    observer.observe(el)
    return () => observer.disconnect()
  }, [compact])

  // Reset state when URL changes
  useEffect(() => {
    setDocLoaded(false)
    setError(null)
    setIsLoading(true)
    setPageNumber(initialPage)
  }, [url, initialPage])

  const fileSource = useMemo(() => url, [url])

  const onDocumentLoadSuccess = useCallback((pdf: any) => {
    setNumPages(pdf.numPages)
    setDocLoaded(true)
    setIsLoading(false)
    setError(null)
  }, [])

  const onDocumentLoadError = useCallback((err: Error) => {
    console.error('PDFViewer load error:', err)
    setError('Error al cargar el PDF')
    setIsLoading(false)
  }, [])

  const onPageLoadError = useCallback((err: Error) => {
    // Suppress WorkerTransport null errors (race condition on unmount)
    if (err?.message?.includes('sendWithPromise') || err?.message?.includes('null')) {
      console.warn('PDFViewer: PDF worker transport destroyed (unmount race), suppressed')
      return
    }
    console.error('PDFViewer page error:', err)
    setError('Error al renderizar la página')
  }, [])

  // Navigation
  const goToPrevPage = useCallback(() => {
    setPageNumber((prev) => Math.max(1, prev - 1))
  }, [])

  const goToNextPage = useCallback(() => {
    setPageNumber((prev) => Math.min(numPages, prev + 1))
  }, [numPages])

  const goToPage = useCallback(
    (page: number) => {
      if (page >= 1 && page <= numPages) setPageNumber(page)
    },
    [numPages]
  )

  // Zoom / rotate
  const zoomIn = useCallback(() => setScale((prev) => Math.min(3.0, prev + 0.2)), [])
  const zoomOut = useCallback(() => setScale((prev) => Math.max(0.5, prev - 0.2)), [])
  const resetZoom = useCallback(() => setScale(1.0), [])
  const rotate = useCallback(() => setRotation((prev) => (prev + 90) % 360), [])

  const downloadPDF = useCallback(() => {
    const link = document.createElement('a')
    link.href = url
    link.download = fileName
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }, [url, fileName])

  const openFullscreen = useCallback(() => {
    window.open(url, '_blank')
  }, [url])

  // ── Compact mode (inline single-page preview) ──
  if (compact) {
    return (
      <div ref={containerRef} className={cn('w-full flex justify-center', className)}>
        {containerWidth > 0 && !error && (
          <Document
            file={fileSource}
            options={DOC_OPTIONS}
            onLoadSuccess={onDocumentLoadSuccess}
            onLoadError={onDocumentLoadError}
            loading={null}
            className="flex justify-center w-full"
          >
            {docLoaded && (
              <Page
                pageNumber={pageNumber}
                width={containerWidth}
                className="shadow-lg"
                loading={
                  <div
                    className="flex items-center justify-center bg-white dark:bg-gray-800 border border-border"
                    style={{ width: containerWidth, aspectRatio: '1/1.414' }}
                  >
                    <IconLoader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                  </div>
                }
                error={null}
                onLoadError={onPageLoadError}
              />
            )}
          </Document>
        )}
        {error && (
          <p className="text-xs text-muted-foreground py-4">{error}</p>
        )}
      </div>
    )
  }

  // ── Full mode (toolbar + multi-page) ──

  const resolvedHeight = typeof height === 'number' ? `${height}px` : height || '600px'
  const isRelativeHeight = typeof height === 'string' && (height.includes('%') || height.includes('vh'))

  if (error) {
    return (
      <Card className={cn('h-full flex items-center justify-center p-6 text-center', className)}>
        <div>
          <div className="text-red-500 mb-4">
            <svg className="w-16 h-16 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.692-.833-2.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z"
              />
            </svg>
          </div>
          <h3 className="text-lg font-semibold mb-2">Error al cargar el PDF</h3>
          <p className="text-muted-foreground mb-4">{error}</p>
          <Button onClick={() => window.location.reload()} variant="outline">
            Reintentar
          </Button>
        </div>
      </Card>
    )
  }

  return (
    <div
      className={cn('flex flex-col', className)}
      style={
        isRelativeHeight
          ? { height: resolvedHeight }
          : { minHeight: resolvedHeight, height: resolvedHeight }
      }
    >
      {showToolbar && (
        <div className="flex items-center justify-between p-4 border-b bg-card">
          <div className="flex items-center space-x-2">
            <Button variant="outline" size="sm" onClick={goToPrevPage} disabled={pageNumber <= 1}>
              <IconChevronLeft className="h-4 w-4" />
            </Button>

            <div className="flex items-center space-x-2">
              <Input
                type="number"
                value={pageNumber}
                onChange={(e) => goToPage(parseInt(e.target.value) || 1)}
                className="w-16 text-center"
                min={1}
                max={numPages}
              />
              <span className="text-sm text-muted-foreground">de {numPages}</span>
            </div>

            <Button
              variant="outline"
              size="sm"
              onClick={goToNextPage}
              disabled={pageNumber >= numPages}
            >
              <IconChevronRight className="h-4 w-4" />
            </Button>
          </div>

          <div className="flex items-center space-x-2">
            <Button variant="outline" size="sm" onClick={zoomOut} disabled={scale <= 0.5}>
              <IconZoomOut className="h-4 w-4" />
            </Button>

            <Badge variant="secondary" className="cursor-pointer px-3" onClick={resetZoom}>
              {Math.round(scale * 100)}%
            </Badge>

            <Button variant="outline" size="sm" onClick={zoomIn} disabled={scale >= 3.0}>
              <IconZoomIn className="h-4 w-4" />
            </Button>

            <Separator orientation="vertical" className="h-6" />

            <Button variant="outline" size="sm" onClick={rotate}>
              <IconRotateClockwise className="h-4 w-4" />
            </Button>

            <Button variant="outline" size="sm" onClick={downloadPDF}>
              <IconDownload className="h-4 w-4" />
            </Button>

            <Button variant="outline" size="sm" onClick={openFullscreen}>
              <IconMaximize className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}

      <div className="flex-1 overflow-auto bg-gray-100 dark:bg-gray-900 flex justify-center p-4">
        {isLoading && (
          <div className="flex items-center justify-center h-96">
            <IconLoader2 className="h-8 w-8 animate-spin" />
            <span className="ml-2">Cargando PDF...</span>
          </div>
        )}

        <div className="w-full flex justify-center">
          <Document
            file={fileSource}
            options={DOC_OPTIONS}
            onLoadSuccess={onDocumentLoadSuccess}
            onLoadError={onDocumentLoadError}
            loading={null}
            className="flex justify-center w-full"
          >
            {docLoaded && (
              <Page
                pageNumber={pageNumber}
                scale={scale}
                rotate={rotation}
                className="shadow-lg max-w-full"
                loading={
                  <div className="flex items-center justify-center h-96 bg-white border">
                    <IconLoader2 className="h-6 w-6 animate-spin" />
                  </div>
                }
                error={null}
                onLoadError={onPageLoadError}
              />
            )}
          </Document>
        </div>
      </div>

      {/* Status bar */}
      {showToolbar && (
        <div className="flex items-center justify-between px-4 py-2 border-t bg-card text-sm text-muted-foreground">
          <div className="flex items-center space-x-4">
            <span>{fileName}</span>
            {numPages > 0 && (
              <span>
                • Página {pageNumber} de {numPages}
              </span>
            )}
          </div>
          <div className="flex items-center space-x-2">
            <span>Escala: {Math.round(scale * 100)}%</span>
          </div>
        </div>
      )}
    </div>
  )
}
