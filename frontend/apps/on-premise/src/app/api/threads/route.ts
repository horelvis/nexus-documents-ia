import { NextRequest } from 'next/server'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const BACKEND_URL =
  process.env.BACKEND_URL ||
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  'http://localhost:8000'

export async function POST(request: NextRequest) {
  const body = await request.text()

  const response = await fetch(`${BACKEND_URL}/api/threads`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': request.headers.get('Authorization') || '',
      'X-Tenant-ID': request.headers.get('X-Tenant-ID') || '',
    },
    body,
  })

  const text = await response.text()

  // SDK expects { thread_id: "..." } but our API returns { session_id: "..." }
  // Map the field name for compatibility
  try {
    const data = JSON.parse(text)
    if (data.session_id && !data.thread_id) {
      data.thread_id = data.session_id
    }
    return new Response(JSON.stringify(data), {
      status: response.status,
      headers: { 'Content-Type': 'application/json' },
    })
  } catch {
    return new Response(text, {
      status: response.status,
      headers: { 'Content-Type': 'application/json' },
    })
  }
}
