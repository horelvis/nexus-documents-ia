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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
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
  RotateCw,
  List,
  FileText
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
  fitToWidth?: boolean
}

// Type for text position found in PDF
interface TextPosition {
  pageNumber: number
  x: number
  y: number
  width: number
  height: number
}

// Type for page text content
interface PageTextContent {
  pageNumber: number
  text: string
  items: Array<{
    str: string
    transform: number[]
    width: number
    height: number
  }>
  viewport: { width: number; height: number }
}

export default function LegalAnalysisViewer({
  url,
  fileName = 'document.pdf',
  analysisItems,
  className,
  fitToWidth = true
}: LegalAnalysisViewerProps) {
  const [numPages, setNumPages] = useState<number>(0)
  const [pageNumber, setPageNumber] = useState<number>(1)
  const [scale, setScale] = useState<number>(1.0)
  const [rotation, setRotation] = useState<number>(0)
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)
  const [containerWidth, setContainerWidth] = useState<number>(0)
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null)
  const [sidebarTab, setSidebarTab] = useState<'page' | 'all'>('page')
  const [pdfDocument, setPdfDocument] = useState<any>(null)
  const [pageTextContents, setPageTextContents] = useState<PageTextContent[]>([])
  const [isExtractingText, setIsExtractingText] = useState<boolean>(false)

  const containerRef = useRef<HTMLDivElement>(null)
  const pdfWrapperRef = useRef<HTMLDivElement>(null)

  // Helper function to find text in PDF pages and get position
  const findTextInPdf = useCallback((searchText: string): TextPosition | null => {
    if (!pageTextContents.length || !searchText) return null

    // Extract key phrases from the description (first 50 chars or first sentence)
    const searchTerms = searchText
      .slice(0, 100)
      .toLowerCase()
      .replace(/[^\w\sáéíóúñü]/g, ' ')
      .split(/\s+/)
      .filter(term => term.length > 4) // Only meaningful words
      .slice(0, 5)

    if (searchTerms.length === 0) return null

    // Search each page for the terms
    for (const pageContent of pageTextContents) {
      const pageTextLower = pageContent.text.toLowerCase()
      const matchCount = searchTerms.filter(term => pageTextLower.includes(term)).length

      // If at least 60% of terms match, consider it a match
      if (matchCount >= Math.ceil(searchTerms.length * 0.6)) {
        // Find approximate position of the first matching term
        const firstTerm = searchTerms.find(term => pageTextLower.includes(term))
        if (firstTerm) {
          const termIndex = pageTextLower.indexOf(firstTerm)
          // Estimate vertical position based on character position
          const estimatedY = Math.min(85, Math.max(10, (termIndex / pageTextLower.length) * 100))

          return {
            pageNumber: pageContent.pageNumber,
            x: 5,
            y: estimatedY,
            width: 90,
            height: 8
          }
        }
      }
    }

    return null
  }, [pageTextContents])

  // Check if we have real page information (not all items on page 1)
  const hasRealPageInfo = useMemo(() => {
    if (analysisItems.length === 0) return false
    const uniquePages = new Set(analysisItems.map(item => item.pageNumber))
    return uniquePages.size > 1 || !uniquePages.has(1)
  }, [analysisItems])

  // Assign global index numbers and find real positions in PDF
  const itemsWithIndex = useMemo(() => {
    // If we have extracted text, try to find real positions
    if (pageTextContents.length > 0 && !hasRealPageInfo) {
      return analysisItems.map((item, index) => {
        const position = findTextInPdf(item.description)
        return {
          ...item,
          pageNumber: position?.pageNumber || 1,
          highlight: position || item.highlight,
          globalIndex: index + 1,
          foundInPdf: !!position
        }
      })
    }

    // If no text extracted yet or already has real page info
    if (hasRealPageInfo || numPages === 0) {
      return analysisItems.map((item, index) => ({
        ...item,
        globalIndex: index + 1,
        foundInPdf: false
      }))
    }

    // Fallback: distribute items evenly across all pages
    const itemsPerPage = Math.ceil(analysisItems.length / Math.max(numPages, 1))
    return analysisItems.map((item, index) => ({
      ...item,
      pageNumber: Math.min(Math.floor(index / itemsPerPage) + 1, numPages),
      globalIndex: index + 1,
      foundInPdf: false
    }))
  }, [analysisItems, hasRealPageInfo, numPages, pageTextContents, findTextInPdf])

  // Filter items for current page and adjust highlight positions if needed
  const currentItems = useMemo(() => {
    const pageItems = itemsWithIndex.filter(item => item.pageNumber === pageNumber)

    // If items were found in PDF, use their positions; otherwise distribute evenly
    const needsDistribution = pageItems.some(item => !item.foundInPdf)

    if (needsDistribution) {
      // Recalculate highlight positions for items not found in PDF
      return pageItems.map((item, idx) => {
        if (item.foundInPdf) return item

        const totalOnPage = pageItems.length
        const availableHeight = 70 // 15% to 85%
        const spacing = totalOnPage > 1 ? availableHeight / (totalOnPage - 1) : 0
        const baseY = 15 + (idx * spacing)
        const xVariation = (idx % 3) * 5

        return {
          ...item,
          highlight: {
            x: 5 + xVariation,
            y: Math.min(baseY, 85),
            width: 85 - xVariation,
            height: 6
          }
        }
      })
    }

    return pageItems
  }, [itemsWithIndex, pageNumber])

  // Group all items by page for the "all" view
  const itemsByPage = useMemo(() => {
    const grouped: Record<number, typeof itemsWithIndex> = {}
    itemsWithIndex.forEach(item => {
      if (!grouped[item.pageNumber]) {
        grouped[item.pageNumber] = []
      }
      grouped[item.pageNumber].push(item)
    })
    return grouped
  }, [itemsWithIndex])

  // Calculate fit-to-width scale
  useEffect(() => {
    if (!containerRef.current || !fitToWidth) return

    const updateWidth = () => {
      if (containerRef.current) {
        // Account for padding (32px each side = 64px total)
        const width = containerRef.current.clientWidth - 64
        setContainerWidth(width)
      }
    }

    updateWidth()
    const resizeObserver = new ResizeObserver(updateWidth)
    resizeObserver.observe(containerRef.current)

    return () => resizeObserver.disconnect()
  }, [fitToWidth])

  const onDocumentLoadSuccess = useCallback(async ({ numPages, _pdfInfo }: { numPages: number; _pdfInfo?: any }) => {
    setNumPages(numPages)
    setIsLoading(false)
    setError(null)

    // Extract text from all pages for text search
    if (url && analysisItems.length > 0) {
      setIsExtractingText(true)
      try {
        const loadingTask = pdfjs.getDocument(url)
        const pdf = await loadingTask.promise
        setPdfDocument(pdf)

        const textContents: PageTextContent[] = []

        for (let i = 1; i <= numPages; i++) {
          const page = await pdf.getPage(i)
          const viewport = page.getViewport({ scale: 1 })
          const textContent = await page.getTextContent()

          const pageText = textContent.items
            .map((item: any) => item.str)
            .join(' ')

          textContents.push({
            pageNumber: i,
            text: pageText,
            items: textContent.items.map((item: any) => ({
              str: item.str,
              transform: item.transform,
              width: item.width,
              height: item.height
            })),
            viewport: { width: viewport.width, height: viewport.height }
          })
        }

        setPageTextContents(textContents)
      } catch (err) {
        console.error('Error extracting text from PDF:', err)
      } finally {
        setIsExtractingText(false)
      }
    }
  }, [url, analysisItems.length])

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

  // Navigate to item's page and select it
  const handleItemClick = useCallback((item: typeof itemsWithIndex[0]) => {
    setPageNumber(item.pageNumber)
    setSelectedItemId(item.id)
    // Clear selection after animation
    setTimeout(() => setSelectedItemId(null), 2000)
  }, [])

  // Get severity label
  const getSeverityLabel = (severity?: 'high' | 'medium' | 'low') => {
    switch (severity) {
      case 'high': return 'Alto'
      case 'medium': return 'Medio'
      case 'low': return 'Bajo'
      default: return 'Medio'
    }
  }

  // Get severity color for number badge
  const getSeverityColor = (item: typeof itemsWithIndex[0]) => {
    if (item.type === 'recommendation') return 'bg-blue-600 text-white'
    switch (item.severity) {
      case 'high': return 'bg-red-600 text-white'
      case 'medium': return 'bg-amber-500 text-white'
      case 'low': return 'bg-yellow-400 text-yellow-900'
      default: return 'bg-amber-500 text-white'
    }
  }

  // Error state
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
    <div className={cn("flex h-full bg-background", className)}>
      {/* Main PDF Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Toolbar */}
        <div className="h-14 border-b bg-card flex items-center justify-between px-4 shadow-sm z-10">
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
                width={fitToWidth && containerWidth > 0 ? containerWidth : undefined}
                className="shadow-sm"
              />

              {/* Overlays Layer with numbered markers */}
              <div className="absolute inset-0 pointer-events-none">
                {currentItems.map((item) => (
                  <div
                    key={item.id}
                    className={cn(
                      "absolute border-[3px] rounded-sm transition-all duration-500",
                      item.type === 'risk'
                        ? "bg-amber-200/40 border-amber-500 dark:bg-amber-400/30 dark:border-amber-400"
                        : "bg-blue-200/40 border-blue-500 dark:bg-blue-400/30 dark:border-blue-400",
                      selectedItemId === item.id && "ring-4 ring-offset-2 ring-primary animate-pulse"
                    )}
                    style={{
                      left: `${item.highlight.x}%`,
                      top: `${item.highlight.y}%`,
                      width: `${item.highlight.width}%`,
                      height: `${item.highlight.height}%`,
                    }}
                  >
                    {/* Number badge on highlight */}
                    <div
                      className={cn(
                        "absolute -top-3 -left-3 w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold shadow-lg pointer-events-auto cursor-pointer",
                        getSeverityColor(item)
                      )}
                      title={`${item.type === 'risk' ? 'Riesgo' : 'Recomendación'} #${item.globalIndex}`}
                    >
                      {item.globalIndex}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </Document>
        </div>
      </div>

      {/* Analysis Sidebar */}
      <div className="w-96 border-l bg-card flex flex-col shadow-xl z-20">
        <div className="p-4 border-b bg-muted/30">
          <h2 className="font-serif text-xl font-bold mb-3">
            Análisis Legal
          </h2>
          <Tabs value={sidebarTab} onValueChange={(v) => setSidebarTab(v as 'page' | 'all')}>
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="page" className="text-xs">
                <FileText className="h-3 w-3 mr-1" />
                Página {pageNumber}
              </TabsTrigger>
              <TabsTrigger value="all" className="text-xs">
                <List className="h-3 w-3 mr-1" />
                Todos ({itemsWithIndex.length})
              </TabsTrigger>
            </TabsList>
          </Tabs>
        </div>

        <ScrollArea className="flex-1">
          {sidebarTab === 'page' ? (
            /* Current Page Items */
            <div className="p-4 space-y-4">
              {currentItems.length === 0 ? (
                <div className="text-center text-muted-foreground py-12">
                  <FileText className="h-8 w-8 mx-auto mb-2 opacity-50" />
                  <p className="text-sm">No hay observaciones en esta página.</p>
                </div>
              ) : (
                currentItems.map((item) => (
                  <Card
                    key={item.id}
                    className={cn(
                      "p-4 transition-all duration-300 hover:shadow-xl cursor-pointer rounded-xl border-0 shadow-lg",
                      item.type === 'risk'
                        ? "bg-gradient-to-br from-amber-50 to-amber-100/50 dark:from-amber-950/40 dark:to-amber-900/20"
                        : "bg-gradient-to-br from-blue-50 to-blue-100/50 dark:from-blue-950/40 dark:to-blue-900/20",
                      selectedItemId === item.id && "ring-2 ring-primary"
                    )}
                    onClick={() => handleItemClick(item)}
                  >
                    <div className="flex items-start gap-3">
                      {/* Number badge */}
                      <div className={cn(
                        "w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold flex-shrink-0",
                        getSeverityColor(item)
                      )}>
                        {item.globalIndex}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-2">
                          {item.type === 'risk' ? (
                            <Badge variant="outline" className={cn(
                              "text-xs",
                              item.severity === 'high' ? "border-red-500 text-red-600" :
                              item.severity === 'medium' ? "border-amber-500 text-amber-600" :
                              "border-yellow-500 text-yellow-600"
                            )}>
                              <AlertTriangle className="h-3 w-3 mr-1" />
                              Riesgo {getSeverityLabel(item.severity)}
                            </Badge>
                          ) : (
                            <Badge variant="outline" className="text-xs border-blue-500 text-blue-600">
                              <Lightbulb className="h-3 w-3 mr-1" />
                              Recomendación
                            </Badge>
                          )}
                        </div>
                        <p className="text-sm text-gray-800 dark:text-gray-200 leading-relaxed">
                          {item.description}
                        </p>
                      </div>
                    </div>
                  </Card>
                ))
              )}
            </div>
          ) : (
            /* All Items grouped by page */
            <div className="p-4 space-y-6">
              {Object.keys(itemsByPage).length === 0 ? (
                <div className="text-center text-muted-foreground py-12">
                  <List className="h-8 w-8 mx-auto mb-2 opacity-50" />
                  <p className="text-sm">No hay observaciones en el documento.</p>
                </div>
              ) : (
                Object.entries(itemsByPage)
                  .sort(([a], [b]) => Number(a) - Number(b))
                  .map(([page, items]) => (
                    <div key={page}>
                      <div className="flex items-center gap-2 mb-3">
                        <Badge variant="secondary" className="text-xs">
                          Página {page}
                        </Badge>
                        <span className="text-xs text-muted-foreground">
                          {items.length} {items.length === 1 ? 'hallazgo' : 'hallazgos'}
                        </span>
                      </div>
                      <div className="space-y-3 pl-2 border-l-2 border-muted">
                        {items.map((item) => (
                          <Card
                            key={item.id}
                            className={cn(
                              "p-3 transition-all duration-300 hover:shadow-lg cursor-pointer rounded-lg border-0 shadow",
                              item.type === 'risk'
                                ? "bg-gradient-to-br from-amber-50 to-amber-100/50 dark:from-amber-950/40 dark:to-amber-900/20"
                                : "bg-gradient-to-br from-blue-50 to-blue-100/50 dark:from-blue-950/40 dark:to-blue-900/20",
                              Number(page) === pageNumber && "border-l-4 border-l-primary"
                            )}
                            onClick={() => handleItemClick(item)}
                          >
                            <div className="flex items-start gap-2">
                              {/* Number badge - smaller */}
                              <div className={cn(
                                "w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0",
                                getSeverityColor(item)
                              )}>
                                {item.globalIndex}
                              </div>
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-1 mb-1">
                                  {item.type === 'risk' ? (
                                    <AlertTriangle className="h-3 w-3 text-amber-600" />
                                  ) : (
                                    <Lightbulb className="h-3 w-3 text-blue-600" />
                                  )}
                                  <span className="text-xs font-medium text-muted-foreground">
                                    {item.type === 'risk' ? `Riesgo ${getSeverityLabel(item.severity)}` : 'Recomendación'}
                                  </span>
                                </div>
                                <p className="text-xs text-gray-700 dark:text-gray-300 leading-relaxed line-clamp-2">
                                  {item.description}
                                </p>
                              </div>
                            </div>
                          </Card>
                        ))}
                      </div>
                    </div>
                  ))
              )}
            </div>
          )}
        </ScrollArea>

        {/* Summary footer */}
        <div className="p-3 border-t bg-muted/30 text-xs text-muted-foreground space-y-1">
          <div className="flex items-center justify-between">
            <span>
              {itemsWithIndex.filter(i => i.type === 'risk').length} riesgos
            </span>
            <span>
              {itemsWithIndex.filter(i => i.type === 'recommendation').length} recomendaciones
            </span>
          </div>
          {isExtractingText && (
            <div className="flex items-center justify-center gap-2 text-muted-foreground/70">
              <Loader2 className="h-3 w-3 animate-spin" />
              <span>Buscando ubicaciones en el documento...</span>
            </div>
          )}
          {!isExtractingText && !hasRealPageInfo && itemsWithIndex.length > 0 && (
            <div className="text-center text-muted-foreground/70 italic">
              {itemsWithIndex.filter(i => i.foundInPdf).length > 0
                ? `${itemsWithIndex.filter(i => i.foundInPdf).length} de ${itemsWithIndex.length} ubicados en el documento`
                : 'Ubicaciones estimadas'}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
