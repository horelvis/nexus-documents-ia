'use client'

import React, { useState, useEffect, useCallback, useRef, Suspense } from 'react'
import { useParams, useSearchParams, useRouter } from 'next/navigation'
import { useDocumentService } from '@/lib/services/document.service'
import {
    useEmmaService,
    AnnotatedPDFResponse,
    PDFAnnotation,
    AnalysisStreamEvent,
    StoredAnalysisResult
} from '@/lib/services/emma.service'
import {
    Loader2, AlertCircle, Brain, RefreshCw, AlertTriangle, Lightbulb,
    FileText, List, CheckCircle2, Clock, Bot, FileSearch, Sparkles,
    ClipboardCheck, Highlighter, ChevronDown, ChevronUp, ArrowLeft
} from 'lucide-react'
import { useTranslation } from '@/lib/i18n/hooks'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Progress } from '@/components/ui/progress'
import { Document as DocumentType } from '@/lib/types'
import { cn } from '@/lib/utils'
import { FindingDetailDialog, type AnalysisFinding } from '@/components/analysis/finding-detail-dialog'
import { PDFAnnotationViewer } from '@/components/analysis/pdf-annotation-viewer'

// Step item for the progress chat
interface ProgressStep {
    id: string
    type: 'info' | 'agent' | 'finding' | 'complete' | 'error'
    icon: React.ReactNode
    title: string
    description?: string
    status: 'pending' | 'running' | 'completed' | 'error'
    timestamp: Date
    findings?: Array<{
        type: string
        severity?: string
        title: string
    }>
    progress?: number
}

// Error parsing for better UX messages
interface ErrorInfo {
    title: string
    userMessage: string
    description: string
    type: 'network' | 'timeout' | 'server' | 'llm' | 'unknown'
}

function parseErrorMessage(rawError: string): ErrorInfo {
    const lowerError = rawError.toLowerCase()

    // Network errors
    if (lowerError.includes('failed to fetch') ||
        lowerError.includes('network error') ||
        lowerError.includes('err_network') ||
        lowerError.includes('net::err')) {
        return {
            title: 'Error de conexión',
            userMessage: 'No se pudo conectar con el servidor de análisis',
            description: 'Verifica tu conexión a internet o que el servicio esté disponible. Puedes reintentar en unos segundos.',
            type: 'network'
        }
    }

    // Timeout errors
    if (lowerError.includes('timeout') || lowerError.includes('timed out') || lowerError.includes('aborted')) {
        return {
            title: 'Tiempo de espera excedido',
            userMessage: 'El análisis tardó demasiado en completarse',
            description: 'El documento puede ser muy extenso o el servidor está ocupado. Intenta de nuevo en unos minutos.',
            type: 'timeout'
        }
    }

    // LLM / AI model errors
    if (lowerError.includes('context length') || lowerError.includes('token') ||
        lowerError.includes('model') || lowerError.includes('llm') ||
        lowerError.includes('vllm') || lowerError.includes('inference')) {
        return {
            title: 'Error en el modelo de IA',
            userMessage: 'El modelo de análisis no pudo procesar el documento',
            description: lowerError.includes('context length')
                ? 'El documento excede la capacidad del modelo. Intenta con un documento más corto o contacta soporte.'
                : 'Hubo un problema con el servicio de inteligencia artificial. Por favor, reintenta.',
            type: 'llm'
        }
    }

    // Server errors (5xx)
    if (lowerError.includes('500') || lowerError.includes('502') ||
        lowerError.includes('503') || lowerError.includes('504') ||
        lowerError.includes('internal server')) {
        return {
            title: 'Error del servidor',
            userMessage: 'El servidor encontró un problema al procesar la solicitud',
            description: 'Esto puede ser temporal. Por favor, espera unos segundos y reintenta el análisis.',
            type: 'server'
        }
    }

    // Authentication / Authorization errors
    if (lowerError.includes('401') || lowerError.includes('403') ||
        lowerError.includes('unauthorized') || lowerError.includes('forbidden')) {
        return {
            title: 'Error de autenticación',
            userMessage: 'No tienes permiso para realizar este análisis',
            description: 'Tu sesión puede haber expirado. Intenta cerrar sesión y volver a iniciar.',
            type: 'server'
        }
    }

    // Document not found
    if (lowerError.includes('404') || lowerError.includes('not found') ||
        lowerError.includes('no encontr')) {
        return {
            title: 'Documento no encontrado',
            userMessage: 'No se encontró el documento para analizar',
            description: 'El documento puede haber sido eliminado o movido. Verifica que exista y vuelve a intentar.',
            type: 'server'
        }
    }

    // If error contains Spanish detail from backend, use it
    if (rawError.includes('Error de análisis:')) {
        const detail = rawError.replace('Error de análisis:', '').trim()
        return {
            title: 'Error en el análisis',
            userMessage: detail,
            description: 'El servidor reportó un problema específico. Revisa los detalles y reintenta si es posible.',
            type: 'server'
        }
    }

    // Unknown error - show the raw message
    return {
        title: 'Error inesperado',
        userMessage: rawError || 'Ocurrió un error desconocido',
        description: 'Por favor, intenta de nuevo. Si el problema persiste, contacta al soporte técnico.',
        type: 'unknown'
    }
}

// Agent icons mapping
const AGENT_ICONS: Record<string, React.ReactNode> = {
    'ContractAgent': <FileSearch className="h-4 w-4" />,
    'LaborAgent': <ClipboardCheck className="h-4 w-4" />,
    'ComplianceAgent': <AlertTriangle className="h-4 w-4" />,
    'FiscalAgent': <FileText className="h-4 w-4" />,
    'PrivacyAgent': <FileSearch className="h-4 w-4" />,
    'SummarizerAgent': <Sparkles className="h-4 w-4" />,
    'AnalystAgent': <Brain className="h-4 w-4" />,
}

// Agent descriptions for better UX
const AGENT_DESCRIPTIONS: Record<string, string> = {
    'ContractAgent': 'Análisis de cláusulas contractuales',
    'LaborAgent': 'Revisión laboral (período de prueba, jornada, Art. 14 ET)',
    'ComplianceAgent': 'Verificación de cumplimiento normativo',
    'FiscalAgent': 'Análisis de implicaciones fiscales',
    'PrivacyAgent': 'Revisión de protección de datos (RGPD/LOPD)',
    'SummarizerAgent': 'Generación de resumen ejecutivo',
    'AnalystAgent': 'Análisis documental general',
}

// Helper to get agent description
const getAgentDescription = (agentName: string): string => {
    return AGENT_DESCRIPTIONS[agentName] || agentName
}

