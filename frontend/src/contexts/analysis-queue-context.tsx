'use client'

import { createContext, useContext, useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useAuth } from '@clerk/nextjs'
import {
  useAnalysisQueueService,
  type AnalysisStatus,
  type AnalysisType,
  type AnalysisJobListItem,
  type AnalysisQueueStats,
  type AnalysisJobResult
} from '@/lib/services/analysis-queue.service'

// Re-export types for convenience
export type { AnalysisStatus, AnalysisType, AnalysisJobListItem, AnalysisQueueStats, AnalysisJobResult }

// Context Types
export interface AnalysisJob extends AnalysisJobListItem {
  documentName?: string
}

export interface AnalysisQueueContextType {
  // State
  jobs: AnalysisJob[]
  stats: AnalysisQueueStats | null
  isLoading: boolean
  error: string | null

  // Computed
  activeJobs: AnalysisJob[]
  completedJobs: AnalysisJob[]
  pendingCount: number
  processingCount: number

  // Actions
  addToQueue: (documentId: string, documentName: string, analysisType?: AnalysisType) => Promise<string | null>
  addBatchToQueue: (documents: { id: string; name: string }[], analysisType?: AnalysisType) => Promise<string[]>
  cancelJob: (jobId: string) => Promise<boolean>
  refreshQueue: () => Promise<void>
  getJobResult: (jobId: string) => Promise<AnalysisJobResult | null>

  // UI State
  isWidgetOpen: boolean
  setWidgetOpen: (open: boolean) => void
}

const AnalysisQueueContext = createContext<AnalysisQueueContextType | undefined>(undefined)

const POLL_INTERVAL_MS = 5000 // Poll every 5 seconds when there are active jobs
const IDLE_POLL_INTERVAL_MS = 30000 // Poll every 30 seconds when idle

interface AnalysisQueueProviderProps {
  children: React.ReactNode
}

export function AnalysisQueueProvider({ children }: AnalysisQueueProviderProps) {
  const { isSignedIn } = useAuth()
  const queueService = useAnalysisQueueService()

  // State
  const [jobs, setJobs] = useState<AnalysisJob[]>([])
  const [stats, setStats] = useState<AnalysisQueueStats | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isWidgetOpen, setWidgetOpen] = useState(false)

  // Track document names for display
  const documentNamesRef = useRef<Map<string, string>>(new Map())

  // Computed values
  const activeJobs = useMemo(() =>
    jobs.filter(j => j.status === 'pending' || j.status === 'processing'),
    [jobs]
  )

  const completedJobs = useMemo(() =>
    jobs.filter(j => j.status === 'completed' || j.status === 'failed'),
    [jobs]
  )

  const pendingCount = useMemo(() =>
    jobs.filter(j => j.status === 'pending').length,
    [jobs]
  )

  const processingCount = useMemo(() =>
    jobs.filter(j => j.status === 'processing').length,
    [jobs]
  )

  // Load queue data
  const refreshQueue = useCallback(async () => {
    if (!isSignedIn) return

    setIsLoading(true)
    setError(null)

    try {
      const response = await queueService.listJobs({ pageSize: 50 })

      // Merge with stored document names
      const jobsWithNames = response.jobs.map(job => ({
        ...job,
        documentName: job.document_filename ||
          documentNamesRef.current.get(job.document_id) ||
          'Documento'
      }))

      setJobs(jobsWithNames)
      setStats(response.stats)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Error loading queue'
      setError(message)
      console.error('[AnalysisQueue] Failed to refresh:', err)
    } finally {
      setIsLoading(false)
    }
  }, [isSignedIn, queueService])

  // Add document to queue
  const addToQueue = useCallback(async (
    documentId: string,
    documentName: string,
    analysisType: AnalysisType = 'legal'
  ): Promise<string | null> => {
    try {
      // Store document name for later display
      documentNamesRef.current.set(documentId, documentName)

      const result = await queueService.queueAnalysis(documentId, analysisType)

      // Add to local state immediately
      const newJob: AnalysisJob = {
        id: result.id,
        document_id: documentId,
        document_filename: documentName,
        documentName,
        status: result.status,
        progress: 0,
        analysis_type: analysisType,
        created_at: result.created_at
      }

      setJobs(prev => {
        // Check if job already exists (idempotent)
        const exists = prev.some(j => j.id === result.id)
        if (exists) return prev
        return [newJob, ...prev]
      })

      // Open widget to show progress
      setWidgetOpen(true)

      return result.id
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Error adding to queue'
      setError(message)
      console.error('[AnalysisQueue] Failed to add:', err)
      return null
    }
  }, [queueService])

  // Add batch to queue
  const addBatchToQueue = useCallback(async (
    documents: { id: string; name: string }[],
    analysisType: AnalysisType = 'legal'
  ): Promise<string[]> => {
    try {
      // Store document names
      documents.forEach(doc => {
        documentNamesRef.current.set(doc.id, doc.name)
      })

      const documentIds = documents.map(d => d.id)
      const results = await queueService.queueBatchAnalysis(documentIds, analysisType)

      // Add to local state
      const newJobs: AnalysisJob[] = results.map((result, idx) => ({
        id: result.id,
        document_id: result.document_id,
        document_filename: documents.find(d => d.id === result.document_id)?.name,
        documentName: documents.find(d => d.id === result.document_id)?.name || 'Documento',
        status: result.status,
        progress: 0,
        analysis_type: analysisType,
        created_at: result.created_at
      }))

      setJobs(prev => {
        const existingIds = new Set(prev.map(j => j.id))
        const uniqueNewJobs = newJobs.filter(j => !existingIds.has(j.id))
        return [...uniqueNewJobs, ...prev]
      })

      // Open widget
      setWidgetOpen(true)

      return results.map(r => r.id)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Error adding batch to queue'
      setError(message)
      console.error('[AnalysisQueue] Failed to add batch:', err)
      return []
    }
  }, [queueService])

  // Cancel job
  const cancelJob = useCallback(async (jobId: string): Promise<boolean> => {
    try {
      await queueService.cancelJob(jobId)

      // Update local state
      setJobs(prev => prev.map(job =>
        job.id === jobId
          ? { ...job, status: 'failed' as AnalysisStatus, error_message: 'Cancelled by user' }
          : job
      ))

      return true
    } catch (err) {
      console.error('[AnalysisQueue] Failed to cancel:', err)
      return false
    }
  }, [queueService])

  // Get job result
  const getJobResult = useCallback(async (jobId: string): Promise<AnalysisJobResult | null> => {
    try {
      return await queueService.getJobResult(jobId)
    } catch (err) {
      console.error('[AnalysisQueue] Failed to get result:', err)
      return null
    }
  }, [queueService])

  // Poll for updates when there are active jobs
  useEffect(() => {
    if (!isSignedIn) return

    const hasActiveJobs = activeJobs.length > 0
    const interval = hasActiveJobs ? POLL_INTERVAL_MS : IDLE_POLL_INTERVAL_MS

    const pollTimer = setInterval(() => {
      refreshQueue()
    }, interval)

    return () => clearInterval(pollTimer)
  }, [isSignedIn, activeJobs.length, refreshQueue])

  // Initial load
  useEffect(() => {
    if (isSignedIn) {
      refreshQueue()
    }
  }, [isSignedIn, refreshQueue])

  const contextValue = useMemo<AnalysisQueueContextType>(() => ({
    jobs,
    stats,
    isLoading,
    error,
    activeJobs,
    completedJobs,
    pendingCount,
    processingCount,
    addToQueue,
    addBatchToQueue,
    cancelJob,
    refreshQueue,
    getJobResult,
    isWidgetOpen,
    setWidgetOpen
  }), [
    jobs, stats, isLoading, error,
    activeJobs, completedJobs, pendingCount, processingCount,
    addToQueue, addBatchToQueue, cancelJob, refreshQueue, getJobResult,
    isWidgetOpen
  ])

  return (
    <AnalysisQueueContext.Provider value={contextValue}>
      {children}
    </AnalysisQueueContext.Provider>
  )
}

/**
 * Hook to access the analysis queue context
 */
export function useAnalysisQueue() {
  const context = useContext(AnalysisQueueContext)
  if (context === undefined) {
    throw new Error('useAnalysisQueue must be used within an AnalysisQueueProvider')
  }
  return context
}
