/**
 * Typed interrupt discriminated union + type guards for LangGraph HITL interrupts.
 *
 * Replaces stringly-typed `(value as any).type === 'hitl_review'` checks
 * with narrowing type guards that give full IntelliSense after the check.
 */
import type {
  HITLReviewRequest,
  HITLClarificationRequest,
  HITLConfirmationRequest,
} from '@/lib/types/emma'

export type TypedInterruptValue =
  | HITLReviewRequest
  | HITLClarificationRequest
  | HITLConfirmationRequest

export interface TypedInterrupt {
  value: TypedInterruptValue
  resumable: boolean
}

export function isHITLReview(v: unknown): v is HITLReviewRequest {
  return (
    v != null &&
    typeof v === 'object' &&
    (v as Record<string, unknown>).type === 'hitl_review' &&
    'action_request' in v &&
    'review_config' in v
  )
}

export function isClarification(v: unknown): v is HITLClarificationRequest {
  return (
    v != null &&
    typeof v === 'object' &&
    (v as Record<string, unknown>).type === 'clarification' &&
    'question' in v
  )
}

export function isConfirmation(v: unknown): v is HITLConfirmationRequest {
  return (
    v != null &&
    typeof v === 'object' &&
    (v as Record<string, unknown>).type === 'confirmation' &&
    'question' in v
  )
}

/**
 * Parse a raw interrupt object from `values.__interrupt__[0]` into a
 * strongly-typed TypedInterrupt, or null if unrecognized.
 */
export function parseInterrupt(raw: unknown): TypedInterrupt | null {
  if (!raw || typeof raw !== 'object') return null
  const obj = raw as Record<string, unknown>
  const value = obj.value
  const resumable = !!obj.resumable

  if (isHITLReview(value)) return { value, resumable }
  if (isClarification(value)) return { value, resumable }
  if (isConfirmation(value)) return { value, resumable }
  return null
}
