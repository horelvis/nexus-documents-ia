'use client'

/**
 * Layout-level wrapper for VerifiedGenerationDialog.
 *
 * Reads job state from VerifiedGenerationContext so the floating
 * progress widget persists across page navigation.
 *
 * HITL review: The review handler is registered by EmmaChat via context ref.
 * This allows the floating widget (rendered at layout level) to trigger
 * the resume flow without prop drilling.
 */

import { useCallback } from 'react'
import { useVerifiedGeneration } from '@/contexts/verified-generation-context'
import { VerifiedGenerationDialog } from './VerifiedGenerationDialog'
import type { ReviewDecision } from '@/lib/services/verified-generation.service'

export function VerifiedGenerationFloating() {
  const { dialogOpen, setDialogOpen, jobs, reviewHandler } = useVerifiedGeneration()

  const handleSubmitReview = useCallback(
    (jobId: string, decisions: ReviewDecision[]) => {
      if (reviewHandler.current) {
        reviewHandler.current(jobId, decisions)
      }
    },
    [reviewHandler]
  )

  return (
    <VerifiedGenerationDialog
      open={dialogOpen}
      onOpenChange={setDialogOpen}
      jobs={jobs}
      onSubmitReview={handleSubmitReview}
    />
  )
}
