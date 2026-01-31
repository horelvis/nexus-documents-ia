'use client'

import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  IconBrain,
  IconChevronDown,
  IconChevronUp,
  IconX,
  IconCircleCheck,
  IconCircleX,
  IconLoader2,
  IconEdit,
} from '@tabler/icons-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { VerifiedClaimInfo, VerifiedGenerationMetadata } from '@/lib/types/emma'

interface VerifiedGenerationDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  jobs: Record<string, VerifiedGenerationMetadata>
}

/**
 * Floating Verified Generation Widget (queue-widget pattern)
 *
 * Shows all active verification jobs in a single floating panel (top-right).
 * Supports multiple concurrent jobs. Collapses to a pill when dismissed.
 */
export function VerifiedGenerationDialog({ open, onOpenChange, jobs }: VerifiedGenerationDialogProps) {
  const [isExpanded, setIsExpanded] = useState(true)

  const jobEntries = Object.entries(jobs)
  const jobCount = jobEntries.length

  if (jobCount === 0) return null

  // Aggregate stats across all jobs
  const totalActive = jobEntries.reduce((sum, [, j]) => {
    return sum + j.claims.filter(c => c.status === 'generating' || c.status === 'verifying').length
  }, 0)
  const totalVerified = jobEntries.reduce((sum, [, j]) => sum + j.verified_count, 0)
  const totalRejected = jobEntries.reduce((sum, [, j]) => sum + j.rejected_count, 0)
  const hasActiveJobs = jobEntries.some(([, j]) => j.current_phase !== 'complete')

  // Collapsed pill — show when widget is closed but jobs are active
  if (!open && hasActiveJobs) {
    return (
      <motion.button
        initial={{ scale: 0, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        className={cn(
          'fixed top-6 right-6 z-50',
          'flex items-center gap-2 px-4 py-3 rounded-full',
          'bg-emerald-600 text-white shadow-lg',
          'hover:bg-emerald-700 transition-colors'
        )}
        onClick={() => onOpenChange(true)}
      >
        <img src="/emma-avatar.png" alt="Emma" className="h-5 w-5 rounded-full object-cover object-top animate-pulse" />
        <span className="font-medium text-sm">
          {jobCount > 1 ? `${jobCount} verificaciones` : 'Verificando...'}
        </span>
      </motion.button>
    )
  }

  // Full floating panel
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0, y: -100, scale: 0.95 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -100, scale: 0.95 }}
          transition={{ type: 'spring', damping: 25, stiffness: 300 }}
          className={cn(
            'fixed top-6 right-6 z-50',
            'w-96 max-h-[70vh]',
            'bg-card border rounded-xl shadow-2xl',
            'flex flex-col overflow-hidden'
          )}
        >
          {/* Header */}
          <div className="flex items-center justify-between p-4 border-b bg-muted/30">
            <div className="flex items-center gap-3">
              <div className={cn(
                'w-10 h-10 rounded-full flex items-center justify-center',
                hasActiveJobs ? 'bg-emerald-500/10' : 'bg-muted'
              )}>
                <IconBrain className={cn(
                  'h-5 w-5',
                  hasActiveJobs ? 'text-emerald-600 animate-pulse' : 'text-muted-foreground'
                )} />
              </div>
              <div>
                <h3 className="font-semibold text-sm">Cola de Verificación</h3>
                <p className="text-xs text-muted-foreground">
                  {hasActiveJobs
                    ? `${totalActive} claim${totalActive !== 1 ? 's' : ''} en progreso`
                    : `${totalVerified} verificados`
                  }
                </p>
              </div>
            </div>

            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={() => setIsExpanded(!isExpanded)}
              >
                {isExpanded ? (
                  <IconChevronDown className="h-4 w-4" />
                ) : (
                  <IconChevronUp className="h-4 w-4" />
                )}
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={() => onOpenChange(false)}
              >
                <IconX className="h-4 w-4" />
              </Button>
            </div>
          </div>

          {/* Stats Bar */}
          <div className="flex items-center gap-4 px-4 py-2 bg-muted/20 border-b text-xs">
            <div className="flex items-center gap-1">
              <IconLoader2 className="h-3 w-3 text-primary" />
              <span>{totalActive}</span>
            </div>
            <div className="flex items-center gap-1">
              <IconCircleCheck className="h-3 w-3 text-emerald-500" />
              <span>{totalVerified}</span>
            </div>
            {totalRejected > 0 && (
              <div className="flex items-center gap-1">
                <IconCircleX className="h-3 w-3 text-destructive" />
                <span>{totalRejected}</span>
              </div>
            )}
            {jobCount > 1 && (
              <div className="ml-auto text-muted-foreground font-mono">
                {jobCount} jobs
              </div>
            )}
          </div>

          {/* Jobs list */}
          <AnimatePresence>
            {isExpanded && (
              <motion.div
                initial={{ height: 0 }}
                animate={{ height: 'auto' }}
                exit={{ height: 0 }}
                className="overflow-hidden"
              >
                <div className="p-3 space-y-3 max-h-[50vh] overflow-y-auto">
                  {jobEntries.map(([id, job]) => (
                    <JobSection key={id} job={job} />
                  ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

/**
 * Single verification job section in the widget
 */
function JobSection({ job }: { job: VerifiedGenerationMetadata }) {
  const { claims, current_phase, verified_count, total_claims, topic } = job
  const processedCount = claims.filter(c => c.status !== 'generating').length
  const progressPercent = total_claims > 0 ? Math.round((processedCount / total_claims) * 100) : 0
  const isActive = current_phase !== 'complete'

  return (
    <div className="space-y-2">
      {/* Job header + progress */}
      <div>
        <div className="flex items-center justify-between">
          <p className="text-xs text-muted-foreground font-mono truncate flex-1">
            {topic}
          </p>
          <span className="text-[10px] font-mono text-muted-foreground ml-2">
            {processedCount}/{total_claims || '?'}
          </span>
        </div>
        <div className="h-1.5 bg-muted rounded-full overflow-hidden mt-1">
          <motion.div
            className="h-full bg-emerald-500 rounded-full"
            initial={{ width: 0 }}
            animate={{ width: `${progressPercent}%` }}
            transition={{ duration: 0.3 }}
          />
        </div>
      </div>

      {/* Claims */}
      {claims.length > 0 && (
        <div className="space-y-1.5">
          {claims.map(claim => (
            <ClaimJobItem key={claim.claim_id} claim={claim} />
          ))}
        </div>
      )}

      {claims.length === 0 && isActive && (
        <div className="text-center py-4 text-muted-foreground">
          <IconLoader2 className="h-5 w-5 mx-auto mb-1 animate-spin opacity-40" />
          <p className="text-xs">Generando claims...</p>
        </div>
      )}
    </div>
  )
}

/**
 * Single claim item (matches QueueJobItem pattern)
 */
function ClaimJobItem({ claim }: { claim: VerifiedClaimInfo }) {
  const getStatusIcon = () => {
    switch (claim.status) {
      case 'verified':
        return <IconCircleCheck className="h-4 w-4 text-emerald-500" />
      case 'corrected':
        return <IconEdit className="h-4 w-4 text-amber-500" />
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
  }

  const statusColor: Record<string, string> = {
    generating: 'bg-muted text-muted-foreground',
    verifying: 'bg-primary/10 text-primary',
    verified: 'bg-emerald-500/10 text-emerald-600',
    corrected: 'bg-amber-500/10 text-amber-600',
    rejected: 'bg-destructive/10 text-destructive',
  }

  const isActive = claim.status === 'generating' || claim.status === 'verifying'

  return (
    <div className="flex items-start gap-3 p-2.5 bg-muted/50 rounded-lg">
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
          <p className="text-[10px] text-muted-foreground mt-1">
            Confianza: {Math.round(claim.confidence * 100)}%
            {claim.evidence_count ? ` · ${claim.evidence_count} evidencias` : ''}
          </p>
        )}
      </div>
    </div>
  )
}
