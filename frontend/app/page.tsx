"use client"

import { useAuth } from '@clerk/nextjs'
import { useRouter } from 'next/navigation'
import { useEffect } from 'react'
import { 
  HeroSection, 
  FeaturesSection, 
  StatsSection, 
  CTASection, 
  LandingHeader, 
  LandingFooter 
} from "@/components/landing"

export default function Home() {
  const { isLoaded, isSignedIn } = useAuth()
  const router = useRouter()

  // Auto-redirect signed in users to dashboard
  useEffect(() => {
    if (isLoaded && isSignedIn) {
      router.push('/dashboard')
    }
  }, [isLoaded, isSignedIn, router])

  if (!isLoaded) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-indigo-600"></div>
      </div>
    )
  }

  if (isSignedIn) {
    return null // Will redirect to dashboard
  }

  return (
    <div className="min-h-screen bg-white">
      <LandingHeader />
      <main>
        <HeroSection />
        <FeaturesSection />
        <StatsSection />
        <CTASection />
      </main>
      <LandingFooter />
    </div>
  )
}
