'use client'

import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Brain,
  ChevronDown,
  ChevronUp,
  X,
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  ExternalLink,
  Trash2
} from 'lucide-react'
import { useAnalysisQueue, type AnalysisJob } from '@/contexts/analysis-queue-context'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import Link from 'next/link'

/**
 * Status icon component
 */
function StatusIcon({ status }: { status: AnalysisJob['status'] }) {
  switch (status) {
    case 'completed':
      return <CheckCircle2 className="h-4 w-4 text-green-500" />
    case 'failed':
      return <XCircle className="h-4 w-4 text-destructive" />
    case 'processing':
      return <Loader2 className="h-4 w-4 text-primary animate-spin" />
    case 'pending':
    default:
      return <Clock className="h-4 w-4 text-muted-foreground" />
  }
}

/**
 * Status badge component
 */
function StatusBadge({ status }: { status: AnalysisJob['status'] }) {
  const variants: Record<string, string> = {
    pending: 'bg-muted text-muted-foreground',
    processing: 'bg-primary/10 text-primary',
    completed: 'bg-green-500/10 text-green-600',
    failed: 'bg-destructive/10 text-destructive'
  }

  const labels: Record<string, string> = {
    pending: 'Pendiente',
    processing: 'Procesando',
    completed: 'Completado',
    failed: 'Error'
  }

  return (
    <Badge variant="outline" className={cn('text-xs', variants[status])}>
      {labels[status]}
    </Badge>
  )
}

/**
 * Single job item in the queue
 */
function QueueJobItem({ job, onCancel }: { job: AnalysisJob; onCancel: (id: string) => void }) {
  const isActive = job.status === 'pending' || job.status === 'processing'
  const isProcessing = job.status === 'processing'
  // Allow navigation for completed AND processing jobs (to see live progress)
  const canNavigate = job.status === 'completed' || job.status === 'processing'

  return (
    <div className="flex items-center gap-3 p-3 bg-muted/50 rounded-lg">
      <StatusIcon status={job.status} />

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium truncate">
            {job.documentName || job.document_filename || 'Documento'}
          </p>
          <StatusBadge status={job.status} />
        </div>

        {isActive && (
          <div className="mt-1">
            <Progress value={job.progress} className="h-1" />
            {job.current_step && (
              <p className="text-xs text-muted-foreground mt-1 truncate">
                {job.current_step}
              </p>
            )}
          </div>
        )}

        {job.status === 'failed' && job.error_message && (
          <p className="text-xs text-destructive mt-1 truncate">
            {job.error_message}
          </p>
        )}
      </div>

      <div className="flex items-center gap-1">
        {canNavigate && (
          <Link href={`/documents/${job.document_id}/analysis?jobId=${job.id}`}>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              title={isProcessing ? 'Ver análisis en progreso' : 'Ver resultados'}
            >
              <ExternalLink className={cn(
                "h-4 w-4",
                isProcessing && "text-primary"
              )} />
            </Button>
          </Link>
        )}

        {isActive && (
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 text-muted-foreground hover:text-destructive"
            onClick={() => onCancel(job.id)}
            title="Cancelar análisis"
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        )}
      </div>
    </div>
  )
}

/**
 * Floating Analysis Queue Widget
 *
 * Shows analysis queue status in a floating panel.
 * Auto-appears when jobs are added to queue.
 */
export function AnalysisQueueWidget() {
  const {
    jobs,
    stats,
    activeJobs,
    pendingCount,
    processingCount,
    isWidgetOpen,
    setWidgetOpen,
    cancelJob,
    refreshQueue
  } = useAnalysisQueue()

  const [isExpanded, setIsExpanded] = useState(true)

  const activeCount = pendingCount + processingCount
  const hasActiveJobs = activeCount > 0

  // Don't render if no jobs and widget not manually opened
  if (jobs.length === 0 && !isWidgetOpen) {
    return null
  }

  // Auto-show widget when there are active jobs
  if (hasActiveJobs && !isWidgetOpen) {
    return (
      <motion.button
        initial={{ scale: 0, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        className={cn(
          'fixed bottom-6 right-6 z-50',
          'flex items-center gap-2 px-4 py-3 rounded-full',
          'bg-primary text-primary-foreground shadow-lg',
          'hover:bg-primary/90 transition-colors'
        )}
        onClick={() => setWidgetOpen(true)}
      >
        <Brain className="h-5 w-5 animate-pulse" />
        <span className="font-medium">{activeCount} análisis en progreso</span>
      </motion.button>
    )
  }

  // Show full widget panel
  return (
    <AnimatePresence>
      {isWidgetOpen && (
        <motion.div
          initial={{ opacity: 0, y: 100, scale: 0.95 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 100, scale: 0.95 }}
          transition={{ type: 'spring', damping: 25, stiffness: 300 }}
          className={cn(
            'fixed bottom-6 right-6 z-50',
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
                hasActiveJobs ? 'bg-primary/10' : 'bg-muted'
              )}>
                <Brain className={cn(
                  'h-5 w-5',
                  hasActiveJobs ? 'text-primary animate-pulse' : 'text-muted-foreground'
                )} />
              </div>
              <div>
                <h3 className="font-semibold">Cola de Análisis</h3>
                <p className="text-xs text-muted-foreground">
                  {activeCount > 0
                    ? `${activeCount} en progreso`
                    : `${stats?.completed_count || 0} completados`
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
                  <ChevronDown className="h-4 w-4" />
                ) : (
                  <ChevronUp className="h-4 w-4" />
                )}
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={() => setWidgetOpen(false)}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>

          {/* Stats Bar */}
          {stats && (
            <div className="flex items-center gap-4 px-4 py-2 bg-muted/20 border-b text-xs">
              <div className="flex items-center gap-1">
                <Clock className="h-3 w-3 text-muted-foreground" />
                <span>{stats.pending_count}</span>
              </div>
              <div className="flex items-center gap-1">
                <Loader2 className="h-3 w-3 text-primary" />
                <span>{stats.processing_count}</span>
              </div>
              <div className="flex items-center gap-1">
                <CheckCircle2 className="h-3 w-3 text-green-500" />
                <span>{stats.completed_count}</span>
              </div>
              <div className="flex items-center gap-1">
                <XCircle className="h-3 w-3 text-destructive" />
                <span>{stats.failed_count}</span>
              </div>
            </div>
          )}

          {/* Job List */}
          <AnimatePresence>
            {isExpanded && (
              <motion.div
                initial={{ height: 0 }}
                animate={{ height: 'auto' }}
                exit={{ height: 0 }}
                className="overflow-hidden"
              >
                <div className="p-3 space-y-2 max-h-80 overflow-y-auto">
                  {jobs.length === 0 ? (
                    <div className="text-center py-8 text-muted-foreground">
                      <Brain className="h-10 w-10 mx-auto mb-2 opacity-30" />
                      <p className="text-sm">No hay análisis en cola</p>
                    </div>
                  ) : (
                    jobs.slice(0, 10).map(job => (
                      <QueueJobItem
                        key={job.id}
                        job={job}
                        onCancel={cancelJob}
                      />
                    ))
                  )}

                  {jobs.length > 10 && (
                    <p className="text-xs text-center text-muted-foreground py-2">
                      +{jobs.length - 10} más en cola
                    </p>
                  )}
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Footer */}
          <div className="p-3 border-t bg-muted/20">
            <Button
              variant="outline"
              size="sm"
              className="w-full"
              onClick={refreshQueue}
            >
              Actualizar
            </Button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
