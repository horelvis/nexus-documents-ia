"use client"

import { useAuth } from '@clerk/nextjs'
import { useRouter } from 'next/navigation'
import { useEffect } from 'react'
import { useUserContext } from '@/contexts/user-context'
import { InitialLoader } from '@/components/ui/unified-loader'
import { NexusNavbar, SectionContainer, HomeSection } from "@/components/landing/nexus-theme"
import { DemoRequestProvider } from "@/components/landing/nexus-theme/demo-request-provider"

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
    return <InitialLoader />
  }

  if (isSignedIn && backendUser) {
    return null // Will redirect to dashboard
  }

  return (
    <DemoRequestProvider>
      <div className="min-h-screen bg-background">
        <NexusNavbar />
        <SectionContainer>
          <div className="relative flex flex-col items-center justify-center px-4 pt-20">
            <HomeSection />
          </div>
        </SectionContainer>
      </div>
    </DemoRequestProvider>
  )
}
