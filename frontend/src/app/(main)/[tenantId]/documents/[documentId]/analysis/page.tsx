'use client'

import React, { useState, useEffect, useCallback } from 'react'
import { useParams } from 'next/navigation'
import LegalAnalysisViewer, { AnalysisItem } from '@/components/documents/legal-analysis-viewer'
import { useDocumentService } from '@/lib/services/document.service'
import { Loader2, AlertCircle } from 'lucide-react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Document } from '@/lib/types'

export default function AnalysisPage() {
    const params = useParams()
    const documentId = params.documentId as string
    const documentService = useDocumentService()

    const [document, setDocument] = useState<Document | null>(null)
    const [pdfUrl, setPdfUrl] = useState<string | null>(null)
    const [isLoadingDocument, setIsLoadingDocument] = useState(true)
    const [isLoadingPdf, setIsLoadingPdf] = useState(false)
    const [error, setError] = useState<string | null>(null)

    // Load document metadata
    const loadDocument = useCallback(async () => {
        try {
            setIsLoadingDocument(true)
            setError(null)

            const result = await documentService.getDocument(documentId)

            if ('error' in result && result.error) {
                setError(result.error)
            } else if (result.data) {
                setDocument(result.data)
            }
        } catch (err) {
            console.error('Error loading document:', err)
            setError('Error inesperado al cargar el documento')
        } finally {
            setIsLoadingDocument(false)
        }
    }, [documentId, documentService])

    // Load PDF blob
    const loadPdfUrl = useCallback(async () => {
        if (!document) return

        try {
            setIsLoadingPdf(true)
            console.log('[AnalysisPage] Loading PDF for document:', document.id, 'file_type:', document.file_type)

            let result

            if (document.file_type === 'pdf' || document.mime_type === 'application/pdf') {
                result = await documentService.downloadDocument(document.id)
            } else {
                // For non-PDFs, fetch the converted PDF
                result = await documentService.downloadConvertedDocument(document.id)
            }

            if ('blob' in result && result.blob) {
                console.log('[AnalysisPage] Received blob, type:', result.blob.type, 'size:', result.blob.size)
                const localUrl = URL.createObjectURL(result.blob)
                setPdfUrl(localUrl)
                console.log('[AnalysisPage] Created object URL:', localUrl)
            } else if ('error' in result) {
                setError(result.error || 'Error al cargar el PDF')
            }
        } catch (err) {
            console.error('[AnalysisPage] Error loading PDF:', err)
            setError('Error inesperado al cargar el PDF')
        } finally {
            setIsLoadingPdf(false)
        }
    }, [document, documentService])

    // Load document on mount
    useEffect(() => {
        loadDocument()
    }, [loadDocument])

    // Load PDF when document is available
    useEffect(() => {
        if (document && !pdfUrl && !isLoadingPdf) {
            loadPdfUrl()
        }
    }, [document, pdfUrl, isLoadingPdf, loadPdfUrl])

    // Cleanup blob URL on unmount or when URL changes
    useEffect(() => {
        return () => {
            if (pdfUrl && pdfUrl.startsWith('blob:')) {
                URL.revokeObjectURL(pdfUrl)
            }
        }
    }, [pdfUrl])

    // Mock Data matching the user's screenshot
    const mockAnalysisItems: AnalysisItem[] = [
        {
            id: '1',
            type: 'risk',
            severity: 'high',
            title: 'Riesgo Alto',
            description: 'La cláusula de indemnización 8.2 carece de un límite de responsabilidad explícito.',
            pageNumber: 1,
            highlight: {
                x: 10,
                y: 45,
                width: 80,
                height: 12
            }
        },
        {
            id: '2',
            type: 'recommendation',
            title: 'Recomendación',
            description: 'Añadir un límite de responsabilidad monetaria equivalente a las tarifas pagadas en los últimos 12 meses.',
            pageNumber: 1,
            highlight: {
                x: 10,
                y: 60,
                width: 80,
                height: 10
            }
        }
    ]

    if (isLoadingDocument || isLoadingPdf) {
        return (
            <div className="h-screen flex items-center justify-center">
                <div className="text-center">
                    <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4" />
                    <p className="text-muted-foreground">
                        {isLoadingDocument ? 'Cargando documento...' : 'Cargando PDF...'}
                    </p>
                </div>
            </div>
        )
    }

    if (error) {
        return (
            <div className="h-screen flex items-center justify-center p-4">
                <Alert variant="destructive" className="max-w-md">
                    <AlertCircle className="h-4 w-4" />
                    <AlertDescription>{error}</AlertDescription>
                </Alert>
            </div>
        )
    }

    if (!pdfUrl) {
        return (
            <div className="h-screen flex items-center justify-center">
                <div className="text-center">
                    <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4" />
                    <p className="text-muted-foreground">Preparando visor...</p>
                </div>
            </div>
        )
    }

    return (
        <div className="h-screen w-full overflow-hidden bg-gray-900">
            <LegalAnalysisViewer
                url={pdfUrl}
                fileName={document?.filename || 'document.pdf'}
                analysisItems={mockAnalysisItems}
            />
        </div>
    )
}
