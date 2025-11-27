'use client'

import React from 'react'
import { useParams } from 'next/navigation'
import LegalAnalysisViewer, { AnalysisItem } from '@/components/documents/legal-analysis-viewer'
import { useDocumentService } from '@/lib/services/document.service'
import { Loader2 } from 'lucide-react'

export default function AnalysisPage() {
    const params = useParams()
    const documentId = params.documentId as string
    const documentService = useDocumentService()

    const [pdfUrl, setPdfUrl] = React.useState<string | null>(null)
    const [isLoading, setIsLoading] = React.useState(true)

    React.useEffect(() => {
        const loadDocument = async () => {
            try {
                // In a real app, we would fetch the document URL securely
                // For this demo, we'll try to download it
                const result = await documentService.downloadDocument(documentId)
                if (result.blob) {
                    setPdfUrl(URL.createObjectURL(result.blob))
                }
            } catch (error) {
                console.error('Error loading document:', error)
            } finally {
                setIsLoading(false)
            }
        }

        loadDocument()

        return () => {
            if (pdfUrl) URL.revokeObjectURL(pdfUrl)
        }
    }, [documentId])

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
                <Loader2 className="h-8 w-8 animate-spin" />
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
