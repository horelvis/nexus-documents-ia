/**
 * Extend Edit Session API Route
 */
import { NextRequest, NextResponse } from 'next/server'
import { auth } from '@clerk/nextjs/server'

const TEMPLATE_EDITOR_SERVICE_URL = process.env.TEMPLATE_EDITOR_SERVICE_URL || 'http://localhost:8011'
const MICROSERVICES_API_KEY = process.env.MICROSERVICES_API_KEY

/**
 * Extend edit session expiration time
 */
export async function POST(
  request: NextRequest,
  { params }: { params: { sessionId: string } }
) {
  try {
    const { userId } = await auth()
    if (!userId) {
      return NextResponse.json(
        { error: 'Unauthorized' },
        { status: 401 }
      )
    }

    const body = await request.json()
    
    // Validate user is extending their own session
    if (body.user_id !== userId) {
      return NextResponse.json(
        { error: 'Can only extend your own sessions' },
        { status: 403 }
      )
    }

    const response = await fetch(
      `${TEMPLATE_EDITOR_SERVICE_URL}/edit-sessions/${params.sessionId}/extend`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${MICROSERVICES_API_KEY}`
        },
        body: JSON.stringify(body)
      }
    )

    const data = await response.json()

    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || 'Failed to extend edit session' },
        { status: response.status }
      )
    }

    return NextResponse.json(data)

  } catch (error) {
    console.error('Template editor API error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}