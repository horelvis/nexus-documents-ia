import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

/**
 * On-Premise middleware — minimal.
 * Auth is handled client-side via OIDC/SAML (oidc-client-ts).
 * This middleware only handles basic route protection logic.
 */
export function middleware(request: NextRequest) {
  // Allow all requests through — OIDC auth is client-side
  return NextResponse.next()
}

export const config = {
  matcher: [
    // Skip Next.js internals and static files
    '/((?!_next|api/v1|[^?]*\\.(?:html?|css|mjs|js(?!on)|wasm|map|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
  ],
}
