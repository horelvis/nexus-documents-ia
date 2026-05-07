/**
 * useStreamSubmit — Submit handler for useStream with attachment support.
 *
 * Handles:
 * 1. Upload new file attachments via `uploadTempDocument`
 * 2. Collect indexed document IDs from attachments
 * 3. Build `config.configurable` with user context
 * 4. Call `stream.submit()` with `optimisticValues` and `streamMode`
 * 5. Retain uploaded file IDs across follow-up queries
 */
import { useCallback, useRef } from 'react'
import type { Attachment } from '@/lib/types/emma'
import { extractAgentSlug } from '@/lib/utils/parse-agent-mention'

// Use loose types to match the SDK's actual signatures without coupling
interface StreamLike {
  submit: (values: any, options?: any) => any
}

interface SubmitOptions {
  userId?: string
  deepReasoning: boolean
  uploadTempDocument: (file: File) => Promise<{ upload_id: string; filename: string }>
  onAuthError?: () => void
}

const SSO_TOKEN_KEY = 'nexus_sso_tokens'

function hasValidToken(): boolean {
  if (typeof window === 'undefined') return false
  const stored = sessionStorage.getItem(SSO_TOKEN_KEY)
  if (!stored) return false
  try {
    const tokens = JSON.parse(stored)
    if (!tokens.access_token) return false
    if (tokens.expires_at && Date.now() >= tokens.expires_at - 60000) return false
    return true
  } catch {
    return false
  }
}

export function useStreamSubmit(
  stream: StreamLike,
  options: SubmitOptions,
) {
  const { userId, deepReasoning, uploadTempDocument, onAuthError } = options

  // Retain uploaded file IDs across follow-up queries in the same session
  const sessionUploadIdsRef = useRef<string[]>([])
  const sessionDocIdRef = useRef<string | null>(null)
  const sessionIndexedDocIdsRef = useRef<string[]>([])

  const submit = useCallback(
    async (query: string, attachments?: Attachment[]) => {
      if (!userId) return

      if (!hasValidToken()) {
        onAuthError?.()
        return
      }

      // Build configurable context
      const configurable: Record<string, unknown> = {
        user_id: userId,
        deep_reasoning: deepReasoning,
      }

      // Upload new file attachments
      const uploadedDocs = attachments?.filter((a) => a.type === 'upload') || []
      if (uploadedDocs.length > 0) {
        const uploadResults = await Promise.all(
          uploadedDocs.map(async (doc) => {
            const result = await uploadTempDocument(doc.file)
            return result.upload_id
          }),
        )
        configurable.uploaded_file_ids = uploadResults
        sessionUploadIdsRef.current = [
          ...new Set([...sessionUploadIdsRef.current, ...uploadResults]),
        ]
      }

      // Indexed documents
      const indexedDocs = attachments?.filter((a) => a.type === 'indexed') || []
      if (indexedDocs.length > 0) {
        configurable.document_id = indexedDocs[0].documentId
        configurable.indexed_document_ids = indexedDocs.map((a) => a.documentId)
        sessionDocIdRef.current = indexedDocs[0].documentId
        sessionIndexedDocIdsRef.current = indexedDocs.map((a) => a.documentId)
      }

      // Re-attach previous document context for follow-up queries
      if (!configurable.uploaded_file_ids && sessionUploadIdsRef.current.length > 0) {
        configurable.uploaded_file_ids = sessionUploadIdsRef.current
      }
      if (!configurable.document_id && sessionDocIdRef.current) {
        configurable.document_id = sessionDocIdRef.current
      }
      if (!configurable.indexed_document_ids && sessionIndexedDocIdsRef.current.length > 0) {
        configurable.indexed_document_ids = sessionIndexedDocIdsRef.current
      }

      const userContent = query || (attachments?.length ? 'Analiza estos documentos' : '')
      const newMessage = { type: 'human' as const, content: userContent }

      // Extract @<slug> from the user input and forward as state field;
      // classify_node short-circuits to invoke_agent when present.
      const agentSlug = extractAgentSlug(userContent)

      stream.submit(
        agentSlug
          ? { messages: [newMessage], agent_slug: agentSlug }
          : { messages: [newMessage] },
        {
          streamMode: ['values', 'messages'],
          config: { configurable },
          optimisticValues: (prev: any) => ({
            ...prev,
            messages: [...(prev?.messages ?? []), newMessage],
            agent_slug: agentSlug ?? undefined,
            // Clear turn-specific fields to prevent stale metadata from
            // creating phantom progress bubbles in useMessageConverter
            reasoning_steps: [],
            sources: [],
            success: undefined,
            explanation: undefined,
            agent_metadata: undefined,
          }),
        },
      )
    },
    [stream, userId, deepReasoning, uploadTempDocument, onAuthError],
  )

  return { submit }
}
