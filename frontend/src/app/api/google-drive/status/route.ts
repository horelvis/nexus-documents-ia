import { auth } from '@clerk/nextjs/server'
import { NextResponse } from 'next/server'

const API_BASE =
  process.env.API_BASE_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  'http://localhost:8000'

export async function GET() {
  const { getToken, userId } = auth()

  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const token = await getToken()
  if (!token) {
    return NextResponse.json({ error: 'Unable to obtain auth token' }, { status: 401 })
  }

  const response = await fetch(`${API_BASE}/api/v1/google-drive/status`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })

  const data = await response.json()
  return NextResponse.json(data, { status: response.status })
}
