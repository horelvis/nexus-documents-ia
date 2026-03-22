'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/contexts/auth-context'

/**
 * AdminGuard — Redirects non-admin users to home.
 *
 * Usage: wrap admin page content with <AdminGuard>...</AdminGuard>
 * Checks realm_access.roles from the Keycloak JWT for 'admin' or 'realm-admin'.
 */
export function AdminGuard({ children }: { children: React.ReactNode }) {
  const { isLoaded, isAuthenticated, isAdmin } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (isLoaded && (!isAuthenticated || !isAdmin)) {
      router.replace('/')
    }
  }, [isLoaded, isAuthenticated, isAdmin, router])

  if (!isLoaded) return null
  if (!isAuthenticated || !isAdmin) return null

  return <>{children}</>
}
