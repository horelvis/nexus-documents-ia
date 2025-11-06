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
  const { backendUser } = useUserContext()
  const [subscriptionData, setSubscriptionData] = useState<SubscriptionData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Simple effect that only depends on the specific values we need
  useEffect(() => {
    if (!backendUser) {
      setLoading(false)
      setSubscriptionData(null)
      return
    }

    const { subscription_plan, subscription_status } = backendUser

    if (subscription_plan && subscription_status) {
      const contextSubscription: SubscriptionData = {
        id: 'from_context',
        plan_id: subscription_plan,
        status: subscription_status,
        current_period_end: 0,
        subscription_status: {
          plan_type: subscription_plan,
          status: subscription_status,
          is_active: subscription_status === 'active',
          is_limited: subscription_status !== 'active',
          current_period_end: null,
          can_reactivate: subscription_status === 'canceled' || subscription_status === 'past_due',
          permissions: {
            max_documents: subscription_plan === 'free' ? 10 : -1,
            max_monthly_uploads: subscription_plan === 'free' ? 5 : -1,
            can_upload_documents: true,
            can_view_documents: true,
            can_search_documents: true,
            can_use_chat: subscription_plan !== 'free',
            can_use_agents: subscription_plan !== 'free',
            can_export_documents: subscription_plan !== 'free',
            can_use_api: subscription_plan !== 'free',
            max_file_size_mb: subscription_plan === 'free' ? 10 : 100
          },
          message: ''
        }
      }
      setSubscriptionData(contextSubscription)
    }
    
    setLoading(false)
    setError(null)
  }, [backendUser?.subscription_plan, backendUser?.subscription_status])

  const refetch = useCallback(async () => {
    // For now, refetch just reprocesses the current data
    setLoading(true)
    // The useEffect will handle the update
  }, [])

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
    refetch,

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