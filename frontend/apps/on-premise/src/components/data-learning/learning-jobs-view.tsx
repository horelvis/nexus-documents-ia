'use client'

/**
 * Learning Jobs View Component
 *
 * Displays learning job history and status:
 * - Job type and status
 * - Progress for running jobs
 * - Results summary for completed jobs
 * - Error details for failed jobs
 */

import { useState, useEffect } from 'react'
import {
  IconLoader2,
  IconHistory,
  IconCircleCheck,
  IconCircleX,
  IconClock,
  IconPlayerPlay,
  IconBan,
  IconRefresh,
} from '@tabler/icons-react'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Badge,
  Button,
  Progress,
} from '@nexus/shared/ui'
import {
  dataLearningService,
  DataLearningJob,
  jobTypeLabels,
  jobStatusLabels,
  DataLearningJobStatus,
} from '@/lib/services/data-learning.service'

interface LearningJobsViewProps {
  connectorId: string
}

function getStatusIcon(status: DataLearningJobStatus) {
  switch (status) {
    case 'completed':
      return <IconCircleCheck className="h-4 w-4 text-green-500" />
    case 'failed':
      return <IconCircleX className="h-4 w-4 text-red-500" />
    case 'running':
      return <IconPlayerPlay className="h-4 w-4 text-blue-500" />
    case 'cancelled':
      return <IconBan className="h-4 w-4 text-gray-500" />
    case 'pending':
    default:
      return <IconClock className="h-4 w-4 text-yellow-500" />
  }
}

function getStatusBadge(status: DataLearningJobStatus) {
  const config: Record<DataLearningJobStatus, { variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
    pending: { variant: 'outline' },
    running: { variant: 'secondary' },
    completed: { variant: 'default' },
    failed: { variant: 'destructive' },
    cancelled: { variant: 'outline' },
  }
  return (
    <Badge variant={config[status].variant}>
      {jobStatusLabels[status]}
    </Badge>
  )
}

export function LearningJobsView({ connectorId }: LearningJobsViewProps) {
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [jobs, setJobs] = useState<DataLearningJob[]>([])
  const [cancellingId, setCancellingId] = useState<string | null>(null)

  const loadData = async () => {
    setIsLoading(true)
    setError(null)

    try {
      const result = await dataLearningService.getJobs(connectorId, { limit: 20 })
      if (result.data) {
        setJobs(result.data.items)
      } else if (result.error) {
        setError(result.error)
      }
    } catch (err: any) {
      setError(err.message || 'Error al cargar jobs')
    } finally {
      setIsLoading(false)
    }
  }

  const handleCancel = async (jobId: string) => {
    if (!confirm('¿Cancelar este job de aprendizaje?')) return

    setCancellingId(jobId)
    try {
      const result = await dataLearningService.cancelJob(connectorId, jobId)
      if (result.error) {
        setError(result.error)
      } else {
        await loadData()
      }
    } catch (err: any) {
      setError(err.message)
    } finally {
      setCancellingId(null)
    }
  }

  useEffect(() => {
    loadData()
  }, [connectorId])

  // Auto-refresh if there are running jobs
  useEffect(() => {
    const hasRunningJobs = jobs.some(j => j.status === 'running' || j.status === 'pending')
    if (!hasRunningJobs) return

    const interval = setInterval(loadData, 5000)
    return () => clearInterval(interval)
  }, [jobs])

  if (isLoading) {
    return (
      <Card>
        <CardContent className="py-12">
          <div className="flex items-center justify-center">
            <IconLoader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card>
        <CardContent className="py-12">
          <p className="text-center text-destructive">{error}</p>
        </CardContent>
      </Card>
    )
  }

  if (jobs.length === 0) {
    return (
      <Card>
        <CardContent className="py-12">
          <div className="text-center">
            <IconHistory className="h-12 w-12 mx-auto mb-4 text-muted-foreground opacity-50" />
            <p className="text-muted-foreground mb-2">
              No hay jobs de aprendizaje
            </p>
            <p className="text-sm text-muted-foreground">
              Inicia un aprendizaje para ver el historial aquí
            </p>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-lg flex items-center gap-2">
              <IconHistory className="h-5 w-5" />
              Historial de Jobs ({jobs.length})
            </CardTitle>
            <CardDescription>
              Jobs de aprendizaje ejecutados para este conector
            </CardDescription>
          </div>
          <Button variant="outline" size="sm" onClick={loadData}>
            <IconRefresh className="h-4 w-4" />
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {jobs.map((job) => (
            <div
              key={job.id}
              className="p-4 rounded-lg border bg-card"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-start gap-3">
                  {getStatusIcon(job.status)}
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-medium">{jobTypeLabels[job.job_type]}</span>
                      {getStatusBadge(job.status)}
                    </div>

                    {/* Progress for running jobs */}
                    {job.status === 'running' && (
                      <div className="space-y-1 mb-2">
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-muted-foreground">
                            {job.current_phase || 'Procesando...'}
                          </span>
                          <span>{job.progress_percent}%</span>
                        </div>
                        <Progress value={job.progress_percent} className="h-2" />
                      </div>
                    )}

                    {/* Results for completed jobs */}
                    {job.status === 'completed' && job.results_summary && (
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-2 text-xs">
                        {Object.entries(job.results_summary).map(([key, value]) => (
                          <div key={key} className="bg-muted/50 px-2 py-1 rounded">
                            <span className="text-muted-foreground">{key}:</span>{' '}
                            <span className="font-medium">{String(value)}</span>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Error message for failed jobs */}
                    {job.status === 'failed' && job.status_message && (
                      <div className="mt-2 text-sm text-destructive">
                        {job.status_message}
                      </div>
                    )}

                    {/* Errors list */}
                    {job.errors && job.errors.length > 0 && (
                      <div className="mt-2 space-y-1">
                        {job.errors.map((err, idx) => (
                          <div key={idx} className="text-xs text-destructive bg-destructive/10 px-2 py-1 rounded">
                            {err.phase}: {err.error}
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Timestamps */}
                    <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
                      <span>Creado: {new Date(job.created_at).toLocaleString()}</span>
                      {job.started_at && (
                        <span>Iniciado: {new Date(job.started_at).toLocaleString()}</span>
                      )}
                      {job.completed_at && (
                        <span>Completado: {new Date(job.completed_at).toLocaleString()}</span>
                      )}
                    </div>
                  </div>
                </div>

                {/* Cancel button for running/pending jobs */}
                {(job.status === 'running' || job.status === 'pending') && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleCancel(job.id)}
                    disabled={cancellingId === job.id}
                  >
                    {cancellingId === job.id ? (
                      <IconLoader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <IconBan className="h-4 w-4" />
                    )}
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
