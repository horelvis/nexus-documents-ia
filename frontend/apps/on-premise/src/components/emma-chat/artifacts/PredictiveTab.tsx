'use client'

import {
  IconScale,
  IconCircleCheck,
  IconCircleX,
  IconLoader2,
} from '@tabler/icons-react'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { PredictiveFactorInfo, PredictiveAnalysisMetadata } from '@/lib/types/emma'

interface PredictiveTabProps {
  jobs: Record<string, PredictiveAnalysisMetadata>
}

/**
 * Predictive Analysis tab content for the ArtifactsPanel.
 *
 * Renders all active prediction jobs with factor extraction progress,
 * outcome list, and prediction scores. Extracted from
 * PredictiveAnalysisDialog (content only, no floating/pill/overlay).
 */
export function PredictiveTab({ jobs }: PredictiveTabProps) {
  const jobEntries = Object.entries(jobs)

  if (jobEntries.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
        <IconScale className="h-8 w-8 mb-2 opacity-30" />
        <p className="text-sm">Sin analisis predictivos activos</p>
      </div>
    )
  }

  // Aggregate stats
  const totalActive = jobEntries.reduce((sum, [, j]) => {
    return sum + j.factors.filter(f => f.status === 'extracting' || f.status === 'verifying').length
  }, 0)
  const totalWeighted = jobEntries.reduce((sum, [, j]) => sum + j.weighted_count, 0)
  const totalRejected = jobEntries.reduce((sum, [, j]) => sum + j.rejected_count, 0)

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
        {totalWeighted > 0 && (
          <div className="flex items-center gap-1">
            <IconScale className="h-3.5 w-3.5 text-blue-500" />
            <span>{totalWeighted} ponderados</span>
          </div>
        )}
        {totalRejected > 0 && (
          <div className="flex items-center gap-1">
            <IconCircleX className="h-3.5 w-3.5 text-destructive" />
            <span>{totalRejected}</span>
          </div>
        )}
      </div>

      {/* Job sections */}
      <div className="space-y-4">
        {jobEntries.map(([id, job]) => (
          <PredictiveJobSection key={id} job={job} />
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Job section (one per predictive job)
// ---------------------------------------------------------------------------

function PredictiveJobSection({ job }: { job: PredictiveAnalysisMetadata }) {
  const { factors, current_phase, total_factors, case_description, probability, primary_outcome } = job
  const processedCount = factors.filter(f => f.status !== 'extracting').length
  const progressPercent = total_factors > 0 ? Math.round((processedCount / total_factors) * 100) : 0
  const isActive = current_phase !== 'complete'
  const isComplete = current_phase === 'complete'

  return (
    <div className="rounded-lg border border-blue-500/20 bg-blue-500/5 dark:bg-blue-500/5 overflow-hidden">
      {/* Job header + progress */}
      <div className="px-3 pt-3 pb-2">
        <div className="flex items-center justify-between">
          <p className="text-xs text-muted-foreground font-mono truncate flex-1">
            {case_description.length > 60 ? case_description.slice(0, 60) + '...' : case_description}
          </p>
          <span className="text-[10px] font-mono text-muted-foreground ml-2">
            {processedCount}/{total_factors || '?'}
          </span>
        </div>
        <div className="h-1.5 bg-muted rounded-full overflow-hidden mt-1.5">
          <div
            className="h-full bg-blue-500 rounded-full transition-all duration-300"
            style={{ width: `${progressPercent}%` }}
          />
        </div>
      </div>

      {/* Outcome summary (when complete) */}
      {isComplete && probability !== undefined && (
        <div className="mx-3 mb-2 p-2.5 bg-blue-50 dark:bg-blue-500/10 rounded-md border border-blue-200 dark:border-blue-500/20">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold text-blue-700 dark:text-blue-400">
              {primary_outcome || 'Resultado'}
            </p>
            <Badge variant="outline" className="text-[10px] bg-blue-500/10 text-blue-600 border-blue-500/20 font-mono">
              {Math.round(probability * 100)}%
            </Badge>
          </div>
        </div>
      )}

      {/* Factors list */}
      {factors.length > 0 && (
        <div className="px-3 pb-2 space-y-1.5">
          {factors.map(factor => (
            <FactorItem key={factor.factor_id} factor={factor} />
          ))}
        </div>
      )}

      {/* Empty loading state */}
      {factors.length === 0 && isActive && (
        <div className="text-center py-4 text-muted-foreground">
          <IconLoader2 className="h-5 w-5 mx-auto mb-1 animate-spin opacity-40" />
          <p className="text-xs">Extrayendo factores...</p>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Factor item
// ---------------------------------------------------------------------------

function FactorItem({ factor }: { factor: PredictiveFactorInfo }) {
  const getStatusIcon = () => {
    switch (factor.status) {
      case 'weighted':
        return <IconScale className="h-4 w-4 text-blue-500" />
      case 'rejected':
        return <IconCircleX className="h-4 w-4 text-destructive" />
      case 'verifying':
        return <IconLoader2 className="h-4 w-4 text-primary animate-spin" />
      case 'extracting':
      default:
        return <IconLoader2 className="h-4 w-4 text-muted-foreground animate-spin" />
    }
  }

  const statusLabel: Record<string, string> = {
    extracting: 'Extrayendo',
    verifying: 'Verificando',
    weighted: 'Ponderado',
    rejected: 'Rechazado',
  }

  const statusColor: Record<string, string> = {
    extracting: 'bg-muted text-muted-foreground',
    verifying: 'bg-primary/10 text-primary',
    weighted: 'bg-blue-500/10 text-blue-600',
    rejected: 'bg-destructive/10 text-destructive',
  }

  const isActive = factor.status === 'extracting' || factor.status === 'verifying'

  return (
    <div className="flex items-start gap-3 p-2.5 bg-background/60 dark:bg-background/40 rounded-lg">
      <div className="mt-0.5 shrink-0">{getStatusIcon()}</div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className={cn(
            'text-xs truncate flex-1',
            factor.status === 'rejected' && 'text-muted-foreground/50 line-through'
          )}>
            {factor.description || 'Extrayendo factor...'}
          </p>
          <Badge variant="outline" className={cn('text-[10px] shrink-0', statusColor[factor.status])}>
            {statusLabel[factor.status]}
          </Badge>
        </div>

        {factor.factor_type && (
          <p className="text-[10px] text-muted-foreground mt-0.5 font-mono">
            {factor.factor_type}
          </p>
        )}

        {isActive && (
          <div className="mt-1">
            <div className="h-1 bg-muted rounded-full overflow-hidden">
              <div className="h-full bg-primary rounded-full animate-pulse w-2/3" />
            </div>
          </div>
        )}

        {factor.weight !== undefined && !isActive && (
          <p className="text-[10px] text-muted-foreground mt-1">
            Peso: {Math.round(factor.weight * 100)}%
            {factor.confidence ? ` · Confianza: ${Math.round(factor.confidence * 100)}%` : ''}
            {factor.evidence_count ? ` · ${factor.evidence_count} evidencias` : ''}
          </p>
        )}
      </div>
    </div>
  )
}
