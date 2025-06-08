"use client"

import { useAuth } from '@clerk/nextjs'
import { useRouter } from 'next/navigation'
import { useEffect } from 'react'
import { useUserContext } from '@/contexts/user-context'
import { 
  HeroSection, 
  FeaturesSection, 
  StatsSection, 
  PricingSection,
  CTASection, 
  LandingHeader, 
  LandingFooter 
} from "@/components/landing"

export default function Home() {
  const { isLoaded, isSignedIn } = useAuth()
  const { backendUser, userLoading } = useUserContext()
  const router = useRouter()

  // Auto-redirect signed in users to dashboard
  useEffect(() => {
    if (isLoaded && isSignedIn && backendUser && !userLoading) {
      const tenantId = backendUser.tenant_id
      router.push(`/${tenantId}/dashboard`)
    }
  }, [isLoaded, isSignedIn, backendUser, userLoading, router])

  if (!isLoaded || userLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-indigo-600"></div>
      </div>
    )
  }

  if (isSignedIn && backendUser) {
    return null // Will redirect to dashboard
  }

  return (
    <div className="min-h-screen bg-white">
      <LandingHeader />
      <main>
        <HeroSection />
        <FeaturesSection />
        <StatsSection />
        <PricingSection />
        <CTASection />
      </main>
      <LandingFooter />
    </div>
  )
}
