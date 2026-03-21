/**
 * usePredictiveAnalysisHandler — Extracted predictive analysis SSE handler.
 *
 * Uses its OWN SSE stream (queryPredictiveStream), independent of useStream SDK.
 * Manages the predictive lifecycle: upload → SSE stream → factor updates →
 * synthesis → completion injection into chat messages.
 */
import { useState, useCallback, useRef } from 'react'
import { queryPredictiveStream } from '@/lib/services/predictive-analysis.service'
import { classifyError } from '@/lib/services/emma.service'
import type {
  EmmaMessage,
  Attachment,
  PredictiveFactorInfo,
  PredictiveAnalysisMetadata,
} from '@/lib/types/emma'

const SSO_TOKEN_KEY = 'nexus_sso_tokens'

function hasValidToken(): boolean {
  if (typeof window === 'undefined') return false
  const stored = sessionStorage.getItem(SSO_TOKEN_KEY)
  if (!stored) return false
  try {
    const tokens = JSON.parse(stored)
    if (!tokens.access_token) return false
    if (tokens.expires_at && Date.now() >= tokens.expires_at - 60000) return false
    return true
  } catch {
    return false
  }
}

interface PredictiveHandlerOptions {
  userId?: string
  tenantId: string | null
  sessionId: string
  uploadTempDocument: (file: File) => Promise<{ upload_id: string; filename: string }>
  updateMessages: (updater: (prev: EmmaMessage[]) => EmmaMessage[]) => void
  setError: (error: string | null) => void
  setArtifactsPanelOpen: (open: boolean) => void
  setActiveArtifactTab: (tab: string | null) => void
  onAuthError?: () => void
}

export function usePredictiveAnalysisHandler(options: PredictiveHandlerOptions) {
  const {
    userId,
    tenantId,
    sessionId,
    uploadTempDocument,
    updateMessages,
    setError,
    setArtifactsPanelOpen,
    setActiveArtifactTab,
    onAuthError,
  } = options

  const [predictiveJobs, setPredictiveJobs] = useState<
    Record<string, PredictiveAnalysisMetadata>
  >({})
  const predictiveJobsRef = useRef<Record<string, PredictiveAnalysisMetadata>>({})
  const sessionUploadIdsRef = useRef<string[]>([])

  const handlePredictiveAnalysis = useCallback(
    async (caseDescription: string, attachments?: Attachment[]) => {
      if (!userId || !tenantId) return

      if (!hasValidToken()) {
        setError('Tu sesión ha expirado. Por favor inicia sesión nuevamente.')
        setTimeout(() => onAuthError?.(), 1500)
        return
      }

      try {
        const userMessage: EmmaMessage = {
          id: Date.now().toString(),
          type: 'user',
          content: `/predecir ${caseDescription}`,
          timestamp: new Date(),
          metadata:
            attachments && attachments.length > 0
              ? {
                  documents: attachments.map((a) => ({
                    name: a.name,
                    id: a.type === 'indexed' ? a.documentId : a.id,
                    fileType: a.fileType,
                  })),
                }
              : undefined,
        }

        const predictiveMessageId = (Date.now() + 1).toString()
        const initialPredictive: PredictiveAnalysisMetadata = {
          session_id: sessionId,
          tenant_id: tenantId || undefined,
          case_description: caseDescription,
          factors: [],
          current_phase: 'extracting',
          weighted_count: 0,
          rejected_count: 0,
          total_factors: 0,
        }

        updateMessages((prev) => [...prev, userMessage])
        setError(null)

        const jobId = predictiveMessageId
        const updateJob = (
          updater: (prev: PredictiveAnalysisMetadata) => PredictiveAnalysisMetadata,
        ) => {
          setPredictiveJobs((prev) => {
            const current = prev[jobId]
            if (!current) return prev
            const next = updater(current)
            const updated = { ...prev, [jobId]: next }
            predictiveJobsRef.current = updated
            return updated
          })
        }
        const removeJob = () => {
          setPredictiveJobs((prev) => {
            const { [jobId]: _, ...rest } = prev
            predictiveJobsRef.current = rest
            return rest
          })
        }

        setPredictiveJobs((prev) => {
          const updated = { ...prev, [jobId]: initialPredictive }
          predictiveJobsRef.current = updated
          return updated
        })
        setArtifactsPanelOpen(true)
        setActiveArtifactTab('predictive')

        // Upload files
        const uploadedDocs = attachments?.filter((a) => a.type === 'upload') || []
        let uploadedFileIds: string[] = []
        if (uploadedDocs.length > 0) {
          try {
            const uploadResults = await Promise.all(
              uploadedDocs.map(async (doc) => {
                const result = await uploadTempDocument(doc.file)
                return result.upload_id
              }),
            )
            uploadedFileIds = uploadResults
            sessionUploadIdsRef.current = [
              ...new Set([...sessionUploadIdsRef.current, ...uploadedFileIds]),
            ]
          } catch (err) {
            console.error('Failed to upload documents for prediction:', err)
          }
        }

        if (uploadedFileIds.length === 0 && sessionUploadIdsRef.current.length > 0) {
          uploadedFileIds = sessionUploadIdsRef.current
        }

        const contextDocIds =
          attachments?.filter((a) => a.type === 'indexed').map((a) => a.documentId) || []

        try {
          for await (const event of queryPredictiveStream({
            case_description: caseDescription,
            tenant_id: tenantId,
            session_id: sessionId,
            context_document_ids: contextDocIds.length > 0 ? contextDocIds : undefined,
            uploaded_file_ids: uploadedFileIds.length > 0 ? uploadedFileIds : undefined,
          })) {
            if (event.event_type === 'prediction_complete') {
              const jobFactors = predictiveJobsRef.current[jobId]?.factors || []
              removeJob()

              const finalPredictive: PredictiveAnalysisMetadata = {
                ...initialPredictive,
                factors: jobFactors,
                current_phase: 'complete',
                weighted_count: event.data.factors_weighted ?? 0,
                rejected_count: event.data.factors_rejected ?? 0,
                total_factors: event.data.total_factors ?? jobFactors.length,
                probability: event.data.probability,
                primary_outcome: event.data.primary_outcome,
                outcome_probabilities: event.data.outcome_probabilities
                  ? (Object.fromEntries(
                      Object.entries(event.data.outcome_probabilities).map(
                        ([k, v]: [string, unknown]) => [
                          k,
                          typeof v === 'object' && v !== null
                            ? Number((v as Record<string, unknown>).probability) || 0
                            : Number(v) || 0,
                        ],
                      ),
                    ) as Record<string, number>)
                  : undefined,
                recommendation: event.data.recommendation,
                disclaimer: event.data.disclaimer,
                execution_time_ms: event.data.execution_time_ms,
                sources: event.data.sources,
              }

              updateMessages((prev) => [
                ...prev,
                {
                  id: predictiveMessageId,
                  type: 'predictive_result' as const,
                  content: event.data.recommendation || '',
                  timestamp: new Date(),
                  predictive: finalPredictive,
                },
              ])
              return
            }

            if (event.event_type === 'error') {
              removeJob()
              updateMessages((prev) => [
                ...prev,
                {
                  id: predictiveMessageId,
                  type: 'error' as const,
                  content: event.data.error || 'Error en análisis predictivo',
                  timestamp: new Date(),
                },
              ])
              return
            }

            // Update factors in the job
            if (event.factor_id) {
              updateJob((prev) => {
                const existingIdx = prev.factors.findIndex(
                  (f) => f.factor_id === event.factor_id,
                )
                let newFactors: PredictiveFactorInfo[]

                const factorUpdate: Partial<PredictiveFactorInfo> = {
                  factor_id: event.factor_id!,
                }

                if (event.event_type === 'factor_extracted') {
                  factorUpdate.factor_number = event.data.factor_number || prev.factors.length + 1
                  factorUpdate.total_expected = event.data.total_expected || 0
                  factorUpdate.factor_type = event.data.factor_type || ''
                  factorUpdate.description = event.data.description || ''
                  factorUpdate.status = 'extracting'
                } else if (event.event_type === 'factor_verification_started') {
                  factorUpdate.status = 'verifying'
                } else if (event.event_type === 'factor_weighted') {
                  factorUpdate.status = 'weighted'
                  factorUpdate.weight = event.data.weight
                  factorUpdate.confidence = event.data.confidence
                  factorUpdate.outcome = event.data.outcome
                  factorUpdate.evidence_count = event.data.evidence_count
                  factorUpdate.supporting_matches = event.data.supporting_matches
                } else if (event.event_type === 'factor_rejected') {
                  factorUpdate.status = 'rejected'
                }

                if (existingIdx >= 0) {
                  newFactors = prev.factors.map((f, i) =>
                    i === existingIdx ? { ...f, ...factorUpdate } : f,
                  )
                } else {
                  newFactors = [
                    ...prev.factors,
                    {
                      factor_id: factorUpdate.factor_id!,
                      factor_number: factorUpdate.factor_number || prev.factors.length + 1,
                      total_expected: factorUpdate.total_expected || 0,
                      factor_type: factorUpdate.factor_type || '',
                      description: factorUpdate.description || '',
                      status: factorUpdate.status || 'extracting',
                      weight: factorUpdate.weight,
                      confidence: factorUpdate.confidence,
                      outcome: factorUpdate.outcome,
                      evidence_count: factorUpdate.evidence_count,
                    },
                  ]
                }

                const weightedCount = newFactors.filter((f) => f.status === 'weighted').length
                const rejectedCount = newFactors.filter((f) => f.status === 'rejected').length
                const totalExpected =
                  factorUpdate.total_expected || prev.total_factors || newFactors.length
                const hasVerifying = newFactors.some((f) => f.status === 'verifying')

                return {
                  ...prev,
                  factors: newFactors,
                  weighted_count: weightedCount,
                  rejected_count: rejectedCount,
                  total_factors: totalExpected,
                  current_phase: hasVerifying
                    ? ('verifying' as const)
                    : ('extracting' as const),
                }
              })
            }

            if (event.event_type === 'synthesis_started') {
              updateJob((prev) => ({ ...prev, current_phase: 'synthesizing' as const }))
            }
          }

          // Stream ended without prediction_complete
          removeJob()
        } catch (err) {
          console.error('Predictive analysis failed:', err)
          const classified = classifyError(err)
          removeJob()
          updateMessages((prev) => [
            ...prev,
            {
              id: predictiveMessageId,
              type: 'error' as const,
              content: classified.message,
              timestamp: new Date(),
            },
          ])
        }
      } catch (outerErr) {
        console.error('[PredictiveAnalysis] Unexpected error:', outerErr)
      }
    },
    [
      userId,
      tenantId,
      sessionId,
      onAuthError,
      updateMessages,
      uploadTempDocument,
      setError,
      setArtifactsPanelOpen,
      setActiveArtifactTab,
    ],
  )

  return {
    predictiveJobs,
    handlePredictiveAnalysis,
  }
}
