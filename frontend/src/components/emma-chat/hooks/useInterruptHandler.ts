/**
 * useInterruptHandler — Typed interrupt detection + resume for LangGraph HITL.
 *
 * Reads `stream.interrupt` and parses it into a strongly-typed TypedInterrupt.
 * Provides `handleResume` that calls `stream.submit` with the correct
 * `Command(resume=value)` shape.
 */
import { useCallback } from 'react'
import { parseInterrupt, type TypedInterrupt } from '../types/interrupts'

interface StreamLike {
  interrupt?: { value?: unknown; resumable?: boolean } | null | undefined
  submit: (values: any, options?: any) => any
}

export function useInterruptHandler(stream: StreamLike) {
  const pendingInterrupt: TypedInterrupt | null = stream.interrupt
    ? parseInterrupt(stream.interrupt)
    : null

  const handleResume = useCallback(
    (value: unknown) => {
      stream.submit(undefined, { command: { resume: value } })
    },
    [stream],
  )

  return { pendingInterrupt, handleResume }
}
