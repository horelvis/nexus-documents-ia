'use client'

import React, { useState, useEffect, useMemo, useCallback } from 'react'
import { useParams, useSearchParams, useRouter } from 'next/navigation'
import { useDocumentService } from '@/lib/services/document.service'
import { useEmmaService, DocumentAnalysisResponse } from '@/lib/services/emma.service'
import { Document } from '@/lib/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Separator } from '@/components/ui/separator'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Skeleton } from '@/components/ui/skeleton'
import {
  IconArrowLeft,
  IconFileText,
  IconAlertTriangle,
  IconInfoCircle,
  IconCircleCheck,
  IconLoader2,
  IconChevronRight,
  IconBrain,
  IconRefresh,
  IconRobot
} from '@tabler/icons-react'

// Agent configuration
const AGENTS: Record<string, { name: string; description: string; systemPrompt: string }> = {
  auto: {
    name: 'Auto',
    description: 'Emma elige el mejor agente',
    systemPrompt: 'Analiza este documento y determina el mejor enfoque de análisis.'
  },
  search: {
    name: 'Búsqueda',
    description: 'Encuentra documentos relevantes',
    systemPrompt: 'Busca y encuentra información relevante en este documento.'
  },
  analyst: {
    name: 'Análisis',
    description: 'Analiza en profundidad',
    systemPrompt: 'Realiza un análisis profundo de este documento identificando puntos clave.'
  },
  contract: {
    name: 'Contratos',
    description: 'Revisa cláusulas y riesgos',
    systemPrompt: 'Analiza este contrato identificando cláusulas clave, obligaciones y riesgos legales.'
  },
  compliance: {
    name: 'Cumplimiento',
    description: 'Verifica GDPR/LOPD',
    systemPrompt: 'Verifica el cumplimiento normativo de este documento con GDPR, LOPD y otras regulaciones aplicables.'
  },
  summarizer: {
    name: 'Resúmenes',
    description: 'Genera resumen ejecutivo',
    systemPrompt: 'Genera un resumen ejecutivo claro y conciso de este documento.'
  },
}

interface DocumentAnalysis {
  documentId: string
  document: Document | null
  status: 'pending' | 'loading' | 'analyzing' | 'completed' | 'error'
  error?: string
  analysis?: DocumentAnalysisResponse
}

export default function AnalysisPage() {
  const params = useParams()
  const searchParams = useSearchParams()
  const router = useRouter()
  const tenantId = params.tenantId as string
  const documentService = useDocumentService()
  const emmaService = useEmmaService()

  // Get documentIds and agent from URL params
  const documentIdsParam = searchParams.get('documentIds') || ''
  const agentId = searchParams.get('agent') || 'auto'
  const documentIds = useMemo(() =>
    documentIdsParam.split(',').filter(id => id.trim().length > 0),
    [documentIdsParam]
  )

  const agent = AGENTS[agentId] || AGENTS.auto

  // State for tracking analysis progress
  const [analyses, setAnalyses] = useState<DocumentAnalysis[]>([])
  const [currentIndex, setCurrentIndex] = useState(0)
  const [isComplete, setIsComplete] = useState(false)

  // Initialize analyses from document IDs (only once on mount)
  useEffect(() => {
    if (documentIds.length > 0) {
      setAnalyses(documentIds.map(id => ({
        documentId: id,
        document: null,
        status: 'pending'
      })))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [documentIdsParam])

  // Load document metadata
  const loadDocument = useCallback(async (index: number): Promise<Document | null> => {
    const docId = documentIds[index]
    if (!docId) return null

    try {
      const result = await documentService.getDocument(docId)
      if ('error' in result && result.error) {
        setAnalyses(prev => prev.map((a, i) =>
          i === index ? { ...a, status: 'error', error: result.error } : a
        ))
        return null
      }

      if (result.data) {
        setAnalyses(prev => prev.map((a, i) =>
          i === index ? { ...a, document: result.data!, status: 'analyzing' } : a
        ))
        return result.data
      }
      return null
    } catch {
      setAnalyses(prev => prev.map((a, i) =>
        i === index ? { ...a, status: 'error', error: 'Error al cargar documento' } : a
      ))
      return null
    }
  }, [documentIds, documentService])

  // Run analysis on a document
  const analyzeDocument = useCallback(async (index: number, document: Document) => {
    try {
      // Map agent type to analysis type
      const analysisType = agentId === 'contract' || agentId === 'compliance'
        ? 'legal'
        : agentId === 'summarizer'
          ? 'summary'
          : 'comprehensive'

      const result = await emmaService.analyzeDocument(
        document.id,
        tenantId,
        document.filename || document.title || 'Documento',
        analysisType
      )

      setAnalyses(prev => prev.map((a, i) =>
        i === index ? { ...a, status: 'completed', analysis: result } : a
      ))
    } catch (err) {
      setAnalyses(prev => prev.map((a, i) =>
        i === index ? {
          ...a,
          status: 'error',
          error: err instanceof Error ? err.message : 'Error al analizar'
        } : a
      ))
    }
  }, [agentId, emmaService, tenantId])

  // Process documents sequentially
  useEffect(() => {
    const processNext = async () => {
      if (currentIndex >= documentIds.length) {
        setIsComplete(true)
        return
      }

      const currentAnalysis = analyses[currentIndex]
      if (!currentAnalysis || currentAnalysis.status !== 'pending') {
        return
      }

      // Update status to loading
      setAnalyses(prev => prev.map((a, i) =>
        i === currentIndex ? { ...a, status: 'loading' } : a
      ))

      // Load document
      const document = await loadDocument(currentIndex)

      if (document) {
        // Analyze document
        await analyzeDocument(currentIndex, document)
      }

      // Move to next document
      setCurrentIndex(prev => prev + 1)
    }

    if (analyses.length > 0 && currentIndex < documentIds.length) {
      const currentAnalysis = analyses[currentIndex]
      if (currentAnalysis?.status === 'pending') {
        processNext()
      }
    }
  }, [analyses, currentIndex, documentIds.length, loadDocument, analyzeDocument])

  // Progress calculation
  const progress = useMemo(() => {
    if (analyses.length === 0) return 0
    const completed = analyses.filter(a =>
      a.status === 'completed' || a.status === 'error'
    ).length
    return Math.round((completed / analyses.length) * 100)
  }, [analyses])

  // Summary stats
  const stats = useMemo(() => {
    const completed = analyses.filter(a => a.status === 'completed')
    const totalRisks = completed.reduce((sum, a) =>
      sum + (a.analysis?.risks?.length || 0), 0
    )
    const totalRecommendations = completed.reduce((sum, a) =>
      sum + (a.analysis?.recommendations?.length || 0), 0
    )
    const avgConfidence = completed.length > 0
      ? completed.reduce((sum, a) => sum + (a.analysis?.confidence_score || 0), 0) / completed.length
      : 0

    return {
      totalDocuments: analyses.length,
      completed: completed.length,
      errors: analyses.filter(a => a.status === 'error').length,
      totalRisks,
      totalRecommendations,
      avgConfidence: Math.round(avgConfidence * 100)
    }
  }, [analyses])

  // Severity badge color
  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'high': return 'destructive'
      case 'medium': return 'warning'
      case 'low': return 'secondary'
      default: return 'outline'
    }
  }

  // Navigate to individual document analysis
  const goToDocumentAnalysis = (documentId: string) => {
    router.push(`/${tenantId}/documents/${documentId}/analysis`)
  }

  // Go back to documents page
  const goBack = () => {
    router.push(`/${tenantId}/documents`)
  }

  // Retry failed analysis
  const retryAnalysis = async (index: number) => {
    setAnalyses(prev => prev.map((a, i) =>
      i === index ? { ...a, status: 'pending', error: undefined } : a
    ))

    // Trigger reprocessing
    setAnalyses(prev => prev.map((a, i) =>
      i === index ? { ...a, status: 'loading' } : a
    ))

    const document = await loadDocument(index)
    if (document) {
      await analyzeDocument(index, document)
    }
  }

  if (documentIds.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen p-8">
        <IconFileText className="h-16 w-16 text-muted-foreground mb-4" />
        <h2 className="text-2xl font-semibold mb-2">No hay documentos seleccionados</h2>
        <p className="text-muted-foreground mb-6">
          Selecciona documentos desde la página de documentos para analizarlos.
        </p>
        <Button onClick={goBack}>
          <IconArrowLeft className="mr-2 h-4 w-4" />
          Volver a Documentos
        </Button>
      </div>
    )
  }

  // Show loader with skeleton while analyzing (no documents completed yet)
  if (!isComplete && stats.completed === 0) {
    const currentDoc = analyses[currentIndex]
    const currentDocName = currentDoc?.document?.title || currentDoc?.document?.filename || `Documento ${currentIndex + 1}`

    return (
      <div className="min-h-screen w-full bg-background">
        {/* Loader central */}
        <div className="flex items-center justify-center pt-16 pb-8">
          <div className="text-center bg-card p-8 rounded-xl shadow-xl max-w-md">
            <IconBrain className="h-12 w-12 animate-pulse mx-auto mb-4 text-primary" />
            <h3 className="text-lg font-semibold mb-2">Emma está analizando los documentos</h3>
            <p className="text-muted-foreground text-sm mb-4">
              {currentDoc?.status === 'loading' && 'Cargando documento...'}
              {currentDoc?.status === 'analyzing' && `Analizando: ${currentDocName}`}
              {currentDoc?.status === 'pending' && 'Preparando análisis...'}
            </p>
            <div className="mb-4">
              <Progress value={(currentIndex / documentIds.length) * 100} className="h-2" />
              <p className="text-xs text-muted-foreground mt-2">
                {currentIndex + 1} de {documentIds.length} documentos
              </p>
            </div>
            <div className="flex items-center justify-center gap-1">
              <div className="w-2 h-2 bg-primary rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
              <div className="w-2 h-2 bg-primary rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
              <div className="w-2 h-2 bg-primary rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
          </div>
        </div>

        {/* Skeleton de resultados */}
        <div className="max-w-7xl mx-auto px-6 pb-8 space-y-4">
          {/* Skeleton de estadísticas */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <Card key={i}>
                <CardContent className="pt-6">
                  <div className="text-center space-y-2">
                    <Skeleton className="h-8 w-8 rounded-full mx-auto" />
                    <Skeleton className="h-8 w-12 mx-auto" />
                    <Skeleton className="h-4 w-20 mx-auto" />
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Skeleton de documentos */}
          <div className="space-y-4">
            <Skeleton className="h-6 w-48" />
            {documentIds.map((_, index) => (
              <Card key={index} className="overflow-hidden">
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <Skeleton className="h-5 w-5 rounded" />
                      <div className="space-y-2">
                        <Skeleton className="h-5 w-48" />
                        <Skeleton className="h-3 w-24" />
                      </div>
                    </div>
                    <Skeleton className="h-6 w-20 rounded-full" />
                  </div>
                </CardHeader>
                <CardContent className="pt-0">
                  <div className="space-y-3">
                    <Skeleton className="h-16 w-full rounded-lg" />
                    <div className="flex gap-2">
                      <Skeleton className="h-5 w-16 rounded-full" />
                      <Skeleton className="h-5 w-32" />
                    </div>
                    <div className="flex gap-2">
                      <Skeleton className="h-5 w-16 rounded-full" />
                      <Skeleton className="h-5 w-40" />
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6 p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={goBack}>
            <IconArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <IconBrain className="h-6 w-6 text-primary" />
              Análisis con Emma
            </h1>
            <p className="text-muted-foreground flex items-center gap-2">
              <IconRobot className="h-4 w-4" />
              Agente: <span className="font-medium">{agent.name}</span> - {agent.description}
            </p>
          </div>
        </div>
      </div>

      {/* Progress */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg">Progreso del análisis</CardTitle>
            <Badge variant={isComplete ? 'default' : 'secondary'}>
              {isComplete ? 'Completado' : 'En progreso'}
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          <Progress value={progress} className="h-2 mb-2" />
          <div className="flex justify-between text-sm text-muted-foreground">
            <span>{stats.completed} de {stats.totalDocuments} documentos</span>
            <span>{progress}%</span>
          </div>
        </CardContent>
      </Card>

      {/* Summary Stats (when complete) */}
      {isComplete && stats.completed > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card>
            <CardContent className="pt-6">
              <div className="text-center">
                <IconCircleCheck className="h-8 w-8 mx-auto mb-2 text-green-600" />
                <p className="text-2xl font-bold">{stats.completed}</p>
                <p className="text-sm text-muted-foreground">Analizados</p>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <div className="text-center">
                <IconAlertTriangle className="h-8 w-8 mx-auto mb-2 text-amber-600" />
                <p className="text-2xl font-bold">{stats.totalRisks}</p>
                <p className="text-sm text-muted-foreground">Riesgos</p>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <div className="text-center">
                <IconInfoCircle className="h-8 w-8 mx-auto mb-2 text-blue-600" />
                <p className="text-2xl font-bold">{stats.totalRecommendations}</p>
                <p className="text-sm text-muted-foreground">Recomendaciones</p>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <div className="text-center">
                <IconBrain className="h-8 w-8 mx-auto mb-2 text-purple-600" />
                <p className="text-2xl font-bold">{stats.avgConfidence}%</p>
                <p className="text-sm text-muted-foreground">Confianza promedio</p>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Document Analysis Results */}
      <div className="space-y-4">
        <h2 className="text-lg font-semibold">Resultados por documento</h2>

        {analyses.map((analysis, index) => (
          <Card key={analysis.documentId} className="overflow-hidden">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <IconFileText className="h-5 w-5 text-muted-foreground" />
                  <div>
                    <CardTitle className="text-base">
                      {analysis.document?.title || analysis.document?.filename || `Documento ${index + 1}`}
                    </CardTitle>
                    {analysis.document && (
                      <CardDescription className="text-xs">
                        {analysis.document.file_type?.toUpperCase()} - {
                          analysis.document.file_size
                            ? `${(analysis.document.file_size / 1024).toFixed(1)} KB`
                            : 'Tamaño desconocido'
                        }
                      </CardDescription>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  {analysis.status === 'loading' && (
                    <Badge variant="outline" className="gap-1">
                      <IconLoader2 className="h-3 w-3 animate-spin" />
                      Cargando
                    </Badge>
                  )}
                  {analysis.status === 'analyzing' && (
                    <Badge variant="outline" className="gap-1 text-primary border-primary">
                      <IconBrain className="h-3 w-3 animate-pulse" />
                      Analizando
                    </Badge>
                  )}
                  {analysis.status === 'completed' && (
                    <Badge variant="default" className="gap-1 bg-green-600">
                      <IconCircleCheck className="h-3 w-3" />
                      Completado
                    </Badge>
                  )}
                  {analysis.status === 'error' && (
                    <Badge variant="destructive" className="gap-1">
                      <IconAlertTriangle className="h-3 w-3" />
                      Error
                    </Badge>
                  )}
                  {analysis.status === 'pending' && (
                    <Badge variant="secondary">Pendiente</Badge>
                  )}
                </div>
              </div>
            </CardHeader>

            {/* Error state */}
            {analysis.status === 'error' && analysis.error && (
              <CardContent className="pt-0">
                <Alert variant="destructive">
                  <IconAlertTriangle className="h-4 w-4" />
                  <AlertTitle>Error en el análisis</AlertTitle>
                  <AlertDescription className="flex items-center justify-between">
                    <span>{analysis.error}</span>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => retryAnalysis(index)}
                    >
                      <IconRefresh className="h-4 w-4 mr-1" />
                      Reintentar
                    </Button>
                  </AlertDescription>
                </Alert>
              </CardContent>
            )}

            {/* Analysis results */}
            {analysis.status === 'completed' && analysis.analysis && (
              <CardContent className="pt-0">
                <div className="space-y-4">
                  {/* Summary */}
                  {analysis.analysis.summary && (
                    <div className="bg-muted/50 p-3 rounded-lg">
                      <p className="text-sm">{analysis.analysis.summary}</p>
                    </div>
                  )}

                  {/* Risks */}
                  {analysis.analysis.risks.length > 0 && (
                    <div>
                      <h4 className="text-sm font-medium mb-2 flex items-center gap-2">
                        <IconAlertTriangle className="h-4 w-4 text-amber-600" />
                        Riesgos identificados ({analysis.analysis.risks.length})
                      </h4>
                      <div className="space-y-2">
                        {analysis.analysis.risks.slice(0, 3).map((risk, i) => (
                          <div key={i} className="flex items-start gap-2 text-sm">
                            <Badge
                              variant={getSeverityColor(risk.severity) as 'destructive' | 'secondary' | 'outline'}
                              className="text-xs shrink-0"
                            >
                              {risk.severity}
                            </Badge>
                            <span className="text-muted-foreground">{risk.title}</span>
                          </div>
                        ))}
                        {analysis.analysis.risks.length > 3 && (
                          <p className="text-xs text-muted-foreground">
                            +{analysis.analysis.risks.length - 3} más riesgos
                          </p>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Recommendations */}
                  {analysis.analysis.recommendations.length > 0 && (
                    <div>
                      <h4 className="text-sm font-medium mb-2 flex items-center gap-2">
                        <IconInfoCircle className="h-4 w-4 text-blue-600" />
                        Recomendaciones ({analysis.analysis.recommendations.length})
                      </h4>
                      <div className="space-y-1">
                        {analysis.analysis.recommendations.slice(0, 2).map((rec, i) => (
                          <p key={i} className="text-sm text-muted-foreground">
                            • {rec.title}
                          </p>
                        ))}
                        {analysis.analysis.recommendations.length > 2 && (
                          <p className="text-xs text-muted-foreground">
                            +{analysis.analysis.recommendations.length - 2} más recomendaciones
                          </p>
                        )}
                      </div>
                    </div>
                  )}

                  <Separator />

                  {/* View details button */}
                  <div className="flex justify-end">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => goToDocumentAnalysis(analysis.documentId)}
                    >
                      Ver análisis completo
                      <IconChevronRight className="h-4 w-4 ml-1" />
                    </Button>
                  </div>
                </div>
              </CardContent>
            )}

            {/* Loading/Analyzing state */}
            {(analysis.status === 'loading' || analysis.status === 'analyzing') && (
              <CardContent className="pt-0">
                <div className="flex items-center gap-3 text-muted-foreground">
                  <IconLoader2 className="h-5 w-5 animate-spin" />
                  <span className="text-sm">
                    {analysis.status === 'loading'
                      ? 'Cargando documento...'
                      : 'Emma está analizando el documento...'}
                  </span>
                </div>
              </CardContent>
            )}
          </Card>
        ))}
      </div>

      {/* Actions */}
      {isComplete && (
        <div className="flex justify-center gap-4 pt-4">
          <Button variant="outline" onClick={goBack}>
            <IconArrowLeft className="mr-2 h-4 w-4" />
            Volver a Documentos
          </Button>
        </div>
      )}
    </div>
  )
}
