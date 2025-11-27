'use client'

import React, { useState, useCallback, useRef, useEffect, useMemo } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'

// Import PDF.js CSS for text layer and annotations support
import 'react-pdf/dist/Page/AnnotationLayer.css'
import 'react-pdf/dist/Page/TextLayer.css'

import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
  ChevronLeft,
  ChevronRight,
  ZoomIn,
  ZoomOut,
  AlertTriangle,
  Lightbulb,
  Loader2,
  AlertCircle,
  Download,
  Maximize2,
  RotateCw
} from 'lucide-react'
import { cn } from '@/lib/utils'

// Configure PDF.js worker
pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`

export interface AnalysisItem {
  id: string
  type: 'risk' | 'recommendation'
  severity?: 'high' | 'medium' | 'low'
  title: string
  description: string
  pageNumber: number
  // Coordinates in percentage (0-100) relative to the page
  highlight: {
    x: number
    y: number
    width: number
    height: number
  }
}

interface LegalAnalysisViewerProps {
  url: string
  fileName?: string
  analysisItems: AnalysisItem[]
  className?: string
}

export default function LegalAnalysisViewer({
  url,
  fileName = 'document.pdf',
  analysisItems,
  className
}: LegalAnalysisViewerProps) {
  const [numPages, setNumPages] = useState<number>(0)
  const [pageNumber, setPageNumber] = useState<number>(1)
  const [scale, setScale] = useState<number>(1.0)
  const [rotation, setRotation] = useState<number>(0)
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

  const containerRef = useRef<HTMLDivElement>(null)
  const pdfWrapperRef = useRef<HTMLDivElement>(null)

  // Filter items for current page - memoized for performance
  const currentItems = useMemo(
    () => analysisItems.filter(item => item.pageNumber === pageNumber),
    [analysisItems, pageNumber]
  )

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
    setPageNumber(prev => Math.min(Math.max(1, prev + offset), numPages))
  }, [numPages])

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

  // Get severity label
  const getSeverityLabel = (severity?: 'high' | 'medium' | 'low') => {
    switch (severity) {
      case 'high': return 'Alto'
      case 'medium': return 'Medio'
      case 'low': return 'Bajo'
      default: return 'Medio'
    }
  }

  // Error state
  if (error) {
    return (
      <div className={cn("flex h-full items-center justify-center bg-gray-50 dark:bg-gray-900", className)}>
        <Alert variant="destructive" className="max-w-md">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      </div>
    )
  }

  return (
    <div className={cn("flex h-full bg-gray-50 dark:bg-gray-900", className)}>
      {/* Main PDF Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Toolbar */}
        <div className="h-14 border-b bg-white dark:bg-gray-800 flex items-center justify-between px-4 shadow-sm z-10">
          <div className="flex items-center space-x-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => changePage(-1)}
              disabled={pageNumber <= 1}
              aria-label="Página anterior"
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="text-sm font-medium" aria-live="polite">
              Página {pageNumber} de {numPages}
            </span>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => changePage(1)}
              disabled={pageNumber >= numPages}
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
          className="flex-1 overflow-auto p-8 flex justify-center relative"
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
            <div ref={pdfWrapperRef} className="relative shadow-lg">
              <Page
                pageNumber={pageNumber}
                scale={scale}
                rotate={rotation}
                className="bg-white"
              />

              {/* Overlays Layer */}
              <div className="absolute inset-0 pointer-events-none">
                {currentItems.map((item) => (
                  <div
                    key={item.id}
                    className={cn(
                      "absolute border-[3px] rounded-sm transition-all duration-300 shadow-lg",
                      item.type === 'risk'
                        ? "bg-amber-200/40 border-amber-500 dark:bg-amber-400/30 dark:border-amber-400"
                        : "bg-blue-200/40 border-blue-500 dark:bg-blue-400/30 dark:border-blue-400"
                    )}
                    style={{
                      left: `${item.highlight.x}%`,
                      top: `${item.highlight.y}%`,
                      width: `${item.highlight.width}%`,
                      height: `${item.highlight.height}%`,
                    }}
                  />
                ))}
              </div>

              {/* Connectors Layer (SVG) */}
              <svg className="absolute inset-0 overflow-visible pointer-events-none" style={{ width: '100%', height: '100%' }}>
                <defs>
                  {/* Arrow marker for risk */}
                  <marker
                    id="arrowhead-risk"
                    markerWidth="10"
                    markerHeight="10"
                    refX="9"
                    refY="3"
                    orient="auto"
                  >
                    <polygon points="0 0, 10 3, 0 6" fill="#f59e0b" />
                  </marker>
                  {/* Arrow marker for recommendation */}
                  <marker
                    id="arrowhead-recommendation"
                    markerWidth="10"
                    markerHeight="10"
                    refX="9"
                    refY="3"
                    orient="auto"
                  >
                    <polygon points="0 0, 10 3, 0 6" fill="#3b82f6" />
                  </marker>
                </defs>
                {currentItems.map((item, index) => {
                  // Draw curved connector from highlight to sidebar
                  const color = item.type === 'risk' ? '#f59e0b' : '#3b82f6'
                  const markerId = item.type === 'risk' ? 'arrowhead-risk' : 'arrowhead-recommendation'

                  return (
                    <path
                      key={`connector-${item.id}`}
                      d={`M ${item.highlight.x + item.highlight.width}% ${item.highlight.y + (item.highlight.height / 2)}% 
                         C ${item.highlight.x + item.highlight.width + 10}% ${item.highlight.y + (item.highlight.height / 2)}%,
                           90% ${item.highlight.y + (item.highlight.height / 2)}%,
                           100% ${item.highlight.y + (item.highlight.height / 2)}%`}
                      fill="none"
                      stroke={color}
                      strokeWidth="2.5"
                      strokeDasharray="6 3"
                      markerEnd={`url(#${markerId})`}
                      opacity="0.8"
                    />
                  )
                })}
              </svg>
            </div>
          </Document>
        </div>
      </div>

      {/* Analysis Sidebar */}
      <div className="w-96 border-l bg-white dark:bg-gray-800 flex flex-col shadow-xl z-20">
        <div className="p-6 border-b bg-gradient-to-r from-gray-50 to-white dark:from-gray-800 dark:to-gray-900">
          <h2 className="font-serif text-2xl font-bold text-gray-900 dark:text-gray-100">
            Análisis del Agente Legal
          </h2>
        </div>

        <ScrollArea className="flex-1 p-6">
          <div className="space-y-5">
            {currentItems.length === 0 ? (
              <div className="text-center text-muted-foreground py-12">
                <p className="text-sm">No hay observaciones en esta página.</p>
              </div>
            ) : (
              currentItems.map((item) => (
                <Card
                  key={item.id}
                  className={cn(
                    "p-5 transition-all duration-300 hover:shadow-xl hover:scale-[1.02] rounded-xl border-0 shadow-lg",
                    item.type === 'risk'
                      ? "bg-gradient-to-br from-amber-50 to-amber-100/50 dark:from-amber-950/40 dark:to-amber-900/20"
                      : "bg-gradient-to-br from-blue-50 to-blue-100/50 dark:from-blue-950/40 dark:to-blue-900/20"
                  )}
                >
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex-1">
                      {item.type === 'risk' ? (
                        <div className={cn(
                          "inline-flex items-center gap-2 px-3 py-1.5 rounded-lg font-bold text-sm uppercase tracking-wide",
                          item.severity === 'high'
                            ? "bg-amber-500 text-white shadow-md"
                            : "bg-amber-400 text-amber-900"
                        )}>
                          <AlertTriangle className="h-4 w-4" />
                          Riesgo {getSeverityLabel(item.severity)}
                        </div>
                      ) : (
                        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-blue-600 text-white font-bold text-sm uppercase tracking-wide shadow-md">
                          <Lightbulb className="h-4 w-4" />
                          Recomendación
                        </div>
                      )}
                    </div>
                    {item.type === 'risk' ? (
                      <AlertTriangle className="h-6 w-6 text-amber-600 dark:text-amber-500 flex-shrink-0" />
                    ) : (
                      <Lightbulb className="h-6 w-6 text-blue-600 dark:text-blue-500 flex-shrink-0" />
                    )}
                  </div>

                  <p className="text-sm text-gray-800 dark:text-gray-200 leading-relaxed font-medium">
                    {item.description}
                  </p>
                </Card>
              ))
            )}
          </div>
        </ScrollArea>
      </div>
    </div>
  )
}
