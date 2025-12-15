import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server'
import { NextResponse } from 'next/server'

const isPublicRoute = createRouteMatcher([
  '/',
  '/pricing',
  '/auth/sign-in(.*)',
  '/auth/sign-up(.*)',
  '/auth/sign-out(.*)',
  '/auth/redirect',
  '/user-not-found',
  '/tenant-not-found',
  '/shared/(.*)',  // Public share links
  '/integrations/(.*)',
  '/portal/(.*)'   // Site Guest portal (invitation-only, OTP auth)
])

const isSubscriptionRoute = createRouteMatcher([
  '/pricing',
  '/(.*)/plans',
  '/(.*)/checkout(.*)',
  '/auth/(.*)',
  '/(.*)/onboarding(.*)',
  '/auth/redirect'
])

export default clerkMiddleware(async (auth, req) => {
  // Check if route needs authentication
  if (!isPublicRoute(req)) {
    await auth.protect()
  }

  // Get the authenticated user
  const { userId } = await auth()

  // If user is authenticated and on a protected route, validate tenant and check subscription
  if (userId && !isPublicRoute(req) && !isSubscriptionRoute(req)) {
    try {
      // Extract tenant ID from URL path like /:tenantId/dashboard
      const url = req.nextUrl.clone()
      const pathSegments = url.pathname.split('/').filter(Boolean)
      const tenantId = pathSegments[0]

      // Only proceed if we have a tenant ID in the path
      if (tenantId && tenantId.length > 10) { // Basic UUID-like length check
        const backendUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

        try {
          // Get the session token for API calls
          const { getToken } = await auth()
          const token = await getToken()

          // First, validate that the tenant exists
          const tenantResponse = await fetch(`${backendUrl}/api/v1/tenants/validate/${tenantId}`, {
            method: 'GET',
            headers: {
              'Content-Type': 'application/json'
            }
          })

          if (!tenantResponse.ok) {
            // Tenant doesn't exist, redirect to error page
            console.log('[Middleware] Tenant not found, redirecting to error page:', tenantId)
            const errorUrl = new URL('/tenant-not-found', req.url)
            errorUrl.searchParams.set('tenantId', tenantId)
            return NextResponse.redirect(errorUrl)
          }

          // Tenant exists, now check user subscription status
          const userResponse = await fetch(`${backendUrl}/api/v1/auth/me`, {
            headers: {
              'Authorization': `Bearer ${token}`,
              'Content-Type': 'application/json'
            }
          })

          if (userResponse.ok) {
            const userData = await userResponse.json()

            // Check if user has valid subscription or trial
            const hasValidTrial = userData?.trial_ends_at &&
              new Date(userData.trial_ends_at) > new Date()
            const hasPaidSubscription = userData?.subscription_plan &&
              ['basic', 'pro', 'professional', 'enterprise'].includes(userData.subscription_plan)
            const hasActiveStatus = userData?.subscription_status &&
              ['active', 'trialing'].includes(userData.subscription_status)

            // If no valid subscription/trial, redirect to plans
            if (!hasValidTrial && !hasPaidSubscription && !hasActiveStatus) {
              console.log('[Middleware] No valid subscription, redirecting to plans')
              return NextResponse.redirect(new URL(`/${tenantId}/plans`, req.url))
            }
          } else if (userResponse.status === 404) {
            // User exists in Clerk but not registered in backend - redirect to user-not-found
            console.log('[Middleware] User in Clerk but not in backend, redirecting to user-not-found')
            return NextResponse.redirect(new URL('/user-not-found', req.url))
          }
        } catch (fetchError) {
          // If backend is unreachable, allow access (don't break the app)
          console.warn('[Middleware] Backend unreachable, allowing access:', fetchError)
        }
      }
    } catch (error) {
      // If any error occurs, log it but don't break the request
      console.error('[Middleware] Error in middleware:', error)
    }
  }
})

export const config = {
  matcher: [
    // Skip Next.js internals and all static files, unless found in search params
    '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
    // Always run for API routes
    '/(api|trpc)(.*)',
  ],
}
