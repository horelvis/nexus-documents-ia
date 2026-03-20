import { NextRequest } from 'next/server'
import { backendUrl, proxyJson } from '../../proxy'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ threadId: string }> },
) {
  const { threadId } = await params
  return proxyJson(request, backendUrl(threadId, '/state'))
}
