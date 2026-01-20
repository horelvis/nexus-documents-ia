'use client'

import React, { useState, useCallback, useRef, useEffect } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'

// Import PDF.js CSS for text layer and annotations support
import 'react-pdf/dist/Page/AnnotationLayer.css'
import 'react-pdf/dist/Page/TextLayer.css'

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
  ChevronLeft,
  ChevronRight,
  ZoomIn,
  ZoomOut,
  Loader2,
  AlertCircle,
  Download,
  Maximize2,
  RotateCw
} from 'lucide-react'
import { cn } from '@/lib/utils'

// Configure PDF.js worker
pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`

interface PDFAnnotationViewerProps {
  url: string
  fileName?: string
  currentPage: number
  onPageChange: (page: number) => void
  className?: string
}

export function PDFAnnotationViewer({
  url,
  fileName = 'document.pdf',
  currentPage,
  onPageChange,
  className
}: PDFAnnotationViewerProps) {
  const [numPages, setNumPages] = useState<number>(0)
  const [scale, setScale] = useState<number>(1.0)
  const [rotation, setRotation] = useState<number>(0)
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)
  const [containerHeight, setContainerHeight] = useState<number>(0)

  const containerRef = useRef<HTMLDivElement>(null)

  // Calculate fit-to-height scale
  useEffect(() => {
    if (!containerRef.current) return

    const updateHeight = () => {
      if (containerRef.current) {
        // Subtract padding (16px top + 16px bottom = 32px)
        const height = containerRef.current.clientHeight - 32
        setContainerHeight(height)
      }
    }

    updateHeight()
    const resizeObserver = new ResizeObserver(updateHeight)
    resizeObserver.observe(containerRef.current)

    return () => resizeObserver.disconnect()
  }, [])

  const onDocumentLoadSuccess = useCallback(({ numPages }: { numPages: number }) => {
    setNumPages(numPages)
    setIsLoading(false)
    setError(null)
  }, [])

  const onDocumentLoadError = useCallback((error: Error) => {
    console.error('Error loading PDF:', error)
    setError('Error al cargar el documento PDF')
    setIsLoading(false)
  }, [])

  const changePage = useCallback((offset: number) => {
    const newPage = Math.min(Math.max(1, currentPage + offset), numPages)
    onPageChange(newPage)
  }, [currentPage, numPages, onPageChange])

  const handleZoomIn = useCallback(() => {
    setScale(s => Math.min(2.0, s + 0.1))
  }, [])

  const handleZoomOut = useCallback(() => {
    setScale(s => Math.max(0.5, s - 0.1))
  }, [])

  const handleResetZoom = useCallback(() => {
    setScale(1.0)
  }, [])

  const handleRotate = useCallback(() => {
    setRotation(prev => (prev + 90) % 360)
  }, [])

  const handleDownload = useCallback(() => {
    const link = document.createElement('a')
    link.href = url
    link.download = fileName
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }, [url, fileName])

  const handleFullscreen = useCallback(() => {
    window.open(url, '_blank')
  }, [url])

  if (error) {
    return (
      <div className={cn("flex h-full items-center justify-center bg-background", className)}>
        <Alert variant="destructive" className="max-w-md">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      </div>
    )
  }

  return (
    <div className={cn("flex flex-col h-full bg-background", className)}>
      {/* Toolbar */}
      <div className="h-14 border-b bg-card flex items-center justify-between px-4 shadow-sm z-10 flex-shrink-0">
        <div className="flex items-center space-x-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => changePage(-1)}
            disabled={currentPage <= 1}
            aria-label="Página anterior"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="text-sm font-medium" aria-live="polite">
            Página {currentPage} de {numPages}
          </span>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => changePage(1)}
            disabled={currentPage >= numPages}
            aria-label="Página siguiente"
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>

        <div className="flex items-center space-x-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={handleZoomOut}
            disabled={scale <= 0.5}
            aria-label="Reducir zoom"
          >
            <ZoomOut className="h-4 w-4" />
          </Button>
          <Badge
            variant="secondary"
            className="cursor-pointer px-3 min-w-[60px] text-center"
            onClick={handleResetZoom}
            aria-label="Restablecer zoom"
          >
            {Math.round(scale * 100)}%
          </Badge>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleZoomIn}
            disabled={scale >= 2.0}
            aria-label="Aumentar zoom"
          >
            <ZoomIn className="h-4 w-4" />
          </Button>

          <div className="h-6 w-px bg-border mx-1" />

          <Button
            variant="ghost"
            size="sm"
            onClick={handleRotate}
            aria-label="Rotar documento"
          >
            <RotateCw className="h-4 w-4" />
          </Button>

          <Button
            variant="ghost"
            size="sm"
            onClick={handleDownload}
            aria-label="Descargar documento"
          >
            <Download className="h-4 w-4" />
          </Button>

          <Button
            variant="ghost"
            size="sm"
            onClick={handleFullscreen}
            aria-label="Abrir en pantalla completa"
          >
            <Maximize2 className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* PDF Content */}
      <div
        ref={containerRef}
        className="flex-1 overflow-auto p-4 flex justify-center items-start relative"
      >
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        )}

        <Document
          file={url}
          onLoadSuccess={onDocumentLoadSuccess}
          onLoadError={onDocumentLoadError}
          loading={null}
          className="relative"
        >
          <div className="relative shadow-lg">
            <Page
              pageNumber={currentPage}
              scale={scale}
              rotate={rotation}
              height={containerHeight > 0 ? containerHeight : undefined}
              className="shadow-sm"
            />
          </div>
        </Document>
      </div>
    </div>
  )
}
