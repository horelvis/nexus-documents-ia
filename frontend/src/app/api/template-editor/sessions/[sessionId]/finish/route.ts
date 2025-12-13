/**
 * Finish Edit Session API Route
 */
import { NextRequest, NextResponse } from 'next/server'
import { auth } from '@clerk/nextjs/server'

const TEMPLATE_EDITOR_SERVICE_URL = process.env.TEMPLATE_EDITOR_SERVICE_URL || 'http://localhost:8011'
const MICROSERVICES_API_KEY = process.env.MICROSERVICES_API_KEY

/**
 * Finish editing session - sync changes and cleanup
 */
export async function POST(
  request: NextRequest,
  props: { params: Promise<{ sessionId: string }> }
) {
  try {
    const params = await props.params
    const { userId } = await auth()
    if (!userId) {
      return NextResponse.json(
        { error: 'Unauthorized' },
        { status: 401 }
      )
    }

    const body = await request.json()

    // Validate user is finishing their own session
    if (body.user_id !== userId) {
      return NextResponse.json(
        { error: 'Can only finish your own sessions' },
        { status: 403 }
      )
    }

    const response = await fetch(
      `${TEMPLATE_EDITOR_SERVICE_URL}/edit-sessions/${params.sessionId}/finish`,
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
        { error: data.detail || 'Failed to finish edit session' },
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