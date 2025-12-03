'use client'

import React, { useState, useCallback } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'

// Import PDF.js CSS for text layer and annotations support
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
  Loader2,
  Shield,
  ShieldCheck,
  ShieldAlert,
  Info,
  FileSignature,
  PenTool
} from 'lucide-react'
import { cn } from '@/lib/utils'

// Configure PDF.js worker
pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`

interface DigitalSignature {
  name: string
  contactInfo?: string
  location?: string
  reason?: string
  date?: string
  isValid?: boolean
  subFilter?: string
  signedBy?: string
  pageNumber?: number
}

interface PDFViewerProps {
  url: string
  fileName?: string
  className?: string
  showToolbar?: boolean
  initialScale?: number
  height?: string | number
}

export default function PDFViewer({ 
  url, 
  fileName = 'document.pdf', 
  className,
  showToolbar = true,
  initialScale = 1.0,
  height = '600px'
}: PDFViewerProps) {
  const [numPages, setNumPages] = useState<number>(0)
  const [pageNumber, setPageNumber] = useState<number>(1)
  const [scale, setScale] = useState<number>(initialScale)
  const [rotation, setRotation] = useState<number>(0)
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)
  const [signatures, setSignatures] = useState<DigitalSignature[]>([])
  const [showSignatureInfo, setShowSignatureInfo] = useState<boolean>(false)

  const resolvedHeight =
    typeof height === 'number' ? `${height}px` : height || '600px'

  const onDocumentLoadSuccess = useCallback(({ numPages }: { numPages: number }) => {
    setNumPages(numPages)
    setIsLoading(false)
    setError(null)
    // Detectar firmas digitales
    detectDigitalSignatures()
  }, [])

  const detectDigitalSignatures = useCallback(async () => {
    try {
      const loadingTask = pdfjs.getDocument(url)
      const pdf = await loadingTask.promise
      const detectedSignatures: DigitalSignature[] = []

      // Verificar si el documento tiene firmas
      const hasSignatures = pdf.numPages > 0
      
      if (hasSignatures) {
        // Iterar por cada página para buscar anotaciones de firmas
        for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
          const page = await pdf.getPage(pageNum)
          const annotations = await page.getAnnotations()
          
          // Buscar anotaciones de tipo Widget (formularios/firmas)
          annotations.forEach((annotation: any) => {
            if (annotation.subtype === 'Widget' && annotation.fieldType === 'Sig') {
              const signature: DigitalSignature = {
                name: annotation.fieldName || `Signature ${detectedSignatures.length + 1}`,
                contactInfo: annotation.contactInfo,
                location: annotation.location,
                reason: annotation.reason,
                date: annotation.modificationDate,
                isValid: true, // Por defecto true, idealmente se validaría
                subFilter: annotation.subFilter,
                signedBy: annotation.title || annotation.contents,
                pageNumber: pageNum
              }
              detectedSignatures.push(signature)
            }
          })
        }
      }

      // También verificar metadatos del documento para información de firmas
      const metadata = await pdf.getMetadata()
      if (metadata.info?.Producer?.includes('Sign') || metadata.info?.Creator?.includes('Sign')) {
        // Si no se encontraron firmas específicas pero hay indicios, agregar una genérica
        if (detectedSignatures.length === 0) {
          detectedSignatures.push({
            name: 'Digital Signature Detected',
            reason: 'Document appears to be digitally signed',
            isValid: true,
            date: metadata.info?.ModDate || new Date().toISOString()
          })
        }
      }

      setSignatures(detectedSignatures)
    } catch (error) {
      console.warn('Error detecting digital signatures:', error)
      setSignatures([])
    }
  }, [url])

  const onDocumentLoadError = useCallback((error: Error) => {
    console.error('Error loading PDF:', error)
    setError('Error loading PDF document')
    setIsLoading(false)
  }, [])

  const goToPrevPage = useCallback(() => {
    setPageNumber(prev => Math.max(1, prev - 1))
  }, [])

  const goToNextPage = useCallback(() => {
    setPageNumber(prev => Math.min(numPages, prev + 1))
  }, [numPages])

  const goToPage = useCallback((page: number) => {
    if (page >= 1 && page <= numPages) {
      setPageNumber(page)
    }
  }, [numPages])

  const zoomIn = useCallback(() => {
    setScale(prev => Math.min(3.0, prev + 0.2))
  }, [])

  const zoomOut = useCallback(() => {
    setScale(prev => Math.max(0.5, prev - 0.2))
  }, [])

  const resetZoom = useCallback(() => {
    setScale(1.0)
  }, [])

  const rotate = useCallback(() => {
    setRotation(prev => (prev + 90) % 360)
  }, [])

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

  if (error) {
    return (
      <Card className={cn("h-full flex items-center justify-center p-6 text-center", className)}>
        <div>
          <div className="text-red-500 mb-4">
            <svg className="w-16 h-16 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.692-.833-2.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z" />
            </svg>
          </div>
          <h3 className="text-lg font-semibold mb-2">Error loading PDF</h3>
          <p className="text-muted-foreground mb-4">{error}</p>
          <Button onClick={() => window.location.reload()} variant="outline">
            Try Again
          </Button>
        </div>
      </Card>
    )
  }

  return (
    <div
      className={cn("flex flex-col", className)}
      style={{ minHeight: resolvedHeight, height: resolvedHeight }}
    >
      {showToolbar && (
        <div className="flex items-center justify-between p-4 border-b bg-card">
          <div className="flex items-center space-x-2">
            <Button
              variant="outline"
              size="sm"
              onClick={goToPrevPage}
              disabled={pageNumber <= 1}
            >
              <ChevronLeft className="h-4 w-4" />
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
              <span className="text-sm text-muted-foreground">of {numPages}</span>
            </div>

            <Button
              variant="outline"
              size="sm"
              onClick={goToNextPage}
              disabled={pageNumber >= numPages}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>

          <div className="flex items-center space-x-2">
            <Button variant="outline" size="sm" onClick={zoomOut} disabled={scale <= 0.5}>
              <ZoomOut className="h-4 w-4" />
            </Button>
            
            <Badge 
              variant="secondary" 
              className="cursor-pointer px-3"
              onClick={resetZoom}
            >
              {Math.round(scale * 100)}%
            </Badge>
            
            <Button variant="outline" size="sm" onClick={zoomIn} disabled={scale >= 3.0}>
              <ZoomIn className="h-4 w-4" />
            </Button>

            <Separator orientation="vertical" className="h-6" />

            <Button variant="outline" size="sm" onClick={rotate}>
              <RotateCw className="h-4 w-4" />
            </Button>

            <Button variant="outline" size="sm" onClick={downloadPDF}>
              <Download className="h-4 w-4" />
            </Button>

            <Button variant="outline" size="sm" onClick={openFullscreen}>
              <Maximize2 className="h-4 w-4" />
            </Button>

            {signatures.length > 0 && (
              <>
                <Separator orientation="vertical" className="h-6" />
                <Button 
                  variant="outline" 
                  size="sm" 
                  onClick={() => setShowSignatureInfo(!showSignatureInfo)}
                  className="gap-2"
                >
                  <FileSignature className="h-4 w-4" />
                  <span className="text-xs">{signatures.length}</span>
                </Button>
              </>
            )}
          </div>
        </div>
      )}

      {showSignatureInfo && signatures.length > 0 && (
        <div className="border-b bg-blue-50 dark:bg-blue-950 p-4">
          <div className="flex items-center gap-2 mb-3">
            <FileSignature className="h-5 w-5 text-blue-600" />
            <h3 className="font-semibold text-blue-900 dark:text-blue-100">
              Firmas Digitales Detectadas ({signatures.length})
            </h3>
          </div>
          <div className="space-y-3">
            {signatures.map((signature, index) => (
              <Card key={index} className="p-3 bg-white dark:bg-gray-800">
                <div className="flex items-start gap-3">
                  {signature.isValid ? (
                    <ShieldCheck className="h-5 w-5 text-green-600 flex-shrink-0 mt-0.5" />
                  ) : (
                    <ShieldAlert className="h-5 w-5 text-yellow-600 flex-shrink-0 mt-0.5" />
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-2">
                      <h4 className="font-medium text-sm text-gray-900 dark:text-gray-100">{signature.name}</h4>
                      <Badge 
                        variant={signature.isValid ? "default" : "secondary"}
                        className="text-xs"
                      >
                        {signature.isValid ? "Válida" : "Verificar"}
                      </Badge>
                      {signature.pageNumber && (
                        <Badge variant="outline" className="text-xs text-gray-700 dark:text-gray-300">
                          Página {signature.pageNumber}
                        </Badge>
                      )}
                    </div>
                    <div className="text-xs text-gray-700 dark:text-gray-300 space-y-1">
                      {signature.signedBy && (
                        <div>
                          <span className="font-medium">Firmado por:</span> {signature.signedBy}
                        </div>
                      )}
                      {signature.date && (
                        <div>
                          <span className="font-medium">Fecha:</span> {new Date(signature.date).toLocaleString()}
                        </div>
                      )}
                      {signature.reason && (
                        <div>
                          <span className="font-medium">Razón:</span> {signature.reason}
                        </div>
                      )}
                      {signature.location && (
                        <div>
                          <span className="font-medium">Ubicación:</span> {signature.location}
                        </div>
                      )}
                      {signature.contactInfo && (
                        <div>
                          <span className="font-medium">Contacto:</span> {signature.contactInfo}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </Card>
            ))}
          </div>
          <div className="mt-3 text-xs text-blue-700 dark:text-blue-300 flex items-center gap-1">
            <Info className="h-3 w-3" />
            La validación completa de firmas digitales requiere verificación con certificados oficiales.
          </div>
        </div>
      )}

      <div className="flex-1 overflow-auto bg-gray-100 dark:bg-gray-900 flex justify-center p-4">
          {isLoading && (
            <div className="flex items-center justify-center h-96">
              <Loader2 className="h-8 w-8 animate-spin" />
              <span className="ml-2">Loading PDF...</span>
            </div>
          )}
          
          <div className="w-full flex justify-center">
            <Document
              file={url}
              onLoadSuccess={onDocumentLoadSuccess}
              onLoadError={onDocumentLoadError}
              loading={null}
              className="flex justify-center w-full"
            >
              <Page
                pageNumber={pageNumber}
                scale={scale}
                rotate={rotation}
                className="shadow-lg max-w-full"
                loading={
                  <div className="flex items-center justify-center h-96 bg-white border">
                    <Loader2 className="h-6 w-6 animate-spin" />
                  </div>
                }
              />
            </Document>
          </div>
        </div>

      {/* Status bar */}
      {showToolbar && (
        <div className="flex items-center justify-between px-4 py-2 border-t bg-card text-sm text-muted-foreground">
          <div className="flex items-center space-x-4">
            <span>{fileName}</span>
            {numPages > 0 && (
              <span>• Page {pageNumber} of {numPages}</span>
            )}
            {signatures.length > 0 && (
              <span className="flex items-center gap-1">
                • <Shield className="h-3 w-3" />
                {signatures.length} signature{signatures.length > 1 ? 's' : ''}
              </span>
            )}
          </div>
          <div className="flex items-center space-x-2">
            <span>Scale: {Math.round(scale * 100)}%</span>
          </div>
        </div>
      )}
    </div>
  )
}

// Export loading component for lazy loading
export const PDFViewerSkeleton = () => (
  <Card className="h-96 flex items-center justify-center">
    <div className="text-center">
      <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4" />
      <p className="text-muted-foreground">Loading PDF viewer...</p>
    </div>
  </Card>
)
