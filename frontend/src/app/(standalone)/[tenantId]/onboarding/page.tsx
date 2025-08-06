'use client'

import { Suspense, useEffect, useState } from 'react'
import { useUserContext } from '@/contexts/user-context'
import { useRouter, useSearchParams, useParams } from 'next/navigation'
import { NewUserOnboarding } from '@/components/auth/onboarding'
import { useUser } from '@clerk/nextjs'
import { syncUserWithBackend } from '@/lib/sync-user'
import { Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'

function OnboardingContent() {
  const { backendUser, isClerkLoaded, isSignedIn } = useUserContext()
  const { user: clerkUser } = useUser()
  const router = useRouter()
  const params = useParams()
  const searchParams = useSearchParams()
  const plan = searchParams.get('plan')
  const tenantId = params.tenantId as string
  const [isSyncing, setIsSyncing] = useState(false)
  const [syncError, setSyncError] = useState<string | null>(null)

  // Sync user with backend if needed
  useEffect(() => {
    const syncIfNeeded = async () => {
      if (!clerkUser || !isSignedIn || backendUser || isSyncing) return
      
      // If we have a Clerk user but no backend user, sync it
      if (plan === 'free') {
        setIsSyncing(true)
        try {
          await syncUserWithBackend(
            clerkUser.id,
            clerkUser.emailAddresses[0]?.emailAddress || '',
            clerkUser.fullName || clerkUser.firstName + ' ' + (clerkUser.lastName || ''),
            'free'
          )
          // Reload the page to refresh user context
          window.location.reload()
        } catch (error) {
          console.error('Failed to sync user:', error)
          setSyncError('Failed to create your account. Please try again.')
        } finally {
          setIsSyncing(false)
        }
      }
    }
    
    syncIfNeeded()
  }, [clerkUser, isSignedIn, backendUser, isSyncing, plan])

  // Redirect if not authenticated
  if (isClerkLoaded && !isSignedIn) {
    router.push('/auth/sign-in')
    return null
  }

  // Show syncing state
  if (isSyncing) {
    return (
      <div className="min-h-screen flex items-center justify-center relative z-10">
        <div className="text-center space-y-4">
          <Loader2 className="h-8 w-8 animate-spin mx-auto text-white" />
          <p className="text-gray-300">Setting up your account...</p>
        </div>
      </div>
    )
  }

  // Show error if sync failed
  if (syncError) {
    return (
      <div className="min-h-screen flex items-center justify-center relative z-10">
        <div className="text-center space-y-4">
          <p className="text-red-400">{syncError}</p>
          <Button onClick={() => window.location.reload()}>Try Again</Button>
        </div>
      </div>
    )
  }

  // If already completed onboarding, redirect to dashboard
  if (backendUser?.onboarding_completed) {
    router.push(`/${backendUser.tenant_id}/dashboard`)
    return null
  }

  const handleComplete = (tenantId?: string) => {
    if (tenantId) {
      router.push(`/${tenantId}/dashboard`)
    } else {
      // If no tenant ID, something went wrong
      console.error('No tenant ID after onboarding completion')
      router.push('/pricing')
    }
  }

  return <NewUserOnboarding onComplete={handleComplete} />
}

export default function OnboardingPage() {
  return (
    <div className="min-h-screen relative">
      {/* Landing page background */}
      <div className="fixed inset-0 bg-black -z-10"></div>
      <div className="absolute top-[-266px] left-[calc(55%-379px/2)] bg-purple-600/60 opacity-50 rounded-full blur-[10rem] w-[379px] h-[620px] -z-10"></div>
      <div className="absolute top-[-60px] left-[calc(50%-433px/2)] bg-purple-600/40 opacity-50 rounded-full blur-[15rem] w-[433px] h-[525px] -z-10"></div>
      
      <Suspense fallback={
        <div className="min-h-screen flex items-center justify-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-600"></div>
        </div>
      }>
        <OnboardingContent />
      </Suspense>
    </div>
  )
}