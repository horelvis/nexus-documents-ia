"use client"

/**
 * Universal Authentication Guard
 *
 * Protects routes requiring authentication. Works with both:
 * - Clerk authentication (SaaS mode)
 * - SSO authentication (on-premise mode)
 *
 * Uses the unified auth context which automatically selects
 * the appropriate auth provider based on deployment mode.
 */

import { useRouter, usePathname } from 'next/navigation'
import { useEffect, useState } from 'react'
import { InitialLoader } from '@/components/ui/unified-loader'
import { useFeature, Feature, useDeploymentMode, DeploymentMode } from '@/lib/features'
import { useUserContext } from '@/contexts/user-context'

import type { AuthGuardProps } from '@/lib/types'

/**
 * AuthGuard for Clerk-based authentication (SaaS mode).
 */
function ClerkAuthGuard({ children, fallback }: AuthGuardProps) {
  const {
    isClerkLoaded,
    isSignedIn,
    onboarding: { loading: onboardingLoading },
    userLoading,
  } = useUserContext()
  const router = useRouter()

  useEffect(() => {
    if (isClerkLoaded && !isSignedIn) {
      router.push('/auth/sign-in')
    }
  }, [isClerkLoaded, isSignedIn, router])

  if (!isClerkLoaded || userLoading || onboardingLoading) {
    return fallback || <InitialLoader />
  }

  if (!isSignedIn) {
    return fallback || null
  }

  return <>{children}</>
}

/**
 * AuthGuard for SSO-based authentication (on-premise mode).
 */
function SSOAuthGuard({ children, fallback }: AuthGuardProps) {
  const router = useRouter()
  const pathname = usePathname()
  const [isChecking, setIsChecking] = useState(true)
  const [isAuthenticated, setIsAuthenticated] = useState(false)

  useEffect(() => {
    async function checkAuth() {
      // Check for stored tokens
      const storedTokens = sessionStorage.getItem('nexus_sso_tokens')

      if (!storedTokens) {
        // No tokens, check if this is the callback page
        if (pathname.includes('/auth/callback')) {
          setIsChecking(false)
          setIsAuthenticated(true) // Let the callback page handle auth
          return
        }

        // Redirect to SSO login
        try {
          const response = await fetch('/api/v1/auth/sso/login-url')
          if (response.ok) {
            const { login_url } = await response.json()
            if (login_url) {
              window.location.href = login_url
              return
            }
          }
        } catch (err) {
          console.error('[SSOAuthGuard] Failed to get login URL:', err)
        }

        // Fallback to sign-in page
        router.push('/auth/sign-in')
        return
      }

      // Tokens exist, verify they're valid
      try {
        const tokens = JSON.parse(storedTokens)
        const expiresAt = tokens.expires_at || 0

        if (Date.now() >= expiresAt) {
          // Token expired, try to refresh or re-authenticate
          sessionStorage.removeItem('nexus_sso_tokens')
          router.push('/auth/sign-in')
          return
        }

        setIsAuthenticated(true)
      } catch (err) {
        console.error('[SSOAuthGuard] Token validation failed:', err)
        sessionStorage.removeItem('nexus_sso_tokens')
        router.push('/auth/sign-in')
      } finally {
        setIsChecking(false)
      }
    }

    checkAuth()
  }, [pathname, router])

  if (isChecking) {
    return fallback || <InitialLoader />
  }

  if (!isAuthenticated) {
    return fallback || null
  }

  return <>{children}</>
}

/**
 * Universal AuthGuard component.
 *
 * Automatically selects the appropriate auth guard based on deployment mode:
 * - SaaS mode with Clerk enabled → ClerkAuthGuard
 * - On-premise mode or Clerk disabled → SSOAuthGuard
 *
 * Usage:
 *   <AuthGuard>
 *     <ProtectedContent />
 *   </AuthGuard>
 */
export function AuthGuard({ children, fallback }: AuthGuardProps) {
  const deploymentMode = useDeploymentMode()
  const useClerk = useFeature(Feature.CLERK_AUTH)
  const [isHydrated, setIsHydrated] = useState(false)

  // Wait for hydration to prevent mismatch
  useEffect(() => {
    setIsHydrated(true)
  }, [])

  // Show loading during hydration
  if (!isHydrated) {
    return fallback || <InitialLoader />
  }

  // In SaaS mode with Clerk enabled, use Clerk guard
  if (deploymentMode === DeploymentMode.SAAS && useClerk) {
    return <ClerkAuthGuard fallback={fallback}>{children}</ClerkAuthGuard>
  }

  // In on-premise mode or when Clerk is disabled, use SSO guard
  return <SSOAuthGuard fallback={fallback}>{children}</SSOAuthGuard>
}
