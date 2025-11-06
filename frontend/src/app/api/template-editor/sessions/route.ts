/**
 * Template Editor Sessions API Routes
 * Proxy to template-editor-service microservice
 * Updated for debugging
 */
import { NextRequest, NextResponse } from 'next/server'
import { auth } from '@clerk/nextjs/server'

const TEMPLATE_EDITOR_SERVICE_URL = process.env.TEMPLATE_EDITOR_SERVICE_URL || 'http://localhost:8011'
const MICROSERVICES_API_KEY = process.env.MICROSERVICES_API_KEY

/**
 * Create new editing session
 */
export async function POST(request: NextRequest) {
  try {
    // Authenticate user
    const { userId } = await auth()
    if (!userId) {
      return NextResponse.json(
        { error: 'Unauthorized' },
        { status: 401 }
      )
    }

    const body = await request.json()
    
    // Debug logging
    console.log('🔐 API Route - Clerk userId:', userId)
    console.log('📝 API Route - Request body user_id:', body.user_id)
    console.log('🔍 API Route - Full body:', JSON.stringify(body, null, 2))
    
    // Use the authenticated user ID instead of the one from request body
    body.user_id = userId
    console.log('✅ Using authenticated user ID:', userId)

    // Forward request to microservice
    const response = await fetch(`${TEMPLATE_EDITOR_SERVICE_URL}/edit-sessions/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${MICROSERVICES_API_KEY}`
      },
      body: JSON.stringify(body)
    })

    const data = await response.json()

    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || 'Failed to create edit session' },
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
 * Get user sessions
 */
export async function GET(request: NextRequest) {
  try {
    const { userId } = await auth()
    if (!userId) {
      return NextResponse.json(
        { error: 'Unauthorized' },
        { status: 401 }
      )
    }

    const searchParams = request.nextUrl.searchParams
    const tenantId = searchParams.get('tenant_id')
    const includeCompleted = searchParams.get('include_completed') === 'true'

    if (!tenantId) {
      return NextResponse.json(
        { error: 'tenant_id is required' },
        { status: 400 }
      )
    }

    const response = await fetch(
      `${TEMPLATE_EDITOR_SERVICE_URL}/edit-sessions/user/${userId}?tenant_id=${tenantId}&include_completed=${includeCompleted}`,
      {
        headers: {
          'Authorization': `Bearer ${MICROSERVICES_API_KEY}`
        }
      }
    )

    const data = await response.json()

    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || 'Failed to get user sessions' },
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