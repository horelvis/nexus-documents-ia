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
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  ChevronLeft,
  ChevronRight,
  ZoomIn,
  ZoomOut,
  RotateCw,
  Download,
  Maximize2,
  Loader2,
  Eye,
  EyeOff,
  Highlighter,
  List,
  Tag,
  User,
  Building2,
  Calendar,
  Banknote,
  FileText,
  Hash,
  Search,
  X
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

// Entity types and colors
const ENTITY_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  // Personas
  trabajador: { bg: 'bg-blue-100 dark:bg-blue-900/40', border: 'border-blue-400', text: 'text-blue-700 dark:text-blue-300' },
  person: { bg: 'bg-blue-100 dark:bg-blue-900/40', border: 'border-blue-400', text: 'text-blue-700 dark:text-blue-300' },
  cliente: { bg: 'bg-blue-100 dark:bg-blue-900/40', border: 'border-blue-400', text: 'text-blue-700 dark:text-blue-300' },
  declarante: { bg: 'bg-blue-100 dark:bg-blue-900/40', border: 'border-blue-400', text: 'text-blue-700 dark:text-blue-300' },
  // Empresas
  empresa: { bg: 'bg-purple-100 dark:bg-purple-900/40', border: 'border-purple-400', text: 'text-purple-700 dark:text-purple-300' },
  organization: { bg: 'bg-purple-100 dark:bg-purple-900/40', border: 'border-purple-400', text: 'text-purple-700 dark:text-purple-300' },
  company: { bg: 'bg-purple-100 dark:bg-purple-900/40', border: 'border-purple-400', text: 'text-purple-700 dark:text-purple-300' },
  proveedor: { bg: 'bg-purple-100 dark:bg-purple-900/40', border: 'border-purple-400', text: 'text-purple-700 dark:text-purple-300' },
  // Financiero
  amount: { bg: 'bg-green-100 dark:bg-green-900/40', border: 'border-green-400', text: 'text-green-700 dark:text-green-300' },
  liquido: { bg: 'bg-green-100 dark:bg-green-900/40', border: 'border-green-400', text: 'text-green-700 dark:text-green-300' },
  devengo: { bg: 'bg-emerald-100 dark:bg-emerald-900/40', border: 'border-emerald-400', text: 'text-emerald-700 dark:text-emerald-300' },
  deduccion: { bg: 'bg-red-100 dark:bg-red-900/40', border: 'border-red-400', text: 'text-red-700 dark:text-red-300' },
  // Fechas
  fecha: { bg: 'bg-amber-100 dark:bg-amber-900/40', border: 'border-amber-400', text: 'text-amber-700 dark:text-amber-300' },
  date: { bg: 'bg-amber-100 dark:bg-amber-900/40', border: 'border-amber-400', text: 'text-amber-700 dark:text-amber-300' },
  periodo: { bg: 'bg-amber-100 dark:bg-amber-900/40', border: 'border-amber-400', text: 'text-amber-700 dark:text-amber-300' },
  // Identificadores
  invoice_number: { bg: 'bg-cyan-100 dark:bg-cyan-900/40', border: 'border-cyan-400', text: 'text-cyan-700 dark:text-cyan-300' },
  expediente: { bg: 'bg-cyan-100 dark:bg-cyan-900/40', border: 'border-cyan-400', text: 'text-cyan-700 dark:text-cyan-300' },
  // Bancario
  iban: { bg: 'bg-indigo-100 dark:bg-indigo-900/40', border: 'border-indigo-400', text: 'text-indigo-700 dark:text-indigo-300' },
  // Default
  default: { bg: 'bg-gray-100 dark:bg-gray-800', border: 'border-gray-400', text: 'text-gray-700 dark:text-gray-300' }
}

const ENTITY_ICONS: Record<string, React.ReactNode> = {
  trabajador: <User className="h-3 w-3" />,
  person: <User className="h-3 w-3" />,
  cliente: <User className="h-3 w-3" />,
  declarante: <User className="h-3 w-3" />,
  empresa: <Building2 className="h-3 w-3" />,
  organization: <Building2 className="h-3 w-3" />,
  company: <Building2 className="h-3 w-3" />,
  proveedor: <Building2 className="h-3 w-3" />,
  amount: <Banknote className="h-3 w-3" />,
  liquido: <Banknote className="h-3 w-3" />,
  devengo: <Banknote className="h-3 w-3" />,
  deduccion: <Banknote className="h-3 w-3" />,
  fecha: <Calendar className="h-3 w-3" />,
  date: <Calendar className="h-3 w-3" />,
  periodo: <Calendar className="h-3 w-3" />,
  invoice_number: <FileText className="h-3 w-3" />,
  expediente: <FileText className="h-3 w-3" />,
  iban: <Hash className="h-3 w-3" />,
  default: <Tag className="h-3 w-3" />
}

export interface DocumentEntity {
  id?: string
  class: string
  text: string
  attributes?: Record<string, any>
  source_indices?: [number, number] | null
  page?: number
}

type ViewMode = 'highlight' | 'sidebar' | 'badges' | 'off'

interface PDFEntityViewerProps {
  url: string
  fileName?: string
  entities?: DocumentEntity[]
  className?: string
  showToolbar?: boolean
  initialScale?: number
  height?: string | number
}

function getEntityColor(entityClass: string) {
  return ENTITY_COLORS[entityClass.toLowerCase()] || ENTITY_COLORS.default
}

function getEntityIcon(entityClass: string) {
  return ENTITY_ICONS[entityClass.toLowerCase()] || ENTITY_ICONS.default
}

function getEntityLabel(entityClass: string): string {
  const labels: Record<string, string> = {
    trabajador: 'Trabajador',
    person: 'Persona',
    cliente: 'Cliente',
    declarante: 'Declarante',
    empresa: 'Empresa',
    organization: 'Organización',
    company: 'Empresa',
    proveedor: 'Proveedor',
    amount: 'Importe',
    liquido: 'Líquido',
    devengo: 'Devengo',
    deduccion: 'Deducción',
    fecha: 'Fecha',
    date: 'Fecha',
    periodo: 'Período',
    invoice_number: 'Nº Factura',
    expediente: 'Expediente',
    iban: 'IBAN'
  }
  return labels[entityClass.toLowerCase()] || entityClass
}

// Group entities by category
function groupEntities(entities: DocumentEntity[]): Record<string, DocumentEntity[]> {
  const groups: Record<string, DocumentEntity[]> = {}
  entities.forEach(entity => {
    const category = entity.class.toLowerCase()
    if (!groups[category]) {
      groups[category] = []
    }
    groups[category].push(entity)
  })
  return groups
}

export default function PDFEntityViewer({
  url,
  fileName = 'document.pdf',
  entities = [],
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
  const [viewMode, setViewMode] = useState<ViewMode>('sidebar')
  const [selectedEntity, setSelectedEntity] = useState<DocumentEntity | null>(null)
  const [highlightedEntities, setHighlightedEntities] = useState<Set<string>>(new Set())
  const [searchResults, setSearchResults] = useState<number>(0)
  const pageRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // Inject highlight styles
  useEffect(() => {
    const styleId = 'pdf-entity-highlight-styles'
    if (!document.getElementById(styleId)) {
      const style = document.createElement('style')
      style.id = styleId
      style.textContent = highlightStyles
      document.head.appendChild(style)
    }
  }, [])

  // Function to highlight text in the PDF TextLayer
  const highlightTextInPdf = useCallback((searchText: string, isActive: boolean = true) => {
    if (!containerRef.current || !searchText) return 0

    // Clear previous highlights
    const existingHighlights = containerRef.current.querySelectorAll('.entity-highlight, .entity-highlight-active')
    existingHighlights.forEach(el => {
      el.classList.remove('entity-highlight', 'entity-highlight-active')
    })

    // Find text layer spans
    const textLayer = containerRef.current.querySelector('.react-pdf__Page__textContent')
    if (!textLayer) return 0

    const spans = textLayer.querySelectorAll('span')
    const searchLower = searchText.toLowerCase().trim()
    const searchWords = searchLower.split(/\s+/)
    let matchCount = 0
    let firstMatch: Element | null = null

    spans.forEach((span) => {
      const text = span.textContent?.toLowerCase() || ''

      // Check if span contains any part of the search text
      const matches = searchWords.some(word =>
        word.length > 2 && text.includes(word)
      ) || text.includes(searchLower)

      if (matches) {
        span.classList.add(isActive ? 'entity-highlight-active' : 'entity-highlight')
        matchCount++
        if (!firstMatch) firstMatch = span
      }
    })

    // Scroll to first match
    if (firstMatch) {
      firstMatch.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }

    return matchCount
  }, [])

  // Clear all highlights
  const clearHighlights = useCallback(() => {
    if (!containerRef.current) return
    const highlights = containerRef.current.querySelectorAll('.entity-highlight, .entity-highlight-active')
    highlights.forEach(el => el.classList.remove('entity-highlight', 'entity-highlight-active'))
    setSearchResults(0)
    setSelectedEntity(null)
  }, [])

  const resolvedHeight = typeof height === 'number' ? `${height}px` : height

  // Filter relevant entities
  const relevantEntities = entities.filter(e => {
    const cls = (e.class || '').toLowerCase()
    return Object.keys(ENTITY_COLORS).includes(cls) || cls !== 'default'
  })

  const groupedEntities = groupEntities(relevantEntities)

  const onDocumentLoadSuccess = useCallback(({ numPages }: { numPages: number }) => {
    setNumPages(numPages)
    setIsLoading(false)
    setError(null)
  }, [])

  const onDocumentLoadError = useCallback((error: Error) => {
    console.error('Error loading PDF:', error)
    setError('Error loading PDF document')
    setIsLoading(false)
  }, [])

  const goToPrevPage = useCallback(() => setPageNumber(prev => Math.max(1, prev - 1)), [])
  const goToNextPage = useCallback(() => setPageNumber(prev => Math.min(numPages, prev + 1)), [numPages])
  const goToPage = useCallback((page: number) => {
    if (page >= 1 && page <= numPages) setPageNumber(page)
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

  const handleEntityClick = useCallback((entity: DocumentEntity) => {
    setSelectedEntity(entity)

    // Highlight in PDF with a small delay to ensure TextLayer is rendered
    setTimeout(() => {
      const count = highlightTextInPdf(entity.text, true)
      setSearchResults(count)
    }, 100)

    // Toggle in highlighted set
    const entityId = `${entity.class}-${entity.text}`
    setHighlightedEntities(prev => {
      const newSet = new Set(prev)
      if (newSet.has(entityId)) {
        newSet.delete(entityId)
      } else {
        newSet.add(entityId)
      }
      return newSet
    })
  }, [highlightTextInPdf])

  if (error) {
    return (
      <Card className={cn("h-full flex items-center justify-center p-6", className)}>
        <div className="text-center">
          <p className="text-red-500 mb-4">Error loading PDF</p>
          <Button onClick={() => window.location.reload()} variant="outline">
            Try Again
          </Button>
        </div>
      </Card>
    )
  }

  return (
    <div ref={containerRef} className={cn("pdf-entity-viewer flex flex-col bg-background border rounded-lg overflow-hidden", className)} style={{ height: resolvedHeight }}>
      {/* Toolbar */}
      {showToolbar && (
        <div className="flex items-center justify-between p-3 border-b bg-muted/30">
          {/* Navigation */}
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
                max={numPages}
              />
              <span className="text-sm text-muted-foreground">/ {numPages}</span>
            </div>
            <Button variant="outline" size="sm" onClick={goToNextPage} disabled={pageNumber >= numPages}>
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>

          {/* View Mode Selector */}
          {relevantEntities.length > 0 && (
            <Tabs value={viewMode} onValueChange={(v) => setViewMode(v as ViewMode)}>
              <TabsList className="h-8">
                <TabsTrigger value="off" className="h-7 px-2">
                  <EyeOff className="h-3.5 w-3.5" />
                </TabsTrigger>
                <TabsTrigger value="sidebar" className="h-7 px-2">
                  <List className="h-3.5 w-3.5" />
                </TabsTrigger>
                <TabsTrigger value="highlight" className="h-7 px-2">
                  <Highlighter className="h-3.5 w-3.5" />
                </TabsTrigger>
                <TabsTrigger value="badges" className="h-7 px-2">
                  <Tag className="h-3.5 w-3.5" />
                </TabsTrigger>
              </TabsList>
            </Tabs>
          )}

          {/* Zoom & Actions */}
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

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* PDF Viewer */}
        <div className={cn(
          "flex-1 overflow-auto bg-muted/50 flex justify-center p-4",
          viewMode === 'sidebar' && relevantEntities.length > 0 ? 'pr-0' : ''
        )}>
          {isLoading && (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="h-8 w-8 animate-spin" />
              <span className="ml-2">Loading PDF...</span>
            </div>
          )}

          <div ref={pageRef} className="relative">
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

            {/* Highlight Overlay Mode */}
            {viewMode === 'highlight' && relevantEntities.length > 0 && (
              <div className="absolute inset-0 pointer-events-none">
                {relevantEntities.map((entity, idx) => {
                  const colors = getEntityColor(entity.class)
                  const isHighlighted = highlightedEntities.has(`${entity.class}-${entity.text}`)
                  // Position highlights based on entity index (simplified - would need real coordinates)
                  const top = 50 + (idx * 30) % 400
                  const left = 20 + (idx * 50) % 300
                  return (
                    <div
                      key={idx}
                      className={cn(
                        "absolute px-1 py-0.5 rounded text-xs pointer-events-auto cursor-pointer transition-all",
                        colors.bg,
                        colors.text,
                        isHighlighted ? 'ring-2 ring-offset-1 ring-primary' : 'opacity-70 hover:opacity-100'
                      )}
                      style={{ top: `${top}px`, left: `${left}px` }}
                      onClick={() => handleEntityClick(entity)}
                    >
                      {entity.text}
                    </div>
                  )
                })}
              </div>
            )}

            {/* Badges Mode */}
            {viewMode === 'badges' && relevantEntities.length > 0 && (
              <div className="absolute top-0 -right-4 w-48 space-y-1">
                {relevantEntities.slice(0, 15).map((entity, idx) => {
                  const colors = getEntityColor(entity.class)
                  const isHighlighted = highlightedEntities.has(`${entity.class}-${entity.text}`)
                  return (
                    <div
                      key={idx}
                      className={cn(
                        "flex items-center gap-1.5 px-2 py-1 rounded-l text-xs cursor-pointer transition-all border-l-2",
                        colors.bg,
                        colors.border,
                        colors.text,
                        isHighlighted ? 'ring-1 ring-primary' : 'hover:translate-x-1'
                      )}
                      onClick={() => handleEntityClick(entity)}
                    >
                      {getEntityIcon(entity.class)}
                      <span className="truncate">{entity.text}</span>
                    </div>
                  )
                })}
                {relevantEntities.length > 15 && (
                  <div className="text-xs text-muted-foreground pl-2">
                    +{relevantEntities.length - 15} more
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Sidebar Mode */}
        {viewMode === 'sidebar' && relevantEntities.length > 0 && (
          <div className="w-72 border-l bg-background flex flex-col">
            <div className="p-3 border-b">
              <h3 className="font-semibold text-sm flex items-center gap-2">
                <Eye className="h-4 w-4" />
                Entidades Detectadas
              </h3>
              <p className="text-xs text-muted-foreground mt-1">
                {relevantEntities.length} entidades en {Object.keys(groupedEntities).length} categorías
              </p>
            </div>
            <ScrollArea className="flex-1">
              <div className="p-3 space-y-4">
                {Object.entries(groupedEntities).map(([category, categoryEntities]) => {
                  const colors = getEntityColor(category)
                  return (
                    <div key={category}>
                      <div className={cn("flex items-center gap-2 mb-2 px-2 py-1 rounded", colors.bg)}>
                        {getEntityIcon(category)}
                        <span className={cn("text-xs font-medium uppercase", colors.text)}>
                          {getEntityLabel(category)}
                        </span>
                        <Badge variant="secondary" className="ml-auto h-5 text-xs">
                          {categoryEntities.length}
                        </Badge>
                      </div>
                      <div className="space-y-1 pl-1">
                        {categoryEntities.map((entity, idx) => {
                          const isHighlighted = highlightedEntities.has(`${entity.class}-${entity.text}`)
                          const isSelected = selectedEntity?.text === entity.text && selectedEntity?.class === entity.class
                          return (
                            <div
                              key={idx}
                              className={cn(
                                "px-2 py-1.5 rounded text-sm cursor-pointer transition-colors",
                                "hover:bg-muted",
                                isSelected && "bg-muted ring-1 ring-primary",
                                isHighlighted && "bg-primary/10"
                              )}
                              onClick={() => handleEntityClick(entity)}
                            >
                              <div className="font-medium truncate">{entity.text}</div>
                              {entity.attributes?.role && (
                                <div className="text-xs text-muted-foreground truncate">
                                  {entity.attributes.role}
                                </div>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  )
                })}
              </div>
            </ScrollArea>

            {/* Selected Entity Detail */}
            {selectedEntity && (
              <div className="border-t p-3 bg-muted/30">
                <div className="flex items-center justify-between mb-2">
                  <h4 className="text-xs font-medium text-muted-foreground">Detalle</h4>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 w-6 p-0"
                    onClick={clearHighlights}
                  >
                    <X className="h-3 w-3" />
                  </Button>
                </div>
                <div className="space-y-1">
                  <div className="text-sm font-medium">{selectedEntity.text}</div>
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="text-xs">
                      {getEntityLabel(selectedEntity.class)}
                    </Badge>
                    {searchResults > 0 && (
                      <Badge variant="secondary" className="text-xs">
                        <Search className="h-2.5 w-2.5 mr-1" />
                        {searchResults} coincidencias
                      </Badge>
                    )}
                  </div>
                  {selectedEntity.attributes && Object.entries(selectedEntity.attributes)
                    .filter(([k]) => !['confidence', 'provider', 'model'].includes(k))
                    .map(([key, value]) => (
                      <div key={key} className="text-xs text-muted-foreground">
                        <span className="font-medium">{key}:</span> {String(value)}
                      </div>
                    ))
                  }
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Status Bar */}
      {showToolbar && (
        <div className="flex items-center justify-between px-3 py-1.5 border-t bg-muted/30 text-xs text-muted-foreground">
          <span>{fileName}</span>
          <div className="flex items-center gap-3">
            {relevantEntities.length > 0 && (
              <span className="flex items-center gap-1">
                <Tag className="h-3 w-3" />
                {relevantEntities.length} entidades
              </span>
            )}
            <span>Página {pageNumber} de {numPages}</span>
          </div>
        </div>
      )}
    </div>
  )
}
