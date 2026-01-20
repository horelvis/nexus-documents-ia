/**
 * Individual Session API Routes
 */
import { NextRequest, NextResponse } from 'next/server'
import { auth } from '@clerk/nextjs/server'

const TEMPLATE_EDITOR_SERVICE_URL = process.env.TEMPLATE_EDITOR_SERVICE_URL || 'http://localhost:8011'
const MICROSERVICES_API_KEY = process.env.MICROSERVICES_API_KEY

/**
 * Get edit session details
 */
export async function GET(
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

    const response = await fetch(
      `${TEMPLATE_EDITOR_SERVICE_URL}/edit-sessions/${params.sessionId}?user_id=${userId}`,
      {
        headers: {
          'Authorization': `Bearer ${MICROSERVICES_API_KEY}`
        }
      }
    )

    const data = await response.json()

    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || 'Failed to get edit session' },
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

/**
 * Cancel edit session
 */
export async function DELETE(
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

    const response = await fetch(
      `${TEMPLATE_EDITOR_SERVICE_URL}/edit-sessions/${params.sessionId}?user_id=${userId}`,
      {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${MICROSERVICES_API_KEY}`
        }
      }
    )

    if (!response.ok) {
      const data = await response.json()
      return NextResponse.json(
        { error: data.detail || 'Failed to cancel edit session' },
        { status: response.status }
      )
    }

    const data = await response.json()
    return NextResponse.json(data)

  } catch (error) {
    console.error('Template editor API error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}