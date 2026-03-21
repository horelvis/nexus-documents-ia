'use client'

import { useState } from 'react'
import {
  IconBrain,
  IconCircleCheck,
  IconCircleX,
  IconLoader2,
  IconAlertTriangle,
  IconSend,
} from '@tabler/icons-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { VerifiedClaimInfo, VerifiedGenerationMetadata } from '@/lib/types/emma'
import type { ReviewDecision } from '@/lib/services/verified-generation.service'

interface VerifiedGenTabProps {
  jobs: Record<string, VerifiedGenerationMetadata>
  onSubmitReview?: (jobId: string, decisions: ReviewDecision[]) => void
  isResuming?: boolean
}

/**
 * Verified Generation tab content for the ArtifactsPanel.
 *
 * Renders all active verification jobs with progress, claims list,
 * stats badges, and HITL review controls. Extracted from
 * VerifiedGenerationDialog (content only, no floating/pill/overlay).
 */
export function VerifiedGenTab({ jobs, onSubmitReview, isResuming }: VerifiedGenTabProps) {
  const jobEntries = Object.entries(jobs)

  if (jobEntries.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
        <IconBrain className="h-8 w-8 mb-2 opacity-30" />
        <p className="text-sm">Sin verificaciones activas</p>
      </div>
    )
  }

  // Aggregate stats across all jobs
  const totalActive = jobEntries.reduce((sum, [, j]) => {
    return sum + j.claims.filter(c => c.status === 'generating' || c.status === 'verifying').length
  }, 0)
  const totalVerified = jobEntries.reduce((sum, [, j]) => sum + j.verified_count, 0)
  const totalRejected = jobEntries.reduce((sum, [, j]) => sum + j.rejected_count, 0)
  const totalCorrected = jobEntries.reduce((sum, [, j]) => {
    return sum + j.claims.filter(c => c.status === 'corrected').length
  }, 0)
  const hasReviewJobs = jobEntries.some(([, j]) => j.current_phase === 'review')

  return (
    <div className="space-y-4">
      {/* Stats bar */}
      <div className="flex items-center gap-3 px-1 text-xs">
        {totalActive > 0 && (
          <div className="flex items-center gap-1">
            <IconLoader2 className="h-3.5 w-3.5 text-primary animate-spin" />
            <span>{totalActive} en progreso</span>
          </div>
        )}
        {totalVerified > 0 && (
          <div className="flex items-center gap-1">
            <IconCircleCheck className="h-3.5 w-3.5 text-emerald-500" />
            <span>{totalVerified}</span>
          </div>
        )}
        {totalCorrected > 0 && (
          <div className="flex items-center gap-1">
            <IconAlertTriangle className="h-3.5 w-3.5 text-amber-500" />
            <span>{totalCorrected}</span>
          </div>
        )}
        {totalRejected > 0 && (
          <div className="flex items-center gap-1">
            <IconCircleX className="h-3.5 w-3.5 text-destructive" />
            <span>{totalRejected}</span>
          </div>
        )}
        {hasReviewJobs && (
          <Badge variant="outline" className="ml-auto text-[10px] bg-amber-500/10 text-amber-600 border-amber-500/20">
            Revisión pendiente
          </Badge>
        )}
      </div>

      {/* Resuming banner */}
      {isResuming && (
        <div className="px-3 py-2 rounded-lg bg-emerald-500/5 border border-emerald-500/20 text-xs text-emerald-600 dark:text-emerald-400">
          Recuperando estado de verificación...
        </div>
      )}

      {/* Job sections */}
      <div className="space-y-4">
        {jobEntries.map(([id, job]) => (
          <JobSection key={id} jobId={id} job={job} onSubmitReview={onSubmitReview} />
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Job section (one per verification job)
// ---------------------------------------------------------------------------

function JobSection({
  jobId,
  job,
  onSubmitReview,
}: {
  jobId: string
  job: VerifiedGenerationMetadata
  onSubmitReview?: (jobId: string, decisions: ReviewDecision[]) => void
}) {
  const { claims, current_phase, total_claims, topic } = job
  const processedCount = claims.filter(c => c.status !== 'generating').length
  const progressPercent = total_claims > 0 ? Math.round((processedCount / total_claims) * 100) : 0
  const isActive = current_phase !== 'complete' && current_phase !== 'review'
  const isReview = current_phase === 'review'

  // HITL review state
  const [reviewDecisions, setReviewDecisions] = useState<Record<string, ReviewDecision>>({})
  const [isSubmitting, setIsSubmitting] = useState(false)

  const reviewClaims = claims.filter(c => c.needs_review)
  const autoApprovedClaims = claims.filter(c => !c.needs_review)

  const handleDecision = (claimId: string, action: 'approve' | 'reject') => {
    setReviewDecisions(prev => ({ ...prev, [claimId]: { claim_id: claimId, action } }))
  }

  const handleSubmit = () => {
    if (!onSubmitReview) return
    setIsSubmitting(true)
    const decisions = reviewClaims.map(c =>
      reviewDecisions[c.claim_id] || { claim_id: c.claim_id, action: 'approve' as const }
    )
    onSubmitReview(jobId, decisions)
  }

  return (
    <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 dark:bg-emerald-500/5 overflow-hidden">
      {/* Job header + progress */}
      <div className="px-3 pt-3 pb-2">
        <div className="flex items-center justify-between">
          <p className="text-xs text-muted-foreground font-mono truncate flex-1">
            {topic}
          </p>
          <span className="text-[10px] font-mono text-muted-foreground ml-2">
            {isReview ? 'Revision' : `${processedCount}/${total_claims || '?'}`}
          </span>
        </div>
        <div className="h-1.5 bg-muted rounded-full overflow-hidden mt-1.5">
          <div
            className={cn(
              'h-full rounded-full transition-all duration-300',
              isReview ? 'bg-amber-500' : 'bg-emerald-500'
            )}
            style={{ width: isReview ? '100%' : `${progressPercent}%` }}
          />
        </div>
      </div>

      {/* Review banner */}
      {isReview && (
        <div className="mx-3 mb-2 p-2 bg-amber-50 dark:bg-amber-500/10 rounded-md border border-amber-200 dark:border-amber-500/20">
          <p className="text-[10px] font-semibold text-amber-700 dark:text-amber-400">
            {reviewClaims.length} claim{reviewClaims.length !== 1 ? 's' : ''} necesita{reviewClaims.length !== 1 ? 'n' : ''} revision
          </p>
          <p className="text-[9px] text-amber-600/60 dark:text-amber-400/50">
            {autoApprovedClaims.length} aprobados automaticamente
          </p>
        </div>
      )}

      {/* Claims list */}
      {claims.length > 0 && (
        <div className="px-3 pb-2 space-y-1.5">
          {claims.map(claim => (
            <ClaimItem
              key={claim.claim_id}
              claim={claim}
              isReview={isReview}
              reviewDecision={reviewDecisions[claim.claim_id]}
              onDecision={isReview ? handleDecision : undefined}
            />
          ))}
        </div>
      )}

      {/* HITL Submit button */}
      {isReview && onSubmitReview && (
        <div className="px-3 pb-3">
          <Button
            size="sm"
            className="w-full gap-1.5 bg-emerald-600 hover:bg-emerald-700 text-white"
            onClick={handleSubmit}
            disabled={isSubmitting}
          >
            {isSubmitting ? (
              <><IconLoader2 className="h-3.5 w-3.5 animate-spin" /> Generando...</>
            ) : (
              <><IconSend className="h-3.5 w-3.5" /> Enviar revision</>
            )}
          </Button>
        </div>
      )}

      {/* Empty loading state */}
      {claims.length === 0 && isActive && (
        <div className="text-center py-4 text-muted-foreground">
          <IconLoader2 className="h-5 w-5 mx-auto mb-1 animate-spin opacity-40" />
          <p className="text-xs">Generando claims...</p>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Claim item
// ---------------------------------------------------------------------------

function ClaimItem({
  claim,
  isReview = false,
  reviewDecision,
  onDecision,
}: {
  claim: VerifiedClaimInfo
  isReview?: boolean
  reviewDecision?: ReviewDecision
  onDecision?: (claimId: string, action: 'approve' | 'reject') => void
}) {
  const getStatusIcon = () => {
    if (isReview && claim.needs_review) {
      if (reviewDecision?.action === 'approve') return <IconCircleCheck className="h-4 w-4 text-emerald-500" />
      if (reviewDecision?.action === 'reject') return <IconCircleX className="h-4 w-4 text-destructive" />
      return <IconAlertTriangle className="h-4 w-4 text-amber-500" />
    }
    switch (claim.status) {
      case 'verified':
        return <IconCircleCheck className="h-4 w-4 text-emerald-500" />
      case 'corrected':
        return <IconAlertTriangle className="h-4 w-4 text-amber-500" />
      case 'rejected':
        return <IconCircleX className="h-4 w-4 text-destructive" />
      case 'verifying':
        return <IconLoader2 className="h-4 w-4 text-primary animate-spin" />
      case 'generating':
      default:
        return <IconLoader2 className="h-4 w-4 text-muted-foreground animate-spin" />
    }
  }

  const statusLabel: Record<string, string> = {
    generating: 'Generando',
    verifying: 'Verificando',
    verified: 'Verificado',
    corrected: 'Corregido',
    rejected: 'Rechazado',
    review: 'Revision',
  }

  const statusColor: Record<string, string> = {
    generating: 'bg-muted text-muted-foreground',
    verifying: 'bg-primary/10 text-primary',
    verified: 'bg-emerald-500/10 text-emerald-600',
    corrected: 'bg-amber-500/10 text-amber-600',
    rejected: 'bg-destructive/10 text-destructive',
    review: 'bg-amber-500/10 text-amber-600',
  }

  const isActive = claim.status === 'generating' || claim.status === 'verifying'

  return (
    <div className="flex items-start gap-3 p-2.5 bg-background/60 dark:bg-background/40 rounded-lg">
      <div className="mt-0.5 shrink-0">{getStatusIcon()}</div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className={cn(
            'text-xs truncate flex-1',
            claim.status === 'rejected' && 'text-muted-foreground/50 line-through'
          )}>
            {claim.claim_text || 'Generando claim...'}
          </p>
          <Badge variant="outline" className={cn('text-[10px] shrink-0', statusColor[claim.status])}>
            {statusLabel[claim.status]}
          </Badge>
        </div>

        {isActive && (
          <div className="mt-1">
            <div className="h-1 bg-muted rounded-full overflow-hidden">
              <div className="h-full bg-primary rounded-full animate-pulse w-2/3" />
            </div>
          </div>
        )}

        {claim.confidence !== undefined && !isActive && (
          <div className="flex items-center gap-2 mt-1">
            <p className="text-[10px] text-muted-foreground">
              Confianza: {Math.round(claim.confidence * 100)}%
              {claim.evidence_count ? ` · ${claim.evidence_count} evidencias` : ''}
            </p>
            {claim.verification_type && (
              <Badge variant="outline" className="text-[9px] px-1 py-0">
                {claim.verification_type}
              </Badge>
            )}
          </div>
        )}

        {/* HITL quick approve/reject buttons */}
        {isReview && claim.needs_review && onDecision && (
          <div className="flex gap-1 mt-1.5">
            <Button
              size="sm"
              variant={reviewDecision?.action === 'approve' ? 'default' : 'outline'}
              className={cn(
                'h-5 text-[9px] px-1.5 gap-0.5',
                reviewDecision?.action === 'approve' && 'bg-emerald-600 hover:bg-emerald-700 text-white'
              )}
              onClick={() => onDecision(claim.claim_id, 'approve')}
            >
              <IconCircleCheck className="h-2.5 w-2.5" /> OK
            </Button>
            <Button
              size="sm"
              variant={reviewDecision?.action === 'reject' ? 'destructive' : 'outline'}
              className="h-5 text-[9px] px-1.5 gap-0.5"
              onClick={() => onDecision(claim.claim_id, 'reject')}
            >
              <IconCircleX className="h-2.5 w-2.5" /> No
            </Button>
          </div>
        )}
        {isReview && !claim.needs_review && (
          <p className="text-[9px] text-emerald-500 mt-1">Auto-aprobado</p>
        )}
      </div>
    </div>
  )
}
