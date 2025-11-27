'use client'

import React, { useState, useEffect, useCallback } from 'react'
import { useParams } from 'next/navigation'
import LegalAnalysisViewer, { AnalysisItem } from '@/components/documents/legal-analysis-viewer'
import { useDocumentService } from '@/lib/services/document.service'
import { Loader2, AlertCircle } from 'lucide-react'
import { Alert, AlertDescription } from '@/components/ui/alert'

export default function AnalysisPage() {
    const params = useParams()
    const documentId = params.documentId as string
    const documentService = useDocumentService()

    const [pdfUrl, setPdfUrl] = useState<string | null>(null)
    const [isLoading, setIsLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    const loadDocument = useCallback(async () => {
        try {
            setIsLoading(true)
            setError(null)

            const result = await documentService.downloadDocument(documentId)

            // Type guard to check if result has blob
            if ('blob' in result && result.blob) {
                const url = URL.createObjectURL(result.blob)
                setPdfUrl(url)
            } else if ('error' in result) {
                setError(result.error || 'Error al cargar el documento')
            }
        } catch (err) {
            console.error('Error loading document:', err)
            setError('Error inesperado al cargar el documento')
        } finally {
            setIsLoading(false)
        }
    }, [documentId, documentService])

    useEffect(() => {
        loadDocument()
    }, [loadDocument])

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

    if (isLoading) {
        return (
            <div className="h-screen flex items-center justify-center">
                <div className="text-center">
                    <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4" />
                    <p className="text-muted-foreground">Cargando documento...</p>
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

    // Fallback if no PDF loaded (for testing without backend)
    const urlToUse = pdfUrl || 'https://raw.githubusercontent.com/mozilla/pdf.js/ba2edeae/web/compressed.tracemonkey-pldi-09.pdf'

    return (
        <div className="h-screen w-full overflow-hidden">
            <LegalAnalysisViewer
                url={urlToUse}
                analysisItems={mockAnalysisItems}
            />
        </div>
    )
}