function AnalysisPageContent() {
    const params = useParams()
    const searchParams = useSearchParams()
    const router = useRouter()
    const { t } = useTranslation()
    const documentId = params.documentId as string
    const tenantId = params.tenantId as string
    const jobId = searchParams?.get('jobId') || null

    // Debug: log jobId to verify it's being read
    useEffect(() => {
        console.log('[AnalysisPage] jobId from URL:', jobId)
    }, [jobId])
    const documentService = useDocumentService()
    const emmaService = useEmmaService()

    const [document, setDocument] = useState<DocumentType | null>(null)
    const [pdfFile, setPdfFile] = useState<File | null>(null)
    const [analysisResult, setAnalysisResult] = useState<AnnotatedPDFResponse | null>(null)
    const [storedAnalysis, setStoredAnalysis] = useState<StoredAnalysisResult | null>(null)
    // If jobId exists, we need to check for stored analysis before auto-running
    const [isLoadingStoredAnalysis, setIsLoadingStoredAnalysis] = useState(!!jobId)
    const [storedAnalysisChecked, setStoredAnalysisChecked] = useState(!jobId) // true if no jobId (skip check)

    // PDF view state
    const [pdfUrl, setPdfUrl] = useState<string | null>(null)
    const [annotatedPdfUrl, setAnnotatedPdfUrl] = useState<string | null>(null)

    const [pageNumber, setPageNumber] = useState<number>(1)
    const [selectedAnnotationId, setSelectedAnnotationId] = useState<string | null>(null)
    const [sidebarTab, setSidebarTab] = useState<'page' | 'all'>('all')
    const [selectedFinding, setSelectedFinding] = useState<AnalysisFinding | null>(null)

    const [isLoadingDocument, setIsLoadingDocument] = useState(true)
    const [isAnalyzing, setIsAnalyzing] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [analysisError, setAnalysisError] = useState<string | null>(null)

    // Progress tracking
    const [progressSteps, setProgressSteps] = useState<ProgressStep[]>([])
    const [overallProgress, setOverallProgress] = useState(0)
    const [currentPlan, setCurrentPlan] = useState<Array<{ index: number; description: string; agent: string }>>([])
    // Track which step index is currently executing (0-based)
    const [currentStepIndex, setCurrentStepIndex] = useState<number>(-1)
    // Track completed step indices
    const [completedStepIndices, setCompletedStepIndices] = useState<Set<number>>(new Set())
    // Track error step indices
    const [errorStepIndices, setErrorStepIndices] = useState<Set<number>>(new Set())
    // Toggle activity log expansion
    const [isActivityLogExpanded, setIsActivityLogExpanded] = useState(false)

    const progressScrollRef = useRef<HTMLDivElement>(null)
    const analysisStartedRef = useRef<boolean>(false)

    // No auto-scroll needed - logs are shown in reverse order (newest first)

    // Add a progress step
    const addStep = useCallback((step: Omit<ProgressStep, 'id' | 'timestamp'>) => {
        const newStep: ProgressStep = {
            ...step,
            id: `step-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
            timestamp: new Date()
        }
        setProgressSteps(prev => [...prev, newStep])
    }, [])

    // Update the last step of a certain type
    const updateLastStep = useCallback((type: string, updates: Partial<ProgressStep>) => {
        setProgressSteps(prev => {
            const idx = [...prev].reverse().findIndex(s => s.type === type && s.status === 'running')
            if (idx === -1) return prev
            const actualIdx = prev.length - 1 - idx
            const updated = [...prev]
            updated[actualIdx] = { ...updated[actualIdx], ...updates }
            return updated
        })
    }, [])

    // Load document metadata and PDF
    const loadDocument = useCallback(async () => {
        setIsLoadingDocument(true)
        setError(null)

        try {
            const result = await documentService.getDocument(documentId)

            if ('error' in result && result.error) {
                setError(result.error)
                return
            }

            if (result.data) {
                setDocument(result.data)

                let downloadResult
                if (result.data.file_type === 'pdf' || result.data.mime_type === 'application/pdf') {
                    downloadResult = await documentService.downloadDocument(result.data.id)
                } else {
                    downloadResult = await documentService.downloadConvertedDocument(result.data.id)
                }

                if ('blob' in downloadResult && downloadResult.blob) {
                    const file = new File(
                        [downloadResult.blob],
                        result.data.filename || 'document.pdf',
                        { type: 'application/pdf' }
                    )
                    setPdfFile(file)
                } else if ('error' in downloadResult) {
                    setError(downloadResult.error || 'Error al cargar el PDF')
                }
            }
        } catch (err) {
            console.error('Error loading document:', err)
            setError('Error inesperado al cargar el documento')
        } finally {
            setIsLoadingDocument(false)
        }
    }, [documentId, documentService])

    // Run analysis with streaming progress
    const runAnalysis = useCallback(async () => {
        if (!document || !pdfFile) return

        setIsAnalyzing(true)
        setAnalysisError(null)
        setProgressSteps([])
        setOverallProgress(0)
        setCurrentPlan([])
        setCurrentStepIndex(-1)
        setCompletedStepIndices(new Set())
        setErrorStepIndices(new Set())
        setIsActivityLogExpanded(false)
        setAnalysisResult(null)

        try {
            const streamGenerator = emmaService.analyzeDocumentWithAnnotationsStream(
                documentId,
                tenantId,
                'legal',
                pdfFile
            )

            for await (const event of streamGenerator) {
                const { event: eventType, data } = event

                // Debug logging for SSE events
                console.log(`[Analysis SSE] Event: ${eventType}`, {
                    progress: data.progress,
                    step_index: data.step_index,
                    step: data.step,
                    agent: data.agent,
                    total_steps: data.total_steps,
                    message: data.message?.substring(0, 100)
                })

                // Update progress
                if (data.progress !== undefined) {
                    setOverallProgress(data.progress)
                }

                switch (eventType) {
                    case 'start':
                        addStep({
                            type: 'info',
                            icon: <Brain className="h-4 w-4" />,
                            title: 'Iniciando análisis',
                            description: data.message,
                            status: 'completed'
                        })
                        break

                    case 'extracting':
                        addStep({
                            type: 'info',
                            icon: <FileText className="h-4 w-4" />,
                            title: 'Extrayendo texto',
                            description: data.message,
                            status: 'running'
                        })
                        break

                    case 'extracted':
                        updateLastStep('info', { status: 'completed' })
                        addStep({
                            type: 'info',
                            icon: <CheckCircle2 className="h-4 w-4 text-green-500" />,
                            title: `${data.pages} páginas extraídas`,
                            description: `${data.chars?.toLocaleString()} caracteres procesados`,
                            status: 'completed'
                        })
                        break

                    case 'plan_created':
                        updateLastStep('info', { status: 'completed' })
                        if (data.steps) {
                            console.log('[Analysis SSE] Plan created with steps:', data.steps)
                            setCurrentPlan(data.steps)
                            addStep({
                                type: 'info',
                                icon: <List className="h-4 w-4" />,
                                title: `Plan creado: ${data.total_steps} pasos`,
                                description: data.steps.map((s: { agent: string }) => s.agent).join(' → '),
                                status: 'completed'
                            })
                        }
                        break

                    case 'step_start':
                        // Track which step is currently executing
                        if (data.step_index !== undefined) {
                            console.log(`[Analysis SSE] Step START: step_index=${data.step_index}, agent=${data.agent}`)
                            setCurrentStepIndex(data.step_index)
                        }
                        addStep({
                            type: 'agent',
                            icon: AGENT_ICONS[data.agent || ''] || <Bot className="h-4 w-4" />,
                            title: data.description || data.agent || 'Agente',
                            description: data.message,
                            status: 'running',
                            progress: data.progress
                        })
                        break

                    case 'step_complete':
                        // Mark step as completed in the plan tracker
                        if (data.step_index !== undefined) {
                            console.log(`[Analysis SSE] Step COMPLETE: step_index=${data.step_index}, findings=${data.findings_count}`)
                            setCompletedStepIndices(prev => {
                                const newSet = new Set([...prev, data.step_index])
                                console.log(`[Analysis SSE] Completed indices: ${Array.from(newSet).join(', ')}`)
                                return newSet
                            })
                            setCurrentStepIndex(-1) // No step currently running
                        }
                        updateLastStep('agent', {
                            status: 'completed',
                            findings: data.findings?.map(f => ({
                                type: f.type,
                                severity: f.severity,
                                title: f.title
                            }))
                        })
                        if (data.findings_count && data.findings_count > 0) {
                            addStep({
                                type: 'finding',
                                icon: <AlertTriangle className="h-4 w-4 text-amber-500" />,
                                title: `${data.findings_count} hallazgos encontrados`,
                                description: getAgentDescription(data.agent || ''),
                                status: 'completed'
                            })
                        }
                        break

                    case 'step_error':
                        // Mark step as error in the plan tracker
                        if (data.step_index !== undefined) {
                            setErrorStepIndices(prev => new Set([...prev, data.step_index]))
                            setCurrentStepIndex(-1)
                        }
                        updateLastStep('agent', { status: 'error' })
                        addStep({
                            type: 'error',
                            icon: <AlertCircle className="h-4 w-4 text-red-500" />,
                            title: `Error: ${getAgentDescription(data.agent || '')}`,
                            description: data.error,
                            status: 'error'
                        })
                        break

                    case 'annotating':
                        updateLastStep('info', { status: 'completed' })
                        addStep({
                            type: 'info',
                            icon: <Highlighter className="h-4 w-4" />,
                            title: 'Añadiendo anotaciones al PDF',
                            description: data.message,
                            status: 'running'
                        })
                        break

                    case 'annotated':
                        updateLastStep('info', { status: 'completed' })
                        addStep({
                            type: 'info',
                            icon: <CheckCircle2 className="h-4 w-4 text-green-500" />,
                            title: `${data.total} anotaciones añadidas`,
                            description: `En ${data.pages} páginas`,
                            status: 'completed'
                        })
                        break

                    case 'complete':
                        addStep({
                            type: 'complete',
                            icon: <CheckCircle2 className="h-4 w-4 text-green-500" />,
                            title: 'Análisis completado',
                            description: `${data.total_annotations} anotaciones en el documento`,
                            status: 'completed'
                        })

                        // Build response from streaming data
                        if (data.analysis) {
                            const result: AnnotatedPDFResponse = {
                                annotated_pdf: data.annotated_pdf || '',
                                annotations: data.annotations || [],
                                pages_annotated: data.pages_annotated || 0,
                                total_annotations: data.total_annotations || 0,
                                failed_annotations: data.failed_annotations || 0,
                                analysis: {
                                    document_id: data.analysis.document_id,
                                    summary: data.analysis.summary,
                                    risks: data.analysis.risks.map(r => ({
                                        id: r.id,
                                        type: r.type as 'risk',
                                        severity: r.severity as 'high' | 'medium' | 'low',
                                        title: r.title,
                                        description: r.description,
                                        quote: r.quote,
                                        clause: r.clause
                                    })),
                                    recommendations: data.analysis.recommendations.map(r => ({
                                        id: r.id,
                                        type: r.type as 'recommendation',
                                        title: r.title,
                                        description: r.description,
                                        quote: r.quote,
                                        priority: r.priority as 'high' | 'medium' | 'low'
                                    })),
                                    confidence_score: data.analysis.confidence_score,
                                    analysis_type: data.analysis.analysis_type
                                }
                            }
                            setAnalysisResult(result)
                        }
                        break

                    case 'error':
                        addStep({
                            type: 'error',
                            icon: <AlertCircle className="h-4 w-4 text-red-500" />,
                            title: 'Error en el análisis',
                            description: data.error,
                            status: 'error'
                        })
                        setAnalysisError(data.error || 'Error desconocido')
                        break
                }
            }
        } catch (err) {
            console.error('Error analyzing document:', err)
            const rawError = err instanceof Error ? err.message : String(err)

            // Parse and improve error message for better UX
            const errorInfo = parseErrorMessage(rawError)

            setAnalysisError(errorInfo.userMessage)
            addStep({
                type: 'error',
                icon: <AlertCircle className="h-4 w-4 text-red-500" />,
                title: errorInfo.title,
                description: errorInfo.description,
                status: 'error'
            })
        } finally {
            setIsAnalyzing(false)
        }
    }, [document, pdfFile, documentId, tenantId, emmaService, addStep, updateLastStep])

    // Load document on mount
    useEffect(() => {
        loadDocument()
    }, [loadDocument])

    // Load stored analysis if jobId is provided
    useEffect(() => {
        if (!jobId) {
            setIsLoadingStoredAnalysis(false)
            setStoredAnalysisChecked(true)
            return
        }

        const loadStoredAnalysis = async () => {
            console.log('[AnalysisPage] Loading stored analysis for jobId:', jobId)
            setIsLoadingStoredAnalysis(true)
            try {
                const stored = await emmaService.getStoredAnalysis(jobId)
                console.log('[AnalysisPage] Stored analysis result:', stored?.status)

                if (stored) {
                    // Always prevent auto-run if we have a jobId with an existing analysis
                    // (whether completed, in_progress, or pending)
                    analysisStartedRef.current = true

                    if (stored.status === 'completed') {
                        setStoredAnalysis(stored)
                        // Convert stored analysis to AnnotatedPDFResponse format
                        const result: AnnotatedPDFResponse = {
                            annotated_pdf: '', // We don't have the PDF bytes stored
                            annotations: stored.annotations || [],
                            pages_annotated: new Set(stored.annotations?.map(a => a.page_number) || []).size,
                            total_annotations: stored.annotations?.length || 0,
                            failed_annotations: 0,
                            analysis: {
                                document_id: stored.document_id,
                                summary: stored.summary || '',
                                risks: stored.risks || [],
                                recommendations: stored.recommendations || [],
                                confidence_score: stored.confidence_score || 0,
                                analysis_type: stored.analysis_type,
                            }
                        }
                        setAnalysisResult(result)
                        console.log('[AnalysisPage] Stored analysis loaded successfully')
                    } else if (stored.status === 'in_progress' || stored.status === 'pending') {
                        // Analysis is still running - show waiting state
                        console.log('[AnalysisPage] Analysis still in progress, waiting...')
                        setIsAnalyzing(true)
                    } else if (stored.status === 'failed') {
                        // Analysis failed - allow re-run
                        console.log('[AnalysisPage] Previous analysis failed, allowing re-run')
                        analysisStartedRef.current = false
                    }
                } else {
                    console.log('[AnalysisPage] No stored analysis found for jobId')
                }
            } catch (err) {
                console.error('[AnalysisPage] Failed to load stored analysis:', err)
            } finally {
                setIsLoadingStoredAnalysis(false)
                setStoredAnalysisChecked(true) // Mark check as complete
            }
        }

        loadStoredAnalysis()
    }, [jobId, emmaService])

    // Create blob URL for PDF viewer when pdfFile is ready
    useEffect(() => {
        if (pdfFile) {
            const url = URL.createObjectURL(pdfFile)
            setPdfUrl(url)
            return () => URL.revokeObjectURL(url)
        }
    }, [pdfFile])

    // Create blob URL for annotated PDF when analysis completes
    useEffect(() => {
        if (analysisResult?.annotated_pdf) {
            try {
                // Convert base64 to blob
                const byteCharacters = atob(analysisResult.annotated_pdf)
                const byteNumbers = new Array(byteCharacters.length)
                for (let i = 0; i < byteCharacters.length; i++) {
                    byteNumbers[i] = byteCharacters.charCodeAt(i)
                }
                const byteArray = new Uint8Array(byteNumbers)
                const blob = new Blob([byteArray], { type: 'application/pdf' })
                const url = URL.createObjectURL(blob)
                setAnnotatedPdfUrl(url)
                return () => URL.revokeObjectURL(url)
            } catch (err) {
                console.error('Error converting annotated PDF:', err)
            }
        }
    }, [analysisResult?.annotated_pdf])

    // Auto-run analysis ONCE when PDF is ready (only if no stored analysis)
    useEffect(() => {
        // Wait for stored analysis check to complete before deciding to auto-run
        if (!storedAnalysisChecked) {
            console.log('[AnalysisPage] Waiting for stored analysis check...')
            return
        }

        // Only auto-start analysis once per mount and if no stored analysis was found
        if (pdfFile && !analysisStartedRef.current && !storedAnalysis) {
            console.log('[AnalysisPage] Auto-starting new analysis (no stored analysis found)')
            analysisStartedRef.current = true
            runAnalysis()
        }
    }, [pdfFile, runAnalysis, storedAnalysisChecked, storedAnalysis])

    // Navigate to annotation page
    const handleAnnotationClick = useCallback((annotation: PDFAnnotation) => {
        setPageNumber(annotation.page_number)
        setSelectedAnnotationId(annotation.id)
        setTimeout(() => setSelectedAnnotationId(null), 2000)
    }, [])

    // Filter annotations for current page
    const currentPageAnnotations = analysisResult?.annotations.filter(
        a => a.page_number === pageNumber
    ) || []

    // Group annotations by page
    const annotationsByPage = analysisResult?.annotations.reduce((acc, ann) => {
        if (!acc[ann.page_number]) acc[ann.page_number] = []
        acc[ann.page_number].push(ann)
        return acc
    }, {} as Record<number, PDFAnnotation[]>) || {}

    // Create map from finding ID to annotation (for page navigation)
    const annotationById = analysisResult?.annotations.reduce((acc, ann) => {
        acc[ann.id] = ann
        return acc
    }, {} as Record<string, PDFAnnotation>) || {}

    // Combine all findings from analysis (risks + recommendations)
    const allFindings: AnalysisFinding[] = analysisResult ? [
        ...analysisResult.analysis.risks.map(risk => ({
            id: risk.id,
            type: 'risk' as const,
            severity: risk.severity as 'high' | 'medium' | 'low' | undefined,
            title: risk.title,
            description: risk.description,
            quote: risk.quote,
            clause: risk.clause,
            recommendation: risk.recommendation,
            pageNumber: annotationById[risk.id]?.page_number
        })),
        ...analysisResult.analysis.recommendations.map(rec => ({
            id: rec.id,
            type: 'recommendation' as const,
            title: rec.title,
            description: rec.description,
            quote: rec.quote,
            priority: rec.priority as 'high' | 'medium' | 'low' | undefined,
            action_required: rec.action_required,
            pageNumber: annotationById[rec.id]?.page_number
        }))
    ] : []

    // Group findings by page (for "all" view) - include findings without pages in a special group
    const findingsByPage = allFindings.reduce((acc, finding) => {
        const page = finding.pageNumber || 0 // 0 = no page / not annotated
        if (!acc[page]) acc[page] = []
        acc[page].push(finding)
        return acc
    }, {} as Record<number, AnalysisFinding[]>)

    // Findings for current page
    const currentPageFindings = allFindings.filter(f => f.pageNumber === pageNumber)

    // Handler for opening finding detail dialog
    const handleFindingClick = useCallback((finding: AnalysisFinding) => {
        setSelectedFinding(finding)
        // Also highlight in PDF if it has a page
        if (finding.pageNumber && annotationById[finding.id]) {
            setPageNumber(finding.pageNumber)
            setSelectedAnnotationId(finding.id)
            setTimeout(() => setSelectedAnnotationId(null), 2000)
        }
    }, [annotationById])

    // Get severity styles
    const getSeverityColor = (annotation: PDFAnnotation) => {
        if (annotation.type === 'recommendation') return 'bg-blue-600 text-white'
        switch (annotation.severity) {
            case 'high': return 'bg-red-600 text-white'
            case 'medium': return 'bg-amber-500 text-white'
            case 'low': return 'bg-yellow-400 text-yellow-900'
            default: return 'bg-amber-500 text-white'
        }
    }

    const getSeverityLabel = (severity?: string | null) => {
        switch (severity) {
            case 'high': return 'Alto'
            case 'medium': return 'Medio'
            case 'low': return 'Bajo'
            default: return 'Medio'
        }
    }

    // Loading state
    if (isLoadingDocument || isLoadingStoredAnalysis) {
        return (
            <div className="h-screen flex items-center justify-center">
                <div className="text-center">
                    <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4" />
                    <p className="text-muted-foreground">
                        {isLoadingStoredAnalysis ? 'Cargando análisis...' : 'Cargando documento...'}
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

    // Analysis failed without results - show full error page
    if (analysisError && !analysisResult && !isAnalyzing) {
        const errorInfo = parseErrorMessage(analysisError)
        return (
            <div className="h-screen w-full flex bg-background">
                <div className="w-full max-w-xl mx-auto flex flex-col items-center justify-center p-6">
                    {/* Error icon based on type */}
                    <div className={cn(
                        "w-20 h-20 rounded-full flex items-center justify-center mb-6",
                        errorInfo.type === 'network' && "bg-amber-100 dark:bg-amber-900/30",
                        errorInfo.type === 'timeout' && "bg-orange-100 dark:bg-orange-900/30",
                        errorInfo.type === 'llm' && "bg-purple-100 dark:bg-purple-900/30",
                        errorInfo.type === 'server' && "bg-red-100 dark:bg-red-900/30",
                        errorInfo.type === 'unknown' && "bg-gray-100 dark:bg-gray-900/30"
                    )}>
                        {errorInfo.type === 'network' ? (
                            <svg className="w-10 h-10 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.14 0M1.394 9.393c5.857-5.857 15.355-5.857 21.213 0" />
                            </svg>
                        ) : errorInfo.type === 'timeout' ? (
                            <Clock className="w-10 h-10 text-orange-600" />
                        ) : errorInfo.type === 'llm' ? (
                            <Brain className="w-10 h-10 text-purple-600" />
                        ) : (
                            <AlertCircle className="w-10 h-10 text-red-600" />
                        )}
                    </div>

                    {/* Error message */}
                    <h2 className="text-2xl font-semibold text-center mb-2">
                        {errorInfo.title}
                    </h2>
                    <p className="text-lg text-center text-foreground mb-2">
                        {errorInfo.userMessage}
                    </p>
                    <p className="text-sm text-center text-muted-foreground mb-8 max-w-md">
                        {errorInfo.description}
                    </p>

                    {/* Actions */}
                    <div className="flex gap-3">
                        <Button
                            variant="outline"
                            onClick={() => window.history.back()}
                        >
                            ← Volver a documentos
                        </Button>
                        <Button
                            onClick={runAnalysis}
                            disabled={isAnalyzing}
                        >
                            <RefreshCw className="h-4 w-4 mr-2" />
                            Reintentar análisis
                        </Button>
                    </div>

                    {/* Progress history (if there were steps before failure) */}
                    {progressSteps.length > 0 && (
                        <div className="mt-8 w-full max-w-md">
                            <p className="text-xs font-medium text-muted-foreground mb-3 text-center">
                                Últimos pasos antes del error:
                            </p>
                            <div className="bg-muted/30 rounded-lg p-3 space-y-2 max-h-48 overflow-auto">
                                {[...progressSteps].reverse().slice(0, 5).map((step) => (
                                    <div key={step.id} className="flex items-center gap-2 text-xs">
                                        <span className={cn(
                                            "w-2 h-2 rounded-full flex-shrink-0",
                                            step.status === 'completed' && "bg-green-500",
                                            step.status === 'error' && "bg-red-500",
                                            step.status === 'running' && "bg-amber-500"
                                        )} />
                                        <span className="truncate">{step.title}</span>
                                        {step.status === 'error' && (
                                            <span className="text-red-500 ml-auto">Error</span>
                                        )}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            </div>
        )
    }

    // Analysis in progress - centered layout with plan and activity text
    if (isAnalyzing || (!analysisResult && !analysisError)) {
        // Get the most recent activity step for the text display
        const currentActivity = progressSteps.length > 0
            ? progressSteps[progressSteps.length - 1]
            : null

        return (
            <div className="h-screen w-full flex flex-col bg-background">
                {/* Sticky Header with Global Progress */}
                <div className="sticky top-0 z-20 p-4 border-b bg-card/95 backdrop-blur-sm shadow-sm">
                    <div className="w-[70%] mx-auto">
                        <div className="flex items-center gap-4">
                            <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => router.push(`/${tenantId}/documents`)}
                                className="flex-shrink-0"
                                title={t('analysisPage.backToDocuments')}
                            >
                                <ArrowLeft className="h-5 w-5" />
                            </Button>
                            <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0">
                                <Brain className="h-6 w-6 text-primary animate-pulse" />
                            </div>
                            <div className="flex-1 min-w-0">
                                <div className="flex items-center justify-between mb-1">
                                    <h2 className="text-lg font-semibold truncate">
                                        {t('analysisPage.analyzing')}: {document?.filename || 'Documento'}
                                    </h2>
                                    <Badge variant="secondary" className="ml-2 flex-shrink-0">
                                        {overallProgress}%
                                    </Badge>
                                </div>
                                <Progress value={overallProgress} className="h-2" />
                            </div>
                        </div>
                    </div>
                </div>

                {/* Main Content - Centered at 70% width */}
                <div className="flex-1 overflow-auto">
                    <div className="w-[70%] mx-auto py-6">
                        {/* Plan de Análisis */}
                        <div className="bg-card rounded-xl border shadow-sm">
                            <div className="p-4 border-b">
                                <div className="flex items-center justify-between">
                                    <h3 className="font-semibold flex items-center gap-2">
                                        <ClipboardCheck className="h-5 w-5 text-primary" />
                                        Plan de Análisis
                                    </h3>
                                    {currentPlan.length > 0 && (
                                        <Badge variant="outline" className="text-xs">
                                            {completedStepIndices.size}/{currentPlan.length} completados
                                        </Badge>
                                    )}
                                </div>
                            </div>

                            <div className="p-4">
                                {currentPlan.length > 0 ? (
                                    <div className="space-y-3">
                                        {currentPlan.map((step, idx) => {
                                            // Use step.index if available (0-based from backend), fallback to array idx
                                            const stepIndex = step.index !== undefined ? step.index : idx
                                            const isCompleted = completedStepIndices.has(stepIndex)
                                            const isRunning = currentStepIndex === stepIndex
                                            const hasError = errorStepIndices.has(stepIndex)
                                            return (
                                                <div
                                                    key={stepIndex}
                                                    className={cn(
                                                        "p-4 rounded-lg border transition-all",
                                                        isRunning && "bg-primary/5 border-primary/30 shadow-md",
                                                        isCompleted && "bg-green-50 dark:bg-green-950/20 border-green-200 dark:border-green-800",
                                                        hasError && "bg-red-50 dark:bg-red-950/20 border-red-200 dark:border-red-800",
                                                        !isCompleted && !isRunning && !hasError && "bg-muted/30 border-muted"
                                                    )}
                                                >
                                                    <div className="flex items-start gap-3">
                                                        {/* Status indicator */}
                                                        <div className={cn(
                                                            "w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 text-sm font-bold",
                                                            isCompleted && "bg-green-500 text-white",
                                                            isRunning && "bg-primary text-primary-foreground",
                                                            hasError && "bg-red-500 text-white",
                                                            !isCompleted && !isRunning && !hasError && "bg-muted text-muted-foreground border"
                                                        )}>
                                                            {isCompleted ? (
                                                                <CheckCircle2 className="h-4 w-4" />
                                                            ) : isRunning ? (
                                                                <Loader2 className="h-4 w-4 animate-spin" />
                                                            ) : hasError ? (
                                                                <AlertCircle className="h-4 w-4" />
                                                            ) : (
                                                                <span>{stepIndex + 1}</span>
                                                            )}
                                                        </div>

                                                        <div className="flex-1 min-w-0">
                                                            {/* Agent name */}
                                                            <div className="flex items-center gap-2 mb-1">
                                                                <span className={cn(
                                                                    "flex-shrink-0",
                                                                    isRunning ? "text-primary" : "text-muted-foreground"
                                                                )}>
                                                                    {AGENT_ICONS[step.agent] || <Bot className="h-4 w-4" />}
                                                                </span>
                                                                <span className={cn(
                                                                    "text-sm font-medium",
                                                                    isRunning && "text-primary",
                                                                    isCompleted && "text-green-700 dark:text-green-400",
                                                                    hasError && "text-red-600"
                                                                )}>
                                                                    {step.agent}
                                                                </span>
                                                                {isRunning && (
                                                                    <Badge variant="secondary" className="text-[10px] animate-pulse">
                                                                        Ejecutando
                                                                    </Badge>
                                                                )}
                                                            </div>

                                                            {/* Description */}
                                                            <p className={cn(
                                                                "text-sm",
                                                                isCompleted && "text-green-600 dark:text-green-400",
                                                                isRunning && "text-foreground",
                                                                hasError && "text-red-500",
                                                                !isCompleted && !isRunning && !hasError && "text-muted-foreground"
                                                            )}>
                                                                {step.description || 'Procesando...'}
                                                            </p>
                                                        </div>
                                                    </div>
                                                </div>
                                            )
                                        })}
                                    </div>
                                ) : (
                                    <div className="text-center py-8">
                                        <Loader2 className="h-6 w-6 animate-spin mx-auto mb-3 text-primary" />
                                        <p className="text-sm text-muted-foreground">Generando plan de análisis...</p>
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* Activity Text - Simple text below the plan with expandable log */}
                        <div className="mt-6">
                            {/* Current Activity Line */}
                            <div className="text-center">
                                {currentActivity ? (
                                    <div className="flex items-center justify-center gap-3 text-sm text-muted-foreground">
                                        {currentActivity.status === 'running' ? (
                                            <Loader2 className="h-4 w-4 animate-spin text-primary" />
                                        ) : currentActivity.status === 'completed' ? (
                                            <CheckCircle2 className="h-4 w-4 text-green-500" />
                                        ) : currentActivity.status === 'error' ? (
                                            <AlertCircle className="h-4 w-4 text-red-500" />
                                        ) : (
                                            <Clock className="h-4 w-4" />
                                        )}
                                        <span className={cn(
                                            currentActivity.status === 'running' && "text-foreground",
                                            currentActivity.status === 'error' && "text-red-500"
                                        )}>
                                            {currentActivity.title}
                                            {currentActivity.description && (
                                                <span className="text-muted-foreground"> — {currentActivity.description}</span>
                                            )}
                                        </span>
                                    </div>
                                ) : (
                                    <div className="flex items-center justify-center gap-3 text-sm text-muted-foreground">
                                        <Loader2 className="h-4 w-4 animate-spin text-primary" />
                                        <span>Preparando análisis...</span>
                                    </div>
                                )}
                            </div>

                            {/* Ver más button */}
                            {progressSteps.length > 1 && (
                                <div className="text-center mt-3">
                                    <button
                                        onClick={() => setIsActivityLogExpanded(!isActivityLogExpanded)}
                                        className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                                    >
                                        {isActivityLogExpanded ? (
                                            <>
                                                <ChevronUp className="h-3 w-3" />
                                                Ocultar historial
                                            </>
                                        ) : (
                                            <>
                                                <ChevronDown className="h-3 w-3" />
                                                Ver historial ({progressSteps.length} eventos)
                                            </>
                                        )}
                                    </button>
                                </div>
                            )}

                            {/* Expanded Activity Log */}
                            {isActivityLogExpanded && progressSteps.length > 0 && (
                                <div className="mt-4 bg-muted/30 rounded-lg border p-4 max-h-64 overflow-auto">
                                    <div className="space-y-2">
                                        {[...progressSteps].reverse().map((step) => (
                                            <div
                                                key={step.id}
                                                className="flex items-start gap-3 text-sm"
                                            >
                                                {/* Status icon */}
                                                <div className={cn(
                                                    "w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5",
                                                    step.status === 'running' && "bg-primary/20 text-primary",
                                                    step.status === 'completed' && "bg-green-100 text-green-600 dark:bg-green-900/30",
                                                    step.status === 'error' && "bg-red-100 text-red-600 dark:bg-red-900/30",
                                                    step.status === 'pending' && "bg-muted text-muted-foreground"
                                                )}>
                                                    {step.status === 'running' ? (
                                                        <Loader2 className="h-3 w-3 animate-spin" />
                                                    ) : step.status === 'completed' ? (
                                                        <CheckCircle2 className="h-3 w-3" />
                                                    ) : step.status === 'error' ? (
                                                        <AlertCircle className="h-3 w-3" />
                                                    ) : (
                                                        <Clock className="h-3 w-3" />
                                                    )}
                                                </div>

                                                {/* Content */}
                                                <div className="flex-1 min-w-0">
                                                    <div className="flex items-center gap-2">
                                                        <span className={cn(
                                                            "font-medium",
                                                            step.status === 'error' && "text-red-600"
                                                        )}>
                                                            {step.title}
                                                        </span>
                                                        <span className="text-xs text-muted-foreground">
                                                            {step.timestamp.toLocaleTimeString()}
                                                        </span>
                                                    </div>
                                                    {step.description && (
                                                        <p className="text-xs text-muted-foreground truncate">
                                                            {step.description}
                                                        </p>
                                                    )}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            </div>
        )
    }

    // Results view (same as before but with retry button that shows progress)
    return (
        <div className="h-screen w-full overflow-hidden bg-background flex">
            {/* Main PDF Area */}
            <div className="flex-1 flex flex-col min-w-0">
                {/* Error banner - enhanced with detailed information */}
                {analysisError && (
                    <div className="p-4 bg-destructive/10 border-b border-destructive/30">
                        <div className="max-w-4xl mx-auto">
                            <div className="flex items-start gap-4">
                                <div className="flex-shrink-0 mt-0.5">
                                    <div className="w-10 h-10 rounded-full bg-destructive/20 flex items-center justify-center">
                                        <AlertCircle className="h-5 w-5 text-destructive" />
                                    </div>
                                </div>
                                <div className="flex-1 min-w-0">
                                    <h3 className="font-medium text-destructive mb-1">
                                        {parseErrorMessage(analysisError).title}
                                    </h3>
                                    <p className="text-sm text-foreground mb-1">
                                        {parseErrorMessage(analysisError).userMessage}
                                    </p>
                                    <p className="text-xs text-muted-foreground">
                                        {parseErrorMessage(analysisError).description}
                                    </p>
                                </div>
                                <div className="flex-shrink-0">
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        onClick={runAnalysis}
                                        disabled={isAnalyzing}
                                        className="border-destructive/30 hover:bg-destructive/10"
                                    >
                                        <RefreshCw className={cn("h-4 w-4 mr-2", isAnalyzing && "animate-spin")} />
                                        Reintentar análisis
                                    </Button>
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {/* Summary banner */}
                {analysisResult && !analysisError && (
                    <div className="p-2 bg-card/95 border-b backdrop-blur">
                        <div className="flex items-center justify-between px-4">
                            <div className="flex items-center gap-4 text-sm">
                                <span className="flex items-center gap-1">
                                    <span className="font-medium text-amber-600">
                                        {analysisResult.analysis.risks.length}
                                    </span>
                                    <span className="text-muted-foreground">riesgos</span>
                                </span>
                                <span className="flex items-center gap-1">
                                    <span className="font-medium text-blue-600">
                                        {analysisResult.analysis.recommendations.length}
                                    </span>
                                    <span className="text-muted-foreground">recomendaciones</span>
                                </span>
                                <span className="text-muted-foreground">|</span>
                                <span className="text-muted-foreground text-xs">
                                    {analysisResult.total_annotations} anotaciones en {analysisResult.pages_annotated} páginas
                                </span>
                            </div>
                            <Button
                                variant="ghost"
                                size="sm"
                                onClick={runAnalysis}
                                disabled={isAnalyzing}
                            >
                                <RefreshCw className={cn("h-4 w-4 mr-2", isAnalyzing && "animate-spin")} />
                                Re-analizar
                            </Button>
                        </div>
                    </div>
                )}

                {/* PDF Content - uses annotated PDF from backend if available */}
                {(annotatedPdfUrl || pdfUrl) ? (
                    <PDFAnnotationViewer
                        url={annotatedPdfUrl || pdfUrl!}
                        fileName={document?.filename}
                        currentPage={pageNumber}
                        onPageChange={setPageNumber}
                        className="flex-1"
                    />
                ) : (
                    <div className="flex-1 flex items-center justify-center">
                        <div className="text-center">
                            <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4 text-muted-foreground" />
                            <p className="text-muted-foreground">Cargando documento...</p>
                        </div>
                    </div>
                )}
            </div>

            {/* Sidebar */}
            <div className="w-96 border-l bg-card flex flex-col shadow-xl">
                <div className="p-4 border-b bg-muted/30">
                    <h2 className="font-serif text-xl font-bold mb-3">
                        Análisis Legal
                    </h2>
                    <Tabs value={sidebarTab} onValueChange={(v) => setSidebarTab(v as 'page' | 'all')}>
                        <TabsList className="grid w-full grid-cols-2">
                            <TabsTrigger value="page" className="text-xs">
                                <FileText className="h-3 w-3 mr-1" />
                                Página {pageNumber} ({currentPageFindings.length})
                            </TabsTrigger>
                            <TabsTrigger value="all" className="text-xs">
                                <List className="h-3 w-3 mr-1" />
                                Todos ({allFindings.length})
                            </TabsTrigger>
                        </TabsList>
                    </Tabs>
                </div>

                <ScrollArea className="flex-1">
                    {sidebarTab === 'page' ? (
                        <div className="p-4 space-y-4">
                            {currentPageFindings.length === 0 ? (
                                <div className="text-center text-muted-foreground py-12">
                                    <FileText className="h-8 w-8 mx-auto mb-2 opacity-50" />
                                    <p className="text-sm">No hay observaciones en esta página.</p>
                                </div>
                            ) : (
                                currentPageFindings.map((finding, idx) => (
                                    <Card
                                        key={finding.id}
                                        className={cn(
                                            "p-4 transition-all duration-300 hover:shadow-xl cursor-pointer rounded-xl border-0 shadow-lg",
                                            finding.type === 'risk'
                                                ? "bg-gradient-to-br from-amber-50 to-amber-100/50 dark:from-amber-950/40 dark:to-amber-900/20"
                                                : "bg-gradient-to-br from-blue-50 to-blue-100/50 dark:from-blue-950/40 dark:to-blue-900/20",
                                            selectedAnnotationId === finding.id && "ring-2 ring-primary"
                                        )}
                                        onClick={() => handleFindingClick(finding)}
                                    >
                                        <div className="flex items-start gap-3">
                                            <div className={cn(
                                                "w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold flex-shrink-0",
                                                finding.type === 'recommendation' ? 'bg-blue-600 text-white' :
                                                finding.severity === 'high' ? 'bg-red-600 text-white' :
                                                finding.severity === 'medium' ? 'bg-amber-500 text-white' :
                                                'bg-yellow-400 text-yellow-900'
                                            )}>
                                                {idx + 1}
                                            </div>
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-2 mb-2">
                                                    {finding.type === 'risk' ? (
                                                        <Badge variant="outline" className={cn(
                                                            "text-xs",
                                                            finding.severity === 'high' ? "border-red-500 text-red-600" :
                                                            finding.severity === 'medium' ? "border-amber-500 text-amber-600" :
                                                            "border-yellow-500 text-yellow-600"
                                                        )}>
                                                            <AlertTriangle className="h-3 w-3 mr-1" />
                                                            Riesgo {getSeverityLabel(finding.severity)}
                                                        </Badge>
                                                    ) : (
                                                        <Badge variant="outline" className="text-xs border-blue-500 text-blue-600">
                                                            <Lightbulb className="h-3 w-3 mr-1" />
                                                            Recomendación
                                                        </Badge>
                                                    )}
                                                </div>
                                                <p className="font-medium text-sm mb-1">{finding.title}</p>
                                                <p className="text-sm text-gray-600 dark:text-gray-300 line-clamp-3">
                                                    {finding.description}
                                                </p>
                                            </div>
                                        </div>
                                    </Card>
                                ))
                            )}
                        </div>
                    ) : (
                        <div className="p-4 space-y-6">
                            {allFindings.length === 0 ? (
                                <div className="text-center text-muted-foreground py-12">
                                    <List className="h-8 w-8 mx-auto mb-2 opacity-50" />
                                    <p className="text-sm">No hay observaciones en el documento.</p>
                                </div>
                            ) : (
                                <>
                                    {/* Findings with page annotations - sorted by page */}
                                    {Object.entries(findingsByPage)
                                        .filter(([page]) => Number(page) > 0)
                                        .sort(([a], [b]) => Number(a) - Number(b))
                                        .map(([page, findings]) => (
                                            <div key={page}>
                                                <div className="flex items-center gap-2 mb-3">
                                                    <Badge variant="secondary" className="text-xs">
                                                        Página {page}
                                                    </Badge>
                                                    <span className="text-xs text-muted-foreground">
                                                        {findings.length} {findings.length === 1 ? 'hallazgo' : 'hallazgos'}
                                                    </span>
                                                </div>
                                                <div className="space-y-3 pl-2 border-l-2 border-muted">
                                                    {findings.map((finding, idx) => (
                                                        <Card
                                                            key={finding.id}
                                                            className={cn(
                                                                "p-3 transition-all duration-300 hover:shadow-lg cursor-pointer rounded-lg border-0 shadow",
                                                                finding.type === 'risk'
                                                                    ? "bg-gradient-to-br from-amber-50 to-amber-100/50 dark:from-amber-950/40 dark:to-amber-900/20"
                                                                    : "bg-gradient-to-br from-blue-50 to-blue-100/50 dark:from-blue-950/40 dark:to-blue-900/20",
                                                                Number(page) === pageNumber && "border-l-4 border-l-primary"
                                                            )}
                                                            onClick={() => handleFindingClick(finding)}
                                                        >
                                                            <div className="flex items-start gap-2">
                                                                <div className={cn(
                                                                    "w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0",
                                                                    finding.type === 'recommendation' ? 'bg-blue-600 text-white' :
                                                                    finding.severity === 'high' ? 'bg-red-600 text-white' :
                                                                    finding.severity === 'medium' ? 'bg-amber-500 text-white' :
                                                                    'bg-yellow-400 text-yellow-900'
                                                                )}>
                                                                    {idx + 1}
                                                                </div>
                                                                <div className="flex-1 min-w-0">
                                                                    <div className="flex items-center gap-1 mb-1">
                                                                        {finding.type === 'risk' ? (
                                                                            <AlertTriangle className="h-3 w-3 text-amber-600" />
                                                                        ) : (
                                                                            <Lightbulb className="h-3 w-3 text-blue-600" />
                                                                        )}
                                                                        <span className="text-xs font-medium text-muted-foreground">
                                                                            {finding.type === 'risk' ? `Riesgo ${getSeverityLabel(finding.severity)}` : 'Recomendación'}
                                                                        </span>
                                                                    </div>
                                                                    <p className="text-xs font-medium">{finding.title}</p>
                                                                    <p className="text-xs text-gray-600 dark:text-gray-300 line-clamp-2">
                                                                        {finding.description}
                                                                    </p>
                                                                </div>
                                                            </div>
                                                        </Card>
                                                    ))}
                                                </div>
                                            </div>
                                        ))}

                                    {/* Findings without PDF annotations */}
                                    {findingsByPage[0] && findingsByPage[0].length > 0 && (
                                        <div>
                                            <div className="flex items-center gap-2 mb-3">
                                                <Badge variant="outline" className="text-xs text-muted-foreground">
                                                    Sin anotación en PDF
                                                </Badge>
                                                <span className="text-xs text-muted-foreground">
                                                    {findingsByPage[0].length} {findingsByPage[0].length === 1 ? 'hallazgo' : 'hallazgos'}
                                                </span>
                                            </div>
                                            <div className="space-y-3 pl-2 border-l-2 border-dashed border-muted">
                                                {findingsByPage[0].map((finding, idx) => (
                                                    <Card
                                                        key={finding.id}
                                                        className={cn(
                                                            "p-3 transition-all duration-300 hover:shadow-lg cursor-pointer rounded-lg border-0 shadow opacity-80",
                                                            finding.type === 'risk'
                                                                ? "bg-gradient-to-br from-amber-50 to-amber-100/50 dark:from-amber-950/40 dark:to-amber-900/20"
                                                                : "bg-gradient-to-br from-blue-50 to-blue-100/50 dark:from-blue-950/40 dark:to-blue-900/20"
                                                        )}
                                                        onClick={() => handleFindingClick(finding)}
                                                    >
                                                        <div className="flex items-start gap-2">
                                                            <div className={cn(
                                                                "w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0",
                                                                finding.type === 'recommendation' ? 'bg-blue-600 text-white' :
                                                                finding.severity === 'high' ? 'bg-red-600 text-white' :
                                                                finding.severity === 'medium' ? 'bg-amber-500 text-white' :
                                                                'bg-yellow-400 text-yellow-900'
                                                            )}>
                                                                {idx + 1}
                                                            </div>
                                                            <div className="flex-1 min-w-0">
                                                                <div className="flex items-center gap-1 mb-1">
                                                                    {finding.type === 'risk' ? (
                                                                        <AlertTriangle className="h-3 w-3 text-amber-600" />
                                                                    ) : (
                                                                        <Lightbulb className="h-3 w-3 text-blue-600" />
                                                                    )}
                                                                    <span className="text-xs font-medium text-muted-foreground">
                                                                        {finding.type === 'risk' ? `Riesgo ${getSeverityLabel(finding.severity)}` : 'Recomendación'}
                                                                    </span>
                                                                </div>
                                                                <p className="text-xs font-medium">{finding.title}</p>
                                                                <p className="text-xs text-gray-600 dark:text-gray-300 line-clamp-2">
                                                                    {finding.description}
                                                                </p>
                                                            </div>
                                                        </div>
                                                    </Card>
                                                ))}
                                            </div>
                                        </div>
                                    )}
                                </>
                            )}
                        </div>
                    )}
                </ScrollArea>

                {/* Summary footer */}
                {analysisResult && (
                    <div className="p-3 border-t bg-muted/30">
                        {analysisResult.analysis.summary && (
                            <p className="text-xs text-muted-foreground mb-2 line-clamp-3">
                                {analysisResult.analysis.summary}
                            </p>
                        )}
                        <div className="flex items-center justify-between text-xs text-muted-foreground">
                            <span>
                                Confianza: {Math.round(analysisResult.analysis.confidence_score * 100)}%
                            </span>
                        </div>
                    </div>
                )}
            </div>

            {/* Finding Detail Dialog */}
            <FindingDetailDialog
                finding={selectedFinding}
                open={!!selectedFinding}
                onOpenChange={(open) => !open && setSelectedFinding(null)}
            />
        </div>
    )
}

// Wrapper with Suspense for useSearchParams
export default function AnalysisPage() {
    return (
        <Suspense fallback={
            <div className="h-screen flex items-center justify-center">
                <div className="text-center">
                    <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4" />
                    <p className="text-muted-foreground">Cargando...</p>
                </div>
            </div>
        }>
            <AnalysisPageContent />
        </Suspense>
    )
}
