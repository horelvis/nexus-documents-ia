'use client'

import { useState, useEffect, useCallback } from 'react'
import { useApiClient } from '@/lib/api-client'
import { useUserContext } from '@/contexts/user-context'

interface SubscriptionStatus {
  plan_type: string
  status: string
  is_active: boolean
  is_limited: boolean
  current_period_end: string | null
  can_reactivate: boolean
  permissions: {
    max_documents: number
    max_monthly_uploads: number
    can_upload_documents: boolean
    can_view_documents: boolean
    can_search_documents: boolean
    can_use_chat: boolean
    can_use_agents: boolean
    can_export_documents: boolean
    can_use_api: boolean
    max_file_size_mb: number
  }
  message: string
}

interface SubscriptionData {
  id: string
  plan_id: string
  status: string
  current_period_end: number
  subscription_status: SubscriptionStatus
}

interface UseSubscriptionReturn {
  subscriptionData: SubscriptionData | null
  subscriptionStatus: SubscriptionStatus | null
  loading: boolean
  error: string | null
  refetch: () => Promise<void>
  
  // Helper functions
  canPerformAction: (action: keyof SubscriptionStatus['permissions']) => boolean
  isLimited: boolean
  canReactivate: boolean
  planType: string
  
  // Permission checks
  canUploadDocuments: boolean
  canUseChat: boolean
  canUseAgents: boolean
  canExportDocuments: boolean
  canUseAPI: boolean
  
  // Limits
  maxDocuments: number
  maxMonthlyUploads: number
  maxFileSizeMB: number
}

export function useSubscription(): UseSubscriptionReturn {
  const apiClient = useApiClient()
  const { backendUser } = useUserContext()
  const [subscriptionData, setSubscriptionData] = useState<SubscriptionData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchSubscriptionStatus = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      
      // Check if we already have subscription info from user context
      if (backendUser?.subscription_plan && backendUser?.subscription_status) {
        const contextSubscription: SubscriptionData = {
          id: 'from_context',
          plan_id: backendUser.subscription_plan,
          status: backendUser.subscription_status,
          current_period_end: 0,
          subscription_status: {
            plan_type: backendUser.subscription_plan,
            status: backendUser.subscription_status,
            is_active: backendUser.subscription_status === 'active',
            is_limited: backendUser.subscription_status !== 'active',
            current_period_end: null,
            can_reactivate: backendUser.subscription_status === 'canceled' || backendUser.subscription_status === 'past_due',
            permissions: {
              max_documents: backendUser.subscription_plan === 'free' ? 10 : -1,
              max_monthly_uploads: backendUser.subscription_plan === 'free' ? 5 : -1,
              can_upload_documents: true,
              can_view_documents: true,
              can_search_documents: true,
              can_use_chat: backendUser.subscription_plan !== 'free',
              can_use_agents: backendUser.subscription_plan !== 'free',
              can_export_documents: backendUser.subscription_plan !== 'free',
              can_use_api: backendUser.subscription_plan !== 'free',
              max_file_size_mb: backendUser.subscription_plan === 'free' ? 10 : 100
            },
            message: ''
          }
        }
        setSubscriptionData(contextSubscription)
        setLoading(false)
        return
      }
      
      // Only make API call if we don't have subscription info
      const response = await apiClient.get('/stripe/subscription')
      
      if (response.error) {
        setError(response.error)
        return
      }
      
      setSubscriptionData(response.data)
    } catch (err) {
      setError('Error cargando estado de suscripción')
      console.error('Error fetching subscription:', err)
    } finally {
      setLoading(false)
    }
  }, [apiClient, backendUser])

  useEffect(() => {
    fetchSubscriptionStatus()
  }, [fetchSubscriptionStatus])

  const subscriptionStatus = subscriptionData?.subscription_status || null

  const canPerformAction = useCallback((action: keyof SubscriptionStatus['permissions']): boolean => {
    if (!subscriptionStatus) return false
    return subscriptionStatus.permissions[action] as boolean
  }, [subscriptionStatus])

  return {
    subscriptionData,
    subscriptionStatus,
    loading,
    error,
    refetch: fetchSubscriptionStatus,

    // Helper functions
    canPerformAction,
    isLimited: subscriptionStatus?.is_limited || false,
    canReactivate: subscriptionStatus?.can_reactivate || false,
    planType: subscriptionStatus?.plan_type || 'free',

    // Permission checks
    canUploadDocuments: canPerformAction('can_upload_documents'),
    canUseChat: canPerformAction('can_use_chat'),
    canUseAgents: canPerformAction('can_use_agents'),
    canExportDocuments: canPerformAction('can_export_documents'),
    canUseAPI: canPerformAction('can_use_api'),

    // Limits
    maxDocuments: subscriptionStatus?.permissions.max_documents || 0,
    maxMonthlyUploads: subscriptionStatus?.permissions.max_monthly_uploads || 0,
    maxFileSizeMB: subscriptionStatus?.permissions.max_file_size_mb || 0,
  }
}

// Hook específico para verificar si el usuario puede realizar una acción
export function useCanPerformAction(action: keyof SubscriptionStatus['permissions']) {
  const { canPerformAction, loading, subscriptionStatus } = useSubscription()
  
  return {
    canPerform: canPerformAction(action),
    loading,
    reason: subscriptionStatus?.is_limited 
      ? 'Tu suscripción ha expirado. Reactiva tu plan para continuar.'
      : subscriptionStatus?.message || ''
  }
}

// Hook para verificar límites de documentos
export function useDocumentLimits() {
  const { subscriptionStatus, loading } = useSubscription()
  
  return {
    maxDocuments: subscriptionStatus?.permissions.max_documents || 0,
    maxMonthlyUploads: subscriptionStatus?.permissions.max_monthly_uploads || 0,
    maxFileSizeMB: subscriptionStatus?.permissions.max_file_size_mb || 0,
    isUnlimited: (field: 'documents' | 'uploads' | 'fileSize') => {
      if (!subscriptionStatus) return false
      
      switch (field) {
        case 'documents':
          return subscriptionStatus.permissions.max_documents === -1
        case 'uploads':
          return subscriptionStatus.permissions.max_monthly_uploads === -1
        case 'fileSize':
          return subscriptionStatus.permissions.max_file_size_mb === -1
        default:
          return false
      }
    },
    loading
  }
}

export default useSubscription