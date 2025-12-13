import { auth } from '@clerk/nextjs/server'
import { NextRequest, NextResponse } from 'next/server'

const API_BASE =
  process.env.API_BASE_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  'http://localhost:8000'

export async function POST(
  request: NextRequest,
  props: { params: Promise<{ templateId: string; sessionId: string }> }
) {
  const params = await props.params
  const { userId, getToken } = await auth()

  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const token = await getToken()
  if (!token) {
    return NextResponse.json({ error: 'Unable to obtain auth token' }, { status: 401 })
  }

  const payload =
    request.headers.get('content-type')?.includes('application/json')
      ? await request.json().catch(() => ({}))
      : {}

  const response = await fetch(
    `${API_BASE}/api/v1/engine-templates/${params.templateId}/edit-sessions/${params.sessionId}/finish`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
      cache: 'no-store',
    }
  )

  const data = await response.json()
  return NextResponse.json(data, { status: response.status })
}
