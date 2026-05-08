'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/contexts/auth-context'

/**
 * AdminGuard — Redirects non-admin users to home.
 *
 * Usage: wrap admin page content with <AdminGuard>...</AdminGuard>
 * Reads `isAdmin` from the auth context, which derives from `User.is_superuser`
 * on the backend response. KeyCloak roles are NOT consulted for admin gating
 * after the role-based ACL removal (2026-05-04).
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
