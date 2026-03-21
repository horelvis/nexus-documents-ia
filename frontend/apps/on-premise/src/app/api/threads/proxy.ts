/**
 * Shared proxy helpers for LangGraph protocol route handlers.
 *
 * These route handlers exist because Next.js rewrites() buffer responses,
 * which breaks SSE streaming. Route handlers can pipe ReadableStreams
 * directly to the browser.
 */
import { NextRequest } from 'next/server'

const BACKEND_URL =
  process.env.BACKEND_URL ||
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  'http://localhost:8000'

/** Forward auth and tenant headers from the incoming request. */
function forwardHeaders(request: NextRequest): Record<string, string> {
  return {
    'Authorization': request.headers.get('Authorization') || '',
    'X-Tenant-ID': request.headers.get('X-Tenant-ID') || '',
  }
}

/** Build the backend URL for a thread endpoint (LangGraph protocol). */
export function backendUrl(threadId: string, suffix: string): string {
  return `${BACKEND_URL}/api/threads/${threadId}${suffix}`
}

/** Proxy a JSON request/response (non-streaming). */
export async function proxyJson(
  request: NextRequest,
  url: string,
  method: string = 'GET',
): Promise<Response> {
  const headers: Record<string, string> = {
    ...forwardHeaders(request),
    'Content-Type': 'application/json',
  }

  const init: RequestInit = { method, headers }
  if (method === 'POST') {
    init.body = await request.text()
  }

  const response = await fetch(url, init)
  const text = await response.text()
  return new Response(text, {
    status: response.status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** Proxy an SSE stream (pipes ReadableStream without buffering). */
export async function proxySSE(
  request: NextRequest,
  url: string,
): Promise<Response> {
  const body = await request.text()

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      ...forwardHeaders(request),
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream',
    },
    body,
  })

  if (!response.ok || !response.body) {
    const text = await response.text().catch(() => response.statusText)
    return new Response(text, { status: response.status })
  }

  return new Response(response.body, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache, no-transform',
      'Connection': 'keep-alive',
      'X-Accel-Buffering': 'no',
    },
  })
}
