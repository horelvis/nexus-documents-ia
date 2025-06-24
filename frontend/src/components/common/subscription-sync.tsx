'use client'

import { useEffect, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { useAuth } from '@clerk/nextjs'
import { useNotifications } from '@/contexts/app-state-context'
import { useUserContext } from '@/contexts/user-context'
import { Loader2 } from 'lucide-react'

export function SubscriptionSync() {
  const searchParams = useSearchParams()
  const { getToken } = useAuth()
  const { addNotification } = useNotifications()
  const { checkOnboardingStatus } = useUserContext()
  const [isSyncing, setIsSyncing] = useState(false)
  const [hasSynced, setHasSynced] = useState(false)

  useEffect(() => {
    const shouldSync = searchParams.get('sync') === 'true'
    const upgraded = searchParams.get('upgraded') === 'true'

    // Only sync once per page load
    if (shouldSync && !isSyncing && !hasSynced) {
      console.log('SubscriptionSync: Starting sync process...')
      syncSubscription(upgraded)
    }
  }, [searchParams, isSyncing, hasSynced])

  const syncSubscription = async (upgraded: boolean) => {
    setIsSyncing(true)
    setHasSynced(true) // Mark as synced to prevent duplicate calls
    
    try {
      const token = await getToken()
      const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
      
      console.log('SubscriptionSync: Calling sync endpoint...')
      
      // First sync the subscription from Stripe
      const syncResponse = await fetch(`${API_BASE}/api/v1/stripe/sync-subscription`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        }
      })

      if (syncResponse.ok) {
        const syncData = await syncResponse.json()
        console.log('SubscriptionSync: Sync response:', syncData)
        
        // Refresh user data to get updated subscription info
        await checkOnboardingStatus()
        
        if (upgraded) {
          addNotification({
            type: 'success',
            title: '¡Actualización exitosa!',
            message: 'Tu plan ha sido actualizado correctamente. Ya puedes disfrutar de todas las funciones.'
          })
        }
        
        // Remove query params from URL
        const url = new URL(window.location.href)
        url.searchParams.delete('sync')
        url.searchParams.delete('upgraded')
        window.history.replaceState({}, '', url)
      } else {
        const errorData = await syncResponse.json().catch(() => ({}))
        console.error('SubscriptionSync: Sync error:', errorData)
        throw new Error(errorData.detail || 'Failed to sync subscription')
      }
    } catch (error) {
      console.error('SubscriptionSync: Error syncing subscription:', error)
      addNotification({
        type: 'warning',
        title: 'Sincronización pendiente',
        message: 'Tu pago se procesó correctamente. La actualización puede tardar unos minutos.'
      })
    } finally {
      setIsSyncing(false)
    }
  }

  if (isSyncing) {
    return (
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center">
        <div className="bg-white dark:bg-gray-900 rounded-lg p-6 flex flex-col items-center gap-4">
          <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
          <p className="text-lg font-medium">Actualizando tu suscripción...</p>
          <p className="text-sm text-muted-foreground">Esto solo tomará un momento</p>
        </div>
      </div>
    )
  }

  return null
}