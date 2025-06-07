'use client'

import { ModernOnboarding } from "@/components/auth"
import { useRouter, useParams } from "next/navigation"

export default function WelcomePage() {
  const router = useRouter()
  const params = useParams()
  const tenantId = params.tenantId as string
  
  const handleOnboardingComplete = () => {
    router.push(`/${tenantId}/dashboard`)
  }

  return (
    <ModernOnboarding onComplete={handleOnboardingComplete} />
  )
}