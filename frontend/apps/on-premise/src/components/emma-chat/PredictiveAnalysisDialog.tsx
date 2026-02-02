'use client'

import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  IconChartBar,
  IconChevronDown,
  IconChevronUp,
  IconX,
  IconCircleCheck,
  IconCircleX,
  IconLoader2,
  IconScale,
} from '@tabler/icons-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { PredictiveFactorInfo, PredictiveAnalysisMetadata } from '@/lib/types/emma'

interface PredictiveAnalysisDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  jobs: Record<string, PredictiveAnalysisMetadata>
}

/**
 * Floating Predictive Analysis Widget (queue-widget pattern)
 *
 * Shows active prediction jobs. Adapts VerifiedGenerationDialog pattern.
 */
export function PredictiveAnalysisDialog({ open, onOpenChange, jobs }: PredictiveAnalysisDialogProps) {
  const [isExpanded, setIsExpanded] = useState(true)

  const jobEntries = Object.entries(jobs)
  const jobCount = jobEntries.length

  if (jobCount === 0) return null

  const totalActive = jobEntries.reduce((sum, [, j]) => {
    return sum + j.factors.filter(f => f.status === 'extracting' || f.status === 'verifying').length
  }, 0)
  const totalWeighted = jobEntries.reduce((sum, [, j]) => sum + j.weighted_count, 0)
  const totalRejected = jobEntries.reduce((sum, [, j]) => sum + j.rejected_count, 0)
  const hasActiveJobs = jobEntries.some(([, j]) => j.current_phase !== 'complete')

  // Collapsed pill
  if (!open && hasActiveJobs) {
    return (
      <motion.button
        initial={{ scale: 0, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        className={cn(
          'fixed top-6 right-6 z-50',
          'flex items-center gap-2 px-4 py-3 rounded-full',
          'bg-blue-600 text-white shadow-lg',
          'hover:bg-blue-700 transition-colors'
        )}
        onClick={() => onOpenChange(true)}
      >
        <IconChartBar className="h-5 w-5 animate-pulse" />
        <span className="font-medium text-sm">
          {jobCount > 1 ? `${jobCount} análisis` : 'Analizando...'}
        </span>
      </motion.button>
    )
  }

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
                hasActiveJobs ? 'bg-blue-500/10' : 'bg-muted'
              )}>
                <IconChartBar className={cn(
                  'h-5 w-5',
                  hasActiveJobs ? 'text-blue-600 animate-pulse' : 'text-muted-foreground'
                )} />
              </div>
              <div>
                <h3 className="font-semibold text-sm">Análisis Predictivo</h3>
                <p className="text-xs text-muted-foreground">
                  {hasActiveJobs
                    ? `${totalActive} factor${totalActive !== 1 ? 'es' : ''} en progreso`
                    : `${totalWeighted} factores analizados`
                  }
                </p>
              </div>
            </div>

            <div className="flex items-center gap-1">
              <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setIsExpanded(!isExpanded)}>
                {isExpanded ? <IconChevronDown className="h-4 w-4" /> : <IconChevronUp className="h-4 w-4" />}
              </Button>
              <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => onOpenChange(false)}>
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
              <IconScale className="h-3 w-3 text-blue-500" />
              <span>{totalWeighted}</span>
            </div>
            {totalRejected > 0 && (
              <div className="flex items-center gap-1">
                <IconCircleX className="h-3 w-3 text-destructive" />
                <span>{totalRejected}</span>
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
                    <PredictiveJobSection key={id} job={job} />
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

function PredictiveJobSection({ job }: { job: PredictiveAnalysisMetadata }) {
  const { factors, current_phase, weighted_count, total_factors, case_description } = job
  const processedCount = factors.filter(f => f.status !== 'extracting').length
  const progressPercent = total_factors > 0 ? Math.round((processedCount / total_factors) * 100) : 0
  const isActive = current_phase !== 'complete'

  return (
    <div className="space-y-2">
      <div>
        <div className="flex items-center justify-between">
          <p className="text-xs text-muted-foreground font-mono truncate flex-1">
            {case_description.slice(0, 60)}{case_description.length > 60 ? '...' : ''}
          </p>
          <span className="text-[10px] font-mono text-muted-foreground ml-2">
            {processedCount}/{total_factors || '?'}
          </span>
        </div>
        <div className="h-1.5 bg-muted rounded-full overflow-hidden mt-1">
          <motion.div
            className="h-full bg-blue-500 rounded-full"
            initial={{ width: 0 }}
            animate={{ width: `${progressPercent}%` }}
            transition={{ duration: 0.3 }}
          />
        </div>
      </div>

      {factors.length > 0 && (
        <div className="space-y-1.5">
          {factors.map(factor => (
            <FactorJobItem key={factor.factor_id} factor={factor} />
          ))}
        </div>
      )}

      {factors.length === 0 && isActive && (
        <div className="text-center py-4 text-muted-foreground">
          <IconLoader2 className="h-5 w-5 mx-auto mb-1 animate-spin opacity-40" />
          <p className="text-xs">Extrayendo factores...</p>
        </div>
      )}
    </div>
  )
}

function FactorJobItem({ factor }: { factor: PredictiveFactorInfo }) {
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
    <div className="flex items-start gap-3 p-2.5 bg-muted/50 rounded-lg">
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
