import { NextRequest } from 'next/server'
import { backendUrl, proxySSE } from '../../../proxy'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ threadId: string }> },
) {
  const { threadId } = await params
  return proxySSE(request, backendUrl(threadId, '/runs/stream'))
}
