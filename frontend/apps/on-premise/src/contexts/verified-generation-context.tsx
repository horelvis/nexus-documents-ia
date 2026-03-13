'use client'

/**
 * Verified Generation Context
 *
 * Holds verified generation job state at layout level so the floating
 * progress dialog persists across page navigation. EmmaChat writes to
 * this context; the dialog reads from it and renders in the layout.
 */

import { createContext, useContext, useState, useRef, useCallback } from 'react'
import { VerifiedGenerationMetadata } from '@/lib/types/emma'
import type { ReviewDecision } from '@/lib/services/verified-generation.service'

/** Callback type for HITL review submission */
export type ReviewSubmitHandler = (jobId: string, decisions: ReviewDecision[]) => void

interface VerifiedGenerationContextValue {
  /** Whether the floating dialog is open */
  dialogOpen: boolean
  setDialogOpen: (open: boolean) => void

  /** Active verification jobs keyed by job ID */
  jobs: Record<string, VerifiedGenerationMetadata>
  jobsRef: React.MutableRefObject<Record<string, VerifiedGenerationMetadata>>

  /** Add or update a job */
  updateJob: (jobId: string, updater: (prev: VerifiedGenerationMetadata) => VerifiedGenerationMetadata) => void
  /** Set a job (for initial creation) */
  setJob: (jobId: string, job: VerifiedGenerationMetadata) => void
  /** Remove a job */
  removeJob: (jobId: string) => void

  /** HITL: register a review handler (set by EmmaChat) */
  reviewHandler: React.MutableRefObject<ReviewSubmitHandler | null>
}

const VerifiedGenerationContext = createContext<VerifiedGenerationContextValue | null>(null)

export function VerifiedGenerationProvider({ children }: { children: React.ReactNode }) {
  const [dialogOpen, setDialogOpen] = useState(false)
  const [jobs, setJobs] = useState<Record<string, VerifiedGenerationMetadata>>({})
  const jobsRef = useRef<Record<string, VerifiedGenerationMetadata>>({})
  const reviewHandler = useRef<ReviewSubmitHandler | null>(null)

  const setJob = useCallback((jobId: string, job: VerifiedGenerationMetadata) => {
    setJobs((prev) => {
      const updated = { ...prev, [jobId]: job }
      jobsRef.current = updated
      return updated
    })
  }, [])

  const updateJob = useCallback((jobId: string, updater: (prev: VerifiedGenerationMetadata) => VerifiedGenerationMetadata) => {
    setJobs((prev) => {
      const current = prev[jobId]
      if (!current) return prev
      const next = updater(current)
      const updated = { ...prev, [jobId]: next }
      jobsRef.current = updated
      return updated
    })
  }, [])

  const removeJob = useCallback((jobId: string) => {
    setJobs((prev) => {
      const { [jobId]: _, ...rest } = prev
      jobsRef.current = rest
      return rest
    })
  }, [])

  return (
    <VerifiedGenerationContext.Provider
      value={{ dialogOpen, setDialogOpen, jobs, jobsRef, updateJob, setJob, removeJob, reviewHandler }}
    >
      {children}
    </VerifiedGenerationContext.Provider>
  )
}

export function useVerifiedGeneration() {
  const ctx = useContext(VerifiedGenerationContext)
  if (!ctx) throw new Error('useVerifiedGeneration must be used within VerifiedGenerationProvider')
  return ctx
}
