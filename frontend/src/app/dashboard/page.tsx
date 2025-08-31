'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@clerk/nextjs'
import { useTenantService } from '@/lib/services/tenant.service'

export default function DashboardRedirect() {
  const { isLoaded, isSignedIn } = useAuth()
  const router = useRouter()
  const tenantService = useTenantService()

  useEffect(() => {
    if (!isLoaded) return

    if (!isSignedIn) {
      router.push('/auth/sign-in')
      return
    }

    const redirectToDashboard = async () => {
      try {
        const tenant = await tenantService.getCurrentTenant()
        router.push(`/${tenant.id}/dashboard`)
      } catch (error) {
        console.error('Error getting tenant:', error)
        // Fallback to default tenant
        router.push('/default/dashboard')
      }
    }

    redirectToDashboard()
  }, [isLoaded, isSignedIn, router, tenantService])

  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900 mx-auto"></div>
        <p className="mt-2 text-sm text-gray-600">Redirigiendo al dashboard...</p>
      </div>
    </div>
  )
}