'use client'

import { useState, useEffect, useMemo } from 'react'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Progress } from '@/components/ui/progress'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { 
  Building, 
  User, 
  ArrowRight, 
  ArrowLeft,
  CheckCircle, 
  Loader2
} from 'lucide-react'
import { useUserContext } from '@/contexts/user-context'
import { useLanguage } from '@/contexts/language-context'
import { STRIPE_PLANS, type PlanId, formatPrice } from '@/lib/stripe-plans'
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'

// Dynamic schema based on language - ALL FIELDS OPTIONAL
const createUnifiedDataSchema = (t: (key: string) => string) => z.object({
  firstName: z.string().optional().default(''),
  lastName: z.string().optional().default(''),
  companyName: z.string().optional().default(''),
  cif: z.string().optional().default(''),
})

type UnifiedFormData = {
  firstName: string
  lastName: string
  companyName: string
  cif: string
}

interface NewUserOnboardingProps {
  onComplete?: (tenantId?: string) => void
}

export function NewUserOnboarding({ onComplete }: NewUserOnboardingProps) {
  const router = useRouter()
  const { t } = useLanguage()
  const { 
    clerkUser, 
    markOnboardingComplete,
    backendUser,
    refetchUser
  } = useUserContext()
  const [currentStep, setCurrentStep] = useState(0)
  const [isProcessing, setIsProcessing] = useState(false)
  const tenantPlansPath = useMemo(() => {
    if (backendUser?.tenant_id) {
      return `/${backendUser.tenant_id}/plans`
    }
    return '/plans'
  }, [backendUser?.tenant_id])

  const unifiedForm = useForm<UnifiedFormData>({
    resolver: zodResolver(createUnifiedDataSchema(t)),
    defaultValues: {
      firstName: clerkUser?.firstName || '',
      lastName: clerkUser?.lastName || '',
      companyName: '',
      cif: '',
    }
  })

  const translate = (key: string, fallback: string) => {
    const value = t(key)
    return value === key ? fallback : value
  }

  const normalizePlanId = (plan?: string | null): PlanId | null => {
    if (!plan) return null
    const normalized = plan.toLowerCase()
    if (normalized === 'trial' || normalized === 'free') return 'free'
    if (normalized === 'professional' || normalized === 'pro') return 'pro'
    if (normalized === 'basic') return 'basic'
    if (normalized === 'enterprise') return 'enterprise'
    return null
  }

  const derivedPlan = useMemo<PlanId | null>(() => {
    const fromSelected = normalizePlanId(backendUser?.selected_plan)
    if (fromSelected) return fromSelected
    const fromSubscription = normalizePlanId(backendUser?.subscription_plan)
    if (fromSubscription) return fromSubscription
    if (backendUser?.subscription_status?.toLowerCase() === 'trialing') {
      return 'free'
    }
    return null
  }, [backendUser?.selected_plan, backendUser?.subscription_plan, backendUser?.subscription_status])

  const steps = [
    {
      id: 'data',
      title: t('onboarding.companyInfo'),
      description: t('onboarding.companyInfoDesc'),
      icon: <Building className="h-5 w-5" />
    },
    {
      id: 'complete',
      title: t('onboarding.allSet'),
      description: t('onboarding.accountReady'),
      icon: <CheckCircle className="h-5 w-5" />
    }
  ]

  const currentStepId = steps[currentStep]?.id
  const completeStepIndex = steps.findIndex(step => step.id === 'complete')

  const planDetails = derivedPlan ? STRIPE_PLANS[derivedPlan] : null

  // Check if user already has backend data
  useEffect(() => {
    if (backendUser && backendUser.onboarding_completed) {
      // User already completed onboarding, redirect to dashboard
      onComplete?.(backendUser.tenant_id)
    }
  }, [backendUser, onComplete])

  const handleNext = async () => {
    if (currentStepId === 'data') {
      // Fields are optional, just complete
      await handleComplete()
      return
    }
  }

  const handlePrevious = () => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1)
    }
  }

  const handleComplete = async () => {
    try {
      setIsProcessing(true)
      
      // Get form data
      const formData = unifiedForm.getValues()
      
      const onboardingData = {
        first_name: formData.firstName,
        last_name: formData.lastName,
        company_name: formData.companyName,
        cif: formData.cif,
        selected_plan: derivedPlan ?? 'free',
      }
      
      console.log('Completing onboarding with data:', onboardingData)
      await markOnboardingComplete(onboardingData)
      
      // Refetch user data
      await refetchUser()
      
      if (completeStepIndex >= 0) {
        setCurrentStep(completeStepIndex)
      } else {
        setCurrentStep(steps.length - 1)
      }
      
      // Auto-redirect after 2 seconds
      setTimeout(() => {
        handleGoToDashboard()
      }, 2000)
      
    } catch (error) {
      console.log('Error completing onboarding:', error)
      // Still redirect even if there's an error
      setTimeout(() => {
        handleGoToDashboard()
      }, 2000)
    } finally {
      setIsProcessing(false)
    }
  }

  const handleGoToDashboard = () => {
    const tenantId = backendUser?.tenant_id
    
    if (onComplete) {
      onComplete(tenantId)
    } else {
      if (tenantId) {
        router.push(`/${tenantId}/dashboard`)
      } else {
        router.push('/dashboard')
      }
    }
  }

  const progressPercentage = ((currentStep + 1) / steps.length) * 100

  return (
    <div className="min-h-screen relative z-10">
      <div className="container mx-auto px-4 py-8">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-3xl md:text-4xl font-bold mb-4 bg-gradient-to-r from-purple-500 to-purple-700 bg-clip-text text-transparent">
            {t('onboarding.welcome')}
          </h1>
          <p className="text-lg text-gray-600 dark:text-gray-300 max-w-2xl mx-auto mb-6">
            {t('onboarding.setupAccount')}
          </p>
          
          {/* Progress */}
          <div className="max-w-md mx-auto">
            <div className="flex items-center justify-between text-sm font-medium text-gray-600 dark:text-gray-300 mb-3">
              <span>{t('onboarding.progress')}</span>
              <span>{currentStep + 1} {t('onboarding.of')} {steps.length}</span>
            </div>
            <Progress value={progressPercentage} className="h-2" />
          </div>
        </div>

        {/* Steps Overview */}
        <div className="flex justify-center mb-8 overflow-x-auto">
          <div className="flex items-center space-x-2 min-w-max">
            {steps.map((step, index) => (
              <div key={step.id} className="flex items-center">
                <div
                  className={`flex items-center justify-center w-10 h-10 rounded-full transition-all duration-300 ${
                    index <= currentStep
                      ? 'bg-purple-600 text-white'
                      : 'bg-gray-200 dark:bg-gray-700 text-gray-500 dark:text-gray-400'
                  }`}
                >
                  {index < currentStep ? (
                    <CheckCircle className="h-5 w-5" />
                  ) : (
                    step.icon
                  )}
                </div>
                {index < steps.length - 1 && (
                  <div className={`w-8 h-0.5 mx-2 ${
                    index < currentStep ? 'bg-purple-600' : 'bg-gray-200 dark:bg-gray-700'
                  }`} />
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Step Content */}
        <div className="max-w-2xl mx-auto">
          <Card className="shadow-xl">
            <CardHeader className="text-center">
              <div className="inline-flex items-center justify-center w-12 h-12 bg-gradient-to-r from-purple-500 to-purple-700 rounded-full mb-4">
                {steps[currentStep]?.icon && (
                  <div className="text-white">
                    {steps[currentStep].icon}
                  </div>
                )}
              </div>
              <CardTitle className="text-xl">{steps[currentStep]?.title}</CardTitle>
              <CardDescription>{steps[currentStep]?.description}</CardDescription>
            </CardHeader>
            
            <CardContent>
              {currentStepId === 'data' && (
                <div className="space-y-6">
                  {planDetails && (
                    <div className="rounded-2xl border border-purple-100 dark:border-purple-900/40 bg-purple-50/40 dark:bg-purple-950/20 p-6 space-y-4">
                      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
                        <div>
                          <p className="text-sm font-semibold text-purple-600 dark:text-purple-300 uppercase tracking-wide">
                            {translate('onboarding.currentPlan', 'Plan seleccionado')}
                          </p>
                          <h3 className="text-2xl font-bold text-gray-900 dark:text-white mt-1">{planDetails.name}</h3>
                          <p className="text-sm text-gray-600 dark:text-gray-300">
                            {planDetails.description}
                          </p>
                        </div>
                        <div className="text-right">
                          {planDetails.price === null ? (
                            <span className="text-lg font-semibold text-gray-900 dark:text-white">
                              {translate('pricing.contactSales', 'Contactar ventas')}
                            </span>
                          ) : (
                            <>
                              <p className="text-3xl font-bold text-gray-900 dark:text-white">
                                {formatPrice(planDetails.price, planDetails.currency)}
                              </p>
                              {planDetails.interval !== 'trial' && (
                                <p className="text-sm text-gray-500 dark:text-gray-400">
                                  /{planDetails.interval === 'month' ? translate('pricing.perMonth', 'mes') : planDetails.interval}
                                </p>
                              )}
                            </>
                          )}
                          {planDetails.popular && (
                            <Badge className="mt-3 bg-purple-600 text-white">
                              {translate('common.popular', 'Popular')}
                            </Badge>
                          )}
                        </div>
                      </div>

                      <Separator />

                      <div className="grid gap-4 md:grid-cols-2">
                        <div>
                          <p className="text-sm font-medium text-gray-700 dark:text-gray-200 mb-2">
                            {translate('onboarding.includes', 'Incluye')}
                          </p>
                          <ul className="space-y-2 text-sm text-gray-600 dark:text-gray-300">
                            {planDetails.features.slice(0, 4).map((feature) => (
                              <li key={feature} className="flex items-start gap-2">
                                <CheckCircle className="h-4 w-4 text-purple-500 dark:text-purple-400 mt-0.5" />
                                <span>{feature}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                        <div className="rounded-xl bg-white/70 dark:bg-black/40 border border-purple-100 dark:border-purple-900/40 p-4">
                          <p className="text-sm font-medium text-gray-700 dark:text-gray-200">
                            {translate('onboarding.needDifferentPlan', '¿Necesitas un plan diferente?')}
                          </p>
                          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                            {translate('onboarding.planChangeInfo', 'Puedes cambiar tu plan cuando lo necesites desde la página de planes.')}
                          </p>
                          <Button
                            variant="outline"
                            className="mt-4 w-full"
                            onClick={() => router.push(tenantPlansPath)}
                          >
                            {translate('onboarding.viewPlans', 'Ver planes')}
                            <ArrowRight className="h-4 w-4 ml-2" />
                          </Button>
                        </div>
                      </div>
                    </div>
                  )}

                  <Form {...unifiedForm}>
                    <form className="space-y-6">
                      {/* Personal data */}
                      <div className="space-y-4">
                        <div className="flex items-center space-x-2 mb-3">
                          <User className="h-4 w-4 text-gray-500" />
                          <h3 className="font-medium text-gray-900 dark:text-gray-100">{t('onboarding.personalData')}</h3>
                        </div>
                        
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          <FormField
                            control={unifiedForm.control}
                            name="firstName"
                            render={({ field }) => (
                              <FormItem>
                                <FormLabel>{t('onboarding.firstName')}</FormLabel>
                                <FormControl>
                                  <Input placeholder={t('onboarding.yourFirstName')} {...field} />
                                </FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />

                          <FormField
                            control={unifiedForm.control}
                            name="lastName"
                            render={({ field }) => (
                              <FormItem>
                                <FormLabel>{t('onboarding.lastName')}</FormLabel>
                                <FormControl>
                                  <Input placeholder={t('onboarding.yourLastName')} {...field} />
                                </FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                        </div>
                      </div>

                      {/* Company data */}
                      <div className="space-y-4 border-t pt-6">
                        <div className="flex items-center space-x-2 mb-3">
                          <Building className="h-4 w-4 text-gray-500" />
                          <h3 className="font-medium text-gray-900 dark:text-gray-100">{t('onboarding.billingData')}</h3>
                        </div>
                        
                        <FormField
                          control={unifiedForm.control}
                          name="companyName"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>{t('onboarding.companyName')}</FormLabel>
                              <FormControl>
                                <Input placeholder={t('onboarding.companyNamePlaceholder')} {...field} />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />

                        <FormField
                          control={unifiedForm.control}
                          name="cif"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>{t('onboarding.taxId')}</FormLabel>
                              <FormControl>
                                <Input placeholder={t('onboarding.taxIdPlaceholder')} {...field} />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      </div>
                    </form>
                  </Form>
                </div>
              )}

              {/* Step 2: Complete */}
              {currentStepId === 'complete' && (
                <div className="text-center py-8 space-y-6">
                  <div className="w-16 h-16 bg-green-100 dark:bg-green-900 rounded-full flex items-center justify-center mx-auto">
                    <CheckCircle className="h-8 w-8 text-green-600 dark:text-green-400" />
                  </div>
                  
                  <div>
                    <h3 className="text-2xl font-bold text-green-600 dark:text-green-400 mb-2">
                      {t('onboarding.allSet')}
                    </h3>
                    <p className="text-gray-600 dark:text-gray-300 mb-6">
                      {t('onboarding.accountReady')}
                    </p>
                  </div>

                  <Button 
                    onClick={handleGoToDashboard}
                    size="lg"
                    className="bg-gradient-to-r from-purple-500 to-purple-700 hover:from-purple-600 hover:to-purple-800 text-white px-8"
                  >
                    {t('onboarding.goToDashboard')}
                    <ArrowRight className="h-5 w-5 ml-2" />
                  </Button>
                </div>
              )}

              {/* Navigation Buttons */}
              {currentStep < steps.length - 1 && (
                <div className="flex flex-col gap-4 pt-6 border-t mt-8">
                  <div className="flex justify-between">
                    <Button
                      variant="outline"
                      onClick={handlePrevious}
                      disabled={currentStep === 0}
                      className={currentStep === 0 ? 'invisible' : ''}
                    >
                      <ArrowLeft className="h-4 w-4 mr-2" />
                      {t('common.previous')}
                    </Button>

                    <Button
                      onClick={handleNext}
                      disabled={isProcessing}
                      className={currentStep === 0 ? 'ml-auto' : ''}
                    >
                      {isProcessing ? (
                        <>
                          <Loader2 className="h-4 w-4 animate-spin mr-2" />
                          {t('onboarding.processing')}
                        </>
                      ) : currentStep === steps.length - 2 ? (
                        <>
                          {t('onboarding.complete')}
                          <CheckCircle className="h-4 w-4 ml-2" />
                        </>
                      ) : (
                        <>
                          {t('common.next')}
                          <ArrowRight className="h-4 w-4 ml-2" />
                        </>
                      )}
                    </Button>
                  </div>

                  {/* Skip option - only show on data step */}
                  {currentStepId === 'data' && (
                    <div className="text-center">
                      <Button
                        variant="ghost"
                        onClick={handleComplete}
                        disabled={isProcessing}
                        className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
                      >
                        {translate('onboarding.skipForNow', 'Completar más tarde')}
                        <ArrowRight className="h-4 w-4 ml-1" />
                      </Button>
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
