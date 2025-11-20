/**
 * Template preview generator
 * Converts HTML content into a PDF via Gotenberg and returns it as base64.
 */
import { NextRequest, NextResponse } from 'next/server'

const GOTENBERG_BASE_URL =
  process.env.GOTENBERG_BASE_URL ||
  process.env.NEXT_PUBLIC_GOTENBERG_BASE_URL ||
  'http://localhost:3000'

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const { html, fileName = 'template.html' } = body || {}

    if (!html || typeof html !== 'string') {
      return NextResponse.json(
        { error: 'html content is required' },
        { status: 400 }
      )
    }

    if (!GOTENBERG_BASE_URL) {
      return NextResponse.json(
        { error: 'Gotenberg URL is not configured' },
        { status: 500 }
      )
    }

    const formData = new FormData()
    const htmlFile = new File([html], 'index.html', { type: 'text/html' })
    formData.append('files', htmlFile, 'index.html')

    const response = await fetch(`${GOTENBERG_BASE_URL}/forms/chromium/convert/html`, {
      method: 'POST',
      body: formData,
      cache: 'no-store',
    })

    if (!response.ok) {
      const errorText = await response.text()
      return NextResponse.json(
        { error: `Gotenberg responded with ${response.status}: ${errorText}` },
        { status: response.status }
      )
    }

    const pdfBuffer = Buffer.from(await response.arrayBuffer())
    return NextResponse.json({
      pdfBase64: pdfBuffer.toString('base64'),
    })
  } catch (error) {
    console.error('Template preview generation failed', error)
    return NextResponse.json(
      { error: (error as Error).message || 'Failed to generate preview' },
      { status: 500 }
    )
  }
}
