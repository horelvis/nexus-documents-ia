'use client'

import React, { useState, useCallback, useRef, useEffect } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { 
  ChevronLeft, 
  ChevronRight, 
  ZoomIn, 
  ZoomOut, 
  AlertTriangle, 
  Lightbulb,
  Loader2
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
  analysisItems: AnalysisItem[]
  className?: string
}

export default function LegalAnalysisViewer({ 
  url, 
  analysisItems,
  className 
}: LegalAnalysisViewerProps) {
  const [numPages, setNumPages] = useState<number>(0)
  const [pageNumber, setPageNumber] = useState<number>(1)
  const [scale, setScale] = useState<number>(1.0)
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [containerWidth, setContainerWidth] = useState<number>(0)
  
  const containerRef = useRef<HTMLDivElement>(null)
  const pdfWrapperRef = useRef<HTMLDivElement>(null)
  
  // Filter items for current page
  const currentItems = analysisItems.filter(item => item.pageNumber === pageNumber)

  useEffect(() => {
    const updateWidth = () => {
      if (containerRef.current) {
        setContainerWidth(containerRef.current.clientWidth)
      }
    }
    
    window.addEventListener('resize', updateWidth)
    updateWidth()
    
    return () => window.removeEventListener('resize', updateWidth)
  }, [])

  const onDocumentLoadSuccess = useCallback(({ numPages }: { numPages: number }) => {
    setNumPages(numPages)
    setIsLoading(false)
  }, [])

  const changePage = (offset: number) => {
    setPageNumber(prev => Math.min(Math.max(1, prev + offset), numPages))
  }

  // Calculate connector path
  const getConnectorPath = (item: AnalysisItem, index: number) => {
    // This is a simplified calculation. In a real app, we'd need precise DOM measurements.
    // We assume the PDF page is centered or left-aligned in the wrapper.
    
    // For now, we'll just draw a line from the highlight to the right edge of the PDF area
    // The actual SVG connecting to the card would need to be in a higher-level container
    // or we can just render the "start" of the connector here.
    
    return "" 
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
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="text-sm font-medium">
              Page {pageNumber} of {numPages}
            </span>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => changePage(1)}
              disabled={pageNumber >= numPages}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
          
          <div className="flex items-center space-x-2">
            <Button variant="ghost" size="sm" onClick={() => setScale(s => Math.max(0.5, s - 0.1))}>
              <ZoomOut className="h-4 w-4" />
            </Button>
            <span className="text-sm w-12 text-center">{Math.round(scale * 100)}%</span>
            <Button variant="ghost" size="sm" onClick={() => setScale(s => Math.min(2.0, s + 0.1))}>
              <ZoomIn className="h-4 w-4" />
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
            className="relative"
          >
            <div ref={pdfWrapperRef} className="relative shadow-lg">
              <Page 
                pageNumber={pageNumber} 
                scale={scale}
                renderTextLayer={true}
                renderAnnotationLayer={true}
                className="bg-white"
              />
              
              {/* Overlays Layer */}
              <div className="absolute inset-0 pointer-events-none">
                {currentItems.map((item) => (
                  <div
                    key={item.id}
                    className={cn(
                      "absolute border-2 opacity-50 transition-all duration-200",
                      item.type === 'risk' ? "bg-amber-100 border-amber-500" : "bg-blue-100 border-blue-500"
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
                {currentItems.map((item, index) => {
                  // Calculate start point (right edge of highlight)
                  const startX = `${item.highlight.x + item.highlight.width}%`
                  const startY = `${item.highlight.y + (item.highlight.height / 2)}%`
                  
                  // We'll draw a line to the right edge of the page
                  // In a real implementation, we'd calculate the exact position of the card
                  return (
                    <path
                      key={`connector-${item.id}`}
                      d={`M ${item.highlight.x + item.highlight.width}% ${item.highlight.y + (item.highlight.height / 2)}% 
                         C ${item.highlight.x + item.highlight.width + 10}% ${item.highlight.y + (item.highlight.height / 2)}%,
                           90% ${item.highlight.y + (item.highlight.height / 2)}%,
                           100% ${item.highlight.y + (item.highlight.height / 2)}%`}
                      fill="none"
                      stroke={item.type === 'risk' ? '#f59e0b' : '#3b82f6'}
                      strokeWidth="2"
                      strokeDasharray="4"
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
        <div className="p-4 border-b">
          <h2 className="font-serif text-xl font-bold text-gray-900 dark:text-gray-100">
            Análisis del Agente Legal
          </h2>
        </div>
        
        <ScrollArea className="flex-1 p-4">
          <div className="space-y-4">
            {currentItems.length === 0 ? (
              <div className="text-center text-muted-foreground py-8">
                No hay observaciones en esta página.
              </div>
            ) : (
              currentItems.map((item) => (
                <Card 
                  key={item.id}
                  className={cn(
                    "p-4 transition-all duration-200 hover:shadow-md border-l-4",
                    item.type === 'risk' 
                      ? "bg-amber-50 dark:bg-amber-950/30 border-l-amber-500 border-y-amber-200 border-r-amber-200" 
                      : "bg-blue-50 dark:bg-blue-950/30 border-l-blue-500 border-y-blue-200 border-r-blue-200"
                  )}
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex items-center gap-2">
                      {item.type === 'risk' ? (
                        <span className="text-xs font-bold text-amber-700 dark:text-amber-400 uppercase tracking-wider">
                          Riesgo {item.severity === 'high' ? 'Alto' : 'Medio'}
                        </span>
                      ) : (
                        <span className="text-xs font-bold text-blue-700 dark:text-blue-400 uppercase tracking-wider">
                          Recomendación
                        </span>
                      )}
                    </div>
                    {item.type === 'risk' ? (
                      <AlertTriangle className="h-5 w-5 text-amber-600" />
                    ) : (
                      <Lightbulb className="h-5 w-5 text-blue-600" />
                    )}
                  </div>
                  
                  <p className="text-sm text-gray-800 dark:text-gray-200 leading-relaxed">
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
