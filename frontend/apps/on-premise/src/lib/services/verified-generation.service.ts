"use client"

/**
 * Verified Generation Service
 *
 * SSE streaming client for the "Agent Self-Verifies" pattern.
 * Each claim is generated and verified against Weaviate before acceptance.
 */

import { API_CONFIG } from '../config'
import { VerifiedClaimInfo } from '../types/emma'

const SSO_TOKEN_KEY = 'nexus_sso_tokens'

function getAccessToken(): string | null {
  if (typeof window === 'undefined') return null
  const stored = sessionStorage.getItem(SSO_TOKEN_KEY)
  if (!stored) return null
  try {
    const tokens = JSON.parse(stored)
    return tokens.access_token || null
  } catch {
    return null
  }
}

// Direct backend URL for SSE (bypasses Next.js proxy buffering)
const STREAMING_API_URL = `${API_CONFIG.STREAMING_BASE_URL}/api/v1`

export type VerifiedEventType =
  | 'claim_generated'
  | 'verification_started'
  | 'claim_verified'
  | 'claim_corrected'
  | 'claim_rejected'
  | 'verification_timeout'
  | 'document_complete'
  | 'error'
  | 'progress'

export interface VerifiedStreamEvent {
  event_type: VerifiedEventType
  claim_id: string | null
  data: Record<string, any>
  timestamp: string
  progress_percent: number | null
}

export interface VerifiedGenerateParams {
  query: string
  tenant_id: string
  session_id?: string
  max_claims?: number
  context_document_ids?: string[]
  uploaded_file_ids?: string[]
  confidence_threshold?: number
}

/**
 * Stream verified document generation via SSE.
 * Yields parsed events as they arrive from the backend.
 */
export async function* queryVerifiedStream(
  params: VerifiedGenerateParams
): AsyncGenerator<VerifiedStreamEvent, void, unknown> {
  const token = getAccessToken()
  const streamUrl = `${STREAMING_API_URL}${API_CONFIG.ENDPOINTS.EMMA_VERIFIED_STREAM}`

  const response = await fetch(streamUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token || ''}`,
    },
    body: JSON.stringify(params),
  })

  if (!response.ok) {
    let errorDetail = ''
    try {
      const errorBody = await response.json()
      errorDetail = errorBody?.detail || errorBody?.message || ''
    } catch {
      // not JSON
    }
    throw new Error(errorDetail || `Verified stream request failed: ${response.status}`)
  }

  const reader = response.body?.getReader()
  if (!reader) throw new Error('No response body')

  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (value) {
        buffer += decoder.decode(value, { stream: !done })
      }

      // The backend emits "data: {json}\n\n" format (no named events)
      const parts = buffer.split('\n\n')
      if (done) {
        buffer = ''
        for (const part of parts) {
          const evt = parseSsePart(part)
          if (evt) {
            console.log('[VerifiedGen] SSE parsed event:', evt.event_type, evt.claim_id)
            yield evt
          } else if (part.trim()) {
            console.warn('[VerifiedGen] Unparsed SSE part:', part.slice(0, 200))
          }
        }
        break
      } else {
        buffer = parts.pop() || ''
        for (const part of parts) {
          const evt = parseSsePart(part)
          if (evt) {
            console.log('[VerifiedGen] SSE parsed event:', evt.event_type, evt.claim_id)
            yield evt
          } else if (part.trim()) {
            console.warn('[VerifiedGen] Unparsed SSE part:', part.slice(0, 200))
          }
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}

function parseSsePart(part: string): VerifiedStreamEvent | null {
  const trimmed = part.trim()
  if (!trimmed || !trimmed.startsWith('data:')) return null
  const jsonStr = trimmed.slice('data:'.length).trim()
  if (!jsonStr) return null
  try {
    return JSON.parse(jsonStr) as VerifiedStreamEvent
  } catch {
    console.warn('[VerifiedGen] Failed to parse SSE:', jsonStr.slice(0, 100))
    return null
  }
}

/**
 * Map a VerifiedStreamEvent to a partial VerifiedClaimInfo update.
 */
export function mapEventToClaim(event: VerifiedStreamEvent): Partial<VerifiedClaimInfo> & { claim_id: string } | null {
  const { event_type, claim_id, data } = event
  if (!claim_id) return null

  switch (event_type) {
    case 'claim_generated':
      return {
        claim_id,
        claim_number: data.claim_number || data.generation_order || 0,
        total_expected: data.total_expected || 0,
        claim_text: data.claim_text || data.text || '',
        status: 'generating',
      }
    case 'verification_started':
      return {
        claim_id,
        status: 'verifying',
      }
    case 'claim_verified':
      return {
        claim_id,
        status: 'verified',
        claim_text: data.claim_text || data.text,
        confidence: data.confidence,
        evidence_count: data.evidence?.length || data.evidence_count || 0,
      }
    case 'claim_corrected':
      return {
        claim_id,
        status: 'corrected',
        claim_text: data.corrected_text || data.correction || data.claim_text || data.text,
        confidence: data.confidence,
        evidence_count: data.evidence?.length || data.evidence_count || 0,
        original_text: data.original_text,
      }
    case 'claim_rejected':
      return {
        claim_id,
        status: 'rejected',
        claim_text: data.claim_text || data.text,
        confidence: data.confidence,
      }
    default:
      return null
  }
}
