'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useAuth } from '@clerk/nextjs'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Separator } from '@/components/ui/separator'
import { 
  CreditCard, 
  ExternalLink, 
  Crown, 
  Zap, 
  Star,
  Shield,
  AlertCircle,
  Loader2,
  Calendar,
  DollarSign
} from 'lucide-react'
import { useUserContext } from '@/contexts/user-context'
import { useTranslation } from '@/lib/i18n/hooks'

interface SubscriptionData {
  id: string
  plan_id: string
  status: string
  interval: string
  current_period_start: number
  current_period_end: number
  cancel_at_period_end: boolean
  customer_id: string
}

export default function BillingPage() {
  const params = useParams()
  const router = useRouter()
  const { getToken } = useAuth()
  const { backendUser, userLoading } = useUserContext()
  const { t, language } = useTranslation()
  
  const [subscription, setSubscription] = useState<SubscriptionData | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isLoadingPortal, setIsLoadingPortal] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const isAdminUser = backendUser?.is_superuser || false

  useEffect(() => {
    if (!isAdminUser && !userLoading) {
      router.push(`/${params.tenantId}/dashboard`)
      return
    }

    if (isAdminUser) {
      fetchSubscription()
    }
  }, [isAdminUser, userLoading, params.tenantId, router])

  const fetchSubscription = async () => {
    try {
      setIsLoading(true)
      const token = await getToken()
      const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
      
      const response = await fetch(`${API_BASE}/api/v1/stripe/subscription`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      })

      if (response.ok) {
        const data = await response.json()
        setSubscription(data)
      } else {
        throw new Error(t('billingPage.error'))
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t('billingPage.unknownError'))
    } finally {
      setIsLoading(false)
    }
  }

  const openStripePortal = async () => {
    try {
      setIsLoadingPortal(true)
      const token = await getToken()
      const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
      
      const response = await fetch(`${API_BASE}/api/v1/stripe/create-customer-portal`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      })

      if (response.ok) {
        const { portal_url } = await response.json()
        window.open(portal_url, '_blank')
      } else {
        throw new Error(t('billingPage.createPortalError'))
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t('billingPage.openPortalError'))
    } finally {
      setIsLoadingPortal(false)
    }
  }

  const getPlanIcon = (planId: string) => {
    switch (planId) {
      case 'enterprise':
        return <Crown className="h-5 w-5 text-purple-600" />
      case 'pro':
        return <Zap className="h-5 w-5 text-blue-600" />
      default:
        return <Star className="h-5 w-5 text-gray-600" />
    }
  }

  const getPlanDisplayName = (planId: string) => {
    const planKey = `billingPage.plans.${planId}`
    const displayName = t(planKey)
    return displayName === planKey ? planId : displayName
  }

  const getStatusBadgeVariant = (status: string) => {
    switch (status) {
      case 'active':
        return 'default'
      case 'past_due':
        return 'destructive'
      case 'canceled':
        return 'secondary'
      default:
        return 'outline'
    }
  }

  const formatDate = (timestamp: number) => {
    const locale = language === 'es' ? 'es-ES' : 'en-US';
    return new Date(timestamp * 1000).toLocaleDateString(locale, {
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    })
  }

  if (userLoading || !backendUser) {
    return (
      <div className="flex items-center justify-center min-h-96">
        <Loader2 className="h-8 w-8 animate-spin" />
      </div>
    )
  }

  if (!isAdminUser) {
    return (
      <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6">
        <div className="px-4 lg:px-6">
          <Alert>
            <Shield className="h-4 w-4" />
            <AlertDescription>
              {t('billingPage.onlyAdmin')}
            </AlertDescription>
          </Alert>
        </div>
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6">
        <div className="px-4 lg:px-6">
          <div className="mb-8">
            <h1 className="text-3xl font-bold mb-2">{t('billingPage.title')}</h1>
            <p className="text-muted-foreground">
              {t('billingPage.subtitle')}
            </p>
          </div>
          
          <div className="flex items-center justify-center min-h-96">
            <Loader2 className="h-8 w-8 animate-spin" />
          </div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6">
        <div className="px-4 lg:px-6">
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6">
      <div className="px-4 lg:px-6">
        <div className="mb-8">
          <h1 className="text-3xl font-bold mb-2">{t('billingPage.title')}</h1>
          <p className="text-muted-foreground">
            {t('billingPage.subtitle')}
          </p>
        </div>

        {subscription && (
          <div className="grid gap-6">
            {/* Current Plan Card */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-3">
                    {getPlanIcon(subscription.plan_id)}
                    <div>
                      <CardTitle className="text-xl">
                        {getPlanDisplayName(subscription.plan_id)}
                      </CardTitle>
                      <CardDescription>
                        {t('billingPage.currentPlan.title')}
                      </CardDescription>
                    </div>
                  </div>
                  <Badge variant={getStatusBadgeVariant(subscription.status)}>
                    {subscription.status.charAt(0).toUpperCase() + subscription.status.slice(1)}
                  </Badge>
                </div>
              </CardHeader>
              
              <CardContent className="space-y-4">
                {subscription.plan_id !== 'free' && (
                  <>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="flex items-center space-x-2">
                        <Calendar className="h-4 w-4 text-muted-foreground" />
                        <div>
                          <p className="text-sm font-medium">{t('billingPage.currentPlan.billingCycle')}</p>
                          <p className="text-sm text-muted-foreground capitalize">
                            {subscription.interval === 'month' ? t('billingPage.currentPlan.monthly') : t('billingPage.currentPlan.yearly')}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center space-x-2">
                        <DollarSign className="h-4 w-4 text-muted-foreground" />
                        <div>
                          <p className="text-sm font-medium">{t('billingPage.currentPlan.nextPayment')}</p>
                          <p className="text-sm text-muted-foreground">
                            {formatDate(subscription.current_period_end)}
                          </p>
                        </div>
                      </div>
                    </div>

                    {subscription.cancel_at_period_end && (
                      <Alert>
                        <AlertCircle className="h-4 w-4" />
                        <AlertDescription>
                          {t('billingPage.currentPlan.cancellationWarning', {date: formatDate(subscription.current_period_end)})}
                        </AlertDescription>
                      </Alert>
                    )}
                  </>
                )}

                {subscription.plan_id === 'free' && (
                  <div className="space-y-3">
                    <p className="text-sm text-muted-foreground">
                      {t('billingPage.freePlan.description')}
                    </p>
                    <Button 
                      onClick={() => router.push('/pricing')}
                      className="w-full sm:w-auto"
                    >
                      <Zap className="h-4 w-4 mr-2" />
                      {t('billingPage.freePlan.upgradeButton')}
                    </Button>
                  </div>
                )}
              </CardContent>

              {subscription.plan_id !== 'free' && (
                <>
                  <Separator />
                  <CardFooter className="pt-6">
                    <Button 
                      onClick={openStripePortal}
                      disabled={isLoadingPortal}
                      className="w-full sm:w-auto"
                    >
                      {isLoadingPortal ? (
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      ) : (
                        <CreditCard className="h-4 w-4 mr-2" />
                      )}
                      {t('billingPage.manageBilling')}
                      <ExternalLink className="h-4 w-4 ml-2" />
                    </Button>
                  </CardFooter>
                </>
              )}
            </Card>

            {/* Billing Portal Info */}
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">{t('billingPage.billingPortal.title')}</CardTitle>
                <CardDescription>
                  {t('billingPage.billingPortal.description')}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  <p className="text-sm text-muted-foreground">
                    {t('billingPage.billingPortal.featureIntro')}
                  </p>
                  <ul className="text-sm text-muted-foreground space-y-1 ml-4">
                    <li>• {language === 'es' ? 'Actualizar métodos de pago' : 'Update payment methods'}</li>
                    <li>• {language === 'es' ? 'Descargar facturas' : 'Download invoices'}</li>
                    <li>• {language === 'es' ? 'Actualizar dirección de facturación' : 'Update billing address'}</li>
                    <li>• {language === 'es' ? 'Gestionar suscripción' : 'Manage subscription'}</li>
                    <li>• {language === 'es' ? 'Ver historial de pagos' : 'View payment history'}</li>
                  </ul>
                </div>
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </div>
  )
}