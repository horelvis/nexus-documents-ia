/**
 * useVerifiedGenerationHandler — Extracted verified document generation SSE handler.
 *
 * Uses its OWN SSE stream (queryVerifiedStream), independent of the useStream SDK.
 * Manages the verified generation lifecycle: upload → SSE stream → claim updates →
 * review phase → completion injection into chat messages.
 */
import { useCallback, useRef, useEffect } from 'react'
import { useVerifiedGeneration as useVerifiedGenerationContext } from '@/contexts/verified-generation-context'
import {
  queryVerifiedStream,
  mapEventToClaim,
  recoverVerifiedSession,
  submitReviewAndResume,
  type ReviewDecision,
} from '@/lib/services/verified-generation.service'
import { classifyError } from '@/lib/services/emma.service'
import type {
  EmmaMessage,
  Attachment,
  VerifiedClaimInfo,
  VerifiedGenerationMetadata,
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

interface VerifiedHandlerOptions {
  userId?: string
  sessionId: string
  uploadTempDocument: (file: File) => Promise<{ upload_id: string; filename: string }>
  updateMessages: (updater: (prev: EmmaMessage[]) => EmmaMessage[]) => void
  setError: (error: string | null) => void
  setArtifactsPanelOpen: (open: boolean) => void
  setActiveArtifactTab: (tab: string | null) => void
  onAuthError?: () => void
}

export function useVerifiedGenerationHandler(options: VerifiedHandlerOptions) {
  const {
    userId,
    sessionId,
    uploadTempDocument,
    updateMessages,
    setError,
    setArtifactsPanelOpen,
    setActiveArtifactTab,
    onAuthError,
  } = options

  const {
    jobs: verifiedJobs,
    jobsRef: verifiedJobsRef,
    updateJob: contextUpdateJob,
    setJob: contextSetJob,
    removeJob: contextRemoveJob,
    reviewHandler: contextReviewHandler,
  } = useVerifiedGenerationContext()

  // Retain uploaded file IDs across follow-up queries
  const sessionUploadIdsRef = useRef<string[]>([])

  // Recover verified generation session if user navigated away during generation
  useEffect(() => {
    if (typeof window === 'undefined') return
    const raw = sessionStorage.getItem('verified_active_session')
    if (!raw) return

    let marker: { sessionId: string; topic: string }
    try {
      marker = JSON.parse(raw)
    } catch {
      sessionStorage.removeItem('verified_active_session')
      return
    }

    recoverVerifiedSession(marker.sessionId).then((data) => {
      if (!data) {
        sessionStorage.removeItem('verified_active_session')
        return
      }
      if (data.status === 'completed') {
        sessionStorage.removeItem('verified_active_session')
        updateMessages((prev) => {
          if (prev.some((m) => m.verified?.session_id === marker.sessionId)) return prev
          return [
            ...prev,
            {
              id: `recovered_${marker.sessionId}`,
              type: 'verified_result' as const,
              content: data.document_text || '',
              timestamp: new Date(),
              verified: {
                session_id: data.session_id,
                topic: data.topic || marker.topic,
                claims: data.claims || [],
                current_phase: 'complete' as const,
                verified_count: data.verified_count || 0,
                rejected_count: data.rejected_count || 0,
                total_claims: data.total_claims || 0,
                document_text: data.document_text,
                execution_time_ms: data.execution_time_ms,
                average_confidence: data.average_confidence,
                sources: data.sources,
                doi_validations: data.doi_validations,
                source_filenames: data.source_filenames,
                source_summary: data.source_summary,
              },
            },
          ]
        })
      }
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Consume completed verified generation jobs from layout-level context
  useEffect(() => {
    const completedEntries = Object.entries(verifiedJobs).filter(
      ([, job]) => job.current_phase === 'complete',
    )
    if (completedEntries.length === 0) return

    for (const [jobId, job] of completedEntries) {
      updateMessages((prev) => {
        if (prev.some((m) => m.id === jobId)) return prev
        return [
          ...prev,
          {
            id: jobId,
            type: 'verified_result' as const,
            content: job.document_text || '',
            timestamp: new Date(),
            verified: job,
          },
        ]
      })
      contextRemoveJob(jobId)
      sessionStorage.removeItem('verified_active_session')
    }
  }, [verifiedJobs, updateMessages, contextRemoveJob])

  const handleVerifiedGeneration = useCallback(
    async (topic: string, attachments?: Attachment[]) => {
      if (!userId) return

      if (!hasValidToken()) {
        setError('Tu sesión ha expirado. Por favor inicia sesión nuevamente.')
        setTimeout(() => onAuthError?.(), 1500)
        return
      }

      try {
        const userMessage: EmmaMessage = {
          id: Date.now().toString(),
          type: 'user',
          content: `/verificar ${topic}`,
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

        const verifiedMessageId = (Date.now() + 1).toString()
        const initialVerified: VerifiedGenerationMetadata = {
          session_id: sessionId,
          topic,
          claims: [],
          current_phase: 'generating',
          verified_count: 0,
          rejected_count: 0,
          total_claims: 0,
        }

        updateMessages((prev) => [...prev, userMessage])
        setError(null)

        const jobId = verifiedMessageId
        const updateJob = (
          updater: (prev: VerifiedGenerationMetadata) => VerifiedGenerationMetadata,
        ) => {
          contextUpdateJob(jobId, updater)
        }
        const removeJob = () => {
          contextRemoveJob(jobId)
        }

        contextSetJob(jobId, initialVerified)
        setArtifactsPanelOpen(true)
        setActiveArtifactTab('verified')

        sessionStorage.setItem(
          'verified_active_session',
          JSON.stringify({
            sessionId,
            topic,
            startedAt: new Date().toISOString(),
          }),
        )

        // Upload non-indexed files
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
            console.error('Failed to upload documents for verification:', err)
          }
        }

        if (uploadedFileIds.length === 0 && sessionUploadIdsRef.current.length > 0) {
          uploadedFileIds = sessionUploadIdsRef.current
        }

        const contextDocIds =
          attachments?.filter((a) => a.type === 'indexed').map((a) => a.documentId) || []

        try {
          for await (const event of queryVerifiedStream({
            query: topic,
            session_id: sessionId,
            context_document_ids: contextDocIds.length > 0 ? contextDocIds : undefined,
            uploaded_file_ids: uploadedFileIds.length > 0 ? uploadedFileIds : undefined,
          })) {
            const claimUpdate = mapEventToClaim(event)

            if (event.event_type === 'document_complete') {
              const jobClaims = verifiedJobsRef.current[jobId]?.claims || []
              const finalVerifiedCount = jobClaims.filter(
                (c: VerifiedClaimInfo) => c.status === 'verified',
              ).length
              const finalCorrectedCount = jobClaims.filter(
                (c: VerifiedClaimInfo) => c.status === 'corrected',
              ).length
              const finalRejectedCount = jobClaims.filter(
                (c: VerifiedClaimInfo) => c.status === 'rejected',
              ).length

              updateJob((prev) => ({
                ...prev,
                claims: jobClaims,
                current_phase: 'complete' as const,
                document_text: event.data.document_text,
                verified_count: finalVerifiedCount + finalCorrectedCount,
                rejected_count: finalRejectedCount,
                total_claims: jobClaims.length,
                execution_time_ms: event.data.execution_time_ms,
                average_confidence: event.data.average_confidence,
                sources: event.data.sources,
                doi_validations: event.data.doi_validations,
                source_filenames: event.data.source_filenames,
                source_summary: event.data.source_summary,
              }))
              return
            }

            if (event.event_type === 'review_requested') {
              const reviewData = event.data
              const reviewClaims = (reviewData.claims || []) as Array<{
                claim_id: string
                needs_review: boolean
              }>

              updateJob((prev) => {
                const updatedClaims = prev.claims.map((c) => {
                  const reviewInfo = reviewClaims.find((rc) => rc.claim_id === c.claim_id)
                  if (reviewInfo) {
                    return {
                      ...c,
                      needs_review: reviewInfo.needs_review,
                      auto_approved: !reviewInfo.needs_review,
                    }
                  }
                  return { ...c, auto_approved: true }
                })
                return {
                  ...prev,
                  claims: updatedClaims,
                  current_phase: 'review' as const,
                  needs_review_count: reviewData.needs_review_count || 0,
                  confidence_threshold: reviewData.confidence_threshold,
                }
              })
              return
            }

            if (event.event_type === 'error') {
              sessionStorage.removeItem('verified_active_session')
              removeJob()
              updateMessages((prev) => [
                ...prev,
                {
                  id: verifiedMessageId,
                  type: 'error' as const,
                  content: event.data.error || 'Error en generación verificada',
                  timestamp: new Date(),
                },
              ])
              return
            }

            if (claimUpdate) {
              updateJob((prev) => {
                const existingIdx = prev.claims.findIndex(
                  (c) => c.claim_id === claimUpdate.claim_id,
                )
                let newClaims: VerifiedClaimInfo[]
                if (existingIdx >= 0) {
                  newClaims = prev.claims.map((c, i) =>
                    i === existingIdx ? { ...c, ...claimUpdate } : c,
                  )
                } else {
                  newClaims = [
                    ...prev.claims,
                    {
                      claim_id: claimUpdate.claim_id,
                      claim_number: claimUpdate.claim_number || prev.claims.length + 1,
                      total_expected: claimUpdate.total_expected || 0,
                      claim_text: claimUpdate.claim_text || '',
                      status: claimUpdate.status || 'generating',
                      confidence: claimUpdate.confidence,
                      evidence_count: claimUpdate.evidence_count,
                      original_text: claimUpdate.original_text,
                      evidence_sources: claimUpdate.evidence_sources,
                      verification_type: claimUpdate.verification_type,
                      verification_reason: claimUpdate.verification_reason,
                    },
                  ]
                }

                const verifiedCount = newClaims.filter(
                  (c) => c.status === 'verified' || c.status === 'corrected',
                ).length
                const rejectedCount = newClaims.filter((c) => c.status === 'rejected').length
                const totalExpected =
                  claimUpdate.total_expected || prev.total_claims || newClaims.length
                const hasVerifying = newClaims.some((c) => c.status === 'verifying')

                return {
                  ...prev,
                  claims: newClaims,
                  verified_count: verifiedCount,
                  rejected_count: rejectedCount,
                  total_claims: totalExpected,
                  current_phase: hasVerifying
                    ? ('verifying' as const)
                    : ('generating' as const),
                }
              })
            }
          }

          // Stream ended without document_complete
          removeJob()
        } catch (err) {
          console.error('Verified generation failed:', err)
          const classified = classifyError(err)
          removeJob()
          updateMessages((prev) => [
            ...prev,
            {
              id: verifiedMessageId,
              type: 'error' as const,
              content: classified.message,
              timestamp: new Date(),
            },
          ])
        }
      } catch (outerErr) {
        console.error('[VerifiedGeneration] Unexpected error:', outerErr)
      }
    },
    [
      userId,
      sessionId,
      onAuthError,
      updateMessages,
      uploadTempDocument,
      setError,
      setArtifactsPanelOpen,
      setActiveArtifactTab,
      contextUpdateJob,
      contextSetJob,
      contextRemoveJob,
      verifiedJobsRef,
    ],
  )

  const handleReviewSubmit = useCallback(
    async (jobId: string, decisions: ReviewDecision[]) => {
      const job = verifiedJobsRef.current[jobId]
      if (!job) return

      contextUpdateJob(jobId, (prev) => ({
        ...prev,
        current_phase: 'verifying' as const,
      }))

      try {
        for await (const event of submitReviewAndResume(
          job.session_id,
          decisions,
        )) {
          if (event.event_type === 'document_complete') {
            const jobClaims = verifiedJobsRef.current[jobId]?.claims || []
            const remainingClaims = jobClaims
              .filter((c) => {
                const dec = decisions.find((d) => d.claim_id === c.claim_id)
                return !dec || dec.action !== 'reject'
              })
              .map((c) => {
                const dec = decisions.find((d) => d.claim_id === c.claim_id)
                if (dec?.action === 'edit' && dec.edited_text) {
                  return {
                    ...c,
                    claim_text: dec.edited_text,
                    status: 'corrected' as const,
                    original_text: c.claim_text,
                  }
                }
                return c
              })

            const finalVerifiedCount = remainingClaims.filter(
              (c) => c.status === 'verified',
            ).length
            const finalCorrectedCount = remainingClaims.filter(
              (c) => c.status === 'corrected',
            ).length
            const finalRejectedCount = decisions.filter((d) => d.action === 'reject').length

            contextUpdateJob(jobId, (prev) => ({
              ...prev,
              claims: remainingClaims,
              current_phase: 'complete' as const,
              document_text: event.data.document_text,
              verified_count: finalVerifiedCount + finalCorrectedCount,
              rejected_count: finalRejectedCount,
              total_claims: remainingClaims.length,
              execution_time_ms: event.data.execution_time_ms,
              average_confidence: event.data.average_confidence,
              sources: event.data.sources,
              doi_validations: event.data.doi_validations,
              source_filenames: event.data.source_filenames,
              source_summary: event.data.source_summary,
              needs_review_count: 0,
            }))
            return
          }

          if (event.event_type === 'error') {
            console.error('[VerifiedGen/Resume] Error:', event.data.error)
            contextUpdateJob(jobId, (prev) => ({
              ...prev,
              current_phase: 'review' as const,
            }))
            return
          }
        }
      } catch (err) {
        console.error('[VerifiedGen/Resume] Failed:', err)
        contextUpdateJob(jobId, (prev) => ({
          ...prev,
          current_phase: 'review' as const,
        }))
      }
    },
    [verifiedJobsRef, contextUpdateJob],
  )

  // Register HITL review handler in context so the floating widget can call it
  useEffect(() => {
    contextReviewHandler.current = handleReviewSubmit
    return () => {
      contextReviewHandler.current = null
    }
  }, [handleReviewSubmit, contextReviewHandler])

  return {
    verifiedJobs,
    handleVerifiedGeneration,
    handleReviewSubmit,
  }
}
