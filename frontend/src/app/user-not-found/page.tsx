"use client"

import { Suspense, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useUserContext } from '@/contexts/user-context'
import { UserNotFound } from '@/components/errors/user-not-found'
import { InitialLoader } from '@/components/ui/unified-loader'

function UserNotFoundContent() {
  const router = useRouter()
  const { backendUser, userLoading, isClerkLoaded } = useUserContext()

  useEffect(() => {
    // If user exists in backend, redirect to dashboard
    if (isClerkLoaded && !userLoading && backendUser?.tenant_id) {
      console.log('[user-not-found] User exists, redirecting to dashboard')
      router.replace(`/${backendUser.tenant_id}/dashboard`)
    }
  }, [backendUser, userLoading, isClerkLoaded, router])

  // Show loader while checking
  if (!isClerkLoaded || userLoading) {
    return <InitialLoader />
  }

  // If user exists, show loader while redirecting
  if (backendUser?.tenant_id) {
    return <InitialLoader />
  }

  // User doesn't exist, show error page
  return <UserNotFound />
}

export default function UserNotFoundPage() {
  return (
    <Suspense fallback={<InitialLoader />}>
      <UserNotFoundContent />
    </Suspense>
  )
}
