'use client'

import { useState, useEffect } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Progress } from '@/components/ui/progress'
import { Badge } from '@/components/ui/badge'
import { 
  Building, 
  User, 
  ArrowRight, 
  CheckCircle, 
  Loader2,
  Sparkles,
  Crown
} from 'lucide-react'
import { useUserContext } from '@/contexts/user-context'
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'

const companyFormSchema = z.object({
  companyName: z.string().min(2, "El nombre debe tener al menos 2 caracteres"),
  industry: z.string().optional(),
  teamSize: z.string().optional(),
  useCase: z.string().optional(),
})

type CompanyFormData = z.infer<typeof companyFormSchema>

interface ExpressOnboardingProps {
  checkoutData?: {
    plan_id: string
    customer_email: string
    amount_total: number
    currency: string
  }
  onComplete?: (tenantId?: string) => void
}

export function ExpressOnboarding({ checkoutData, onComplete }: ExpressOnboardingProps) {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { 
    clerkUser, 
    syncUserWithBackend, 
    markOnboardingComplete,
    backendUser,
    refetchUser
  } = useUserContext()

  const [currentStep, setCurrentStep] = useState(0)
  const [isProcessing, setIsProcessing] = useState(false)
  const [syncCompleted, setSyncCompleted] = useState(false)
  const [syncError, setSyncError] = useState<string | null>(null)
  const [syncStarted, setSyncStarted] = useState(false)
  
  // Debug logging for step changes
  useEffect(() => {
    console.log('📊 ExpressOnboarding State:', {
      currentStep,
      isProcessing,
      syncCompleted,
      syncStarted,
      backendUser: backendUser?.tenant_id,
      clerkUser: !!clerkUser,
      clerkUserId: clerkUser?.id,
      clerkUserLoaded: !!clerkUser,
      searchParams: searchParams.toString()
    })
  }, [currentStep, isProcessing, syncCompleted, syncStarted, backendUser, clerkUser, searchParams])

  const form = useForm<CompanyFormData>({
    resolver: zodResolver(companyFormSchema),
    defaultValues: {
      companyName: '',
      industry: '',
      teamSize: '',
      useCase: '',
    }
  })

  // Load saved onboarding data from localStorage when step 1 is reached
  useEffect(() => {
    if (currentStep === 1) {
      try {
        const savedData = localStorage.getItem('pendingOnboardingData')
        if (savedData) {
          const onboardingData = JSON.parse(savedData)
          console.log('📋 Loading saved onboarding data:', onboardingData)
          
          // Update form with saved data
          form.setValue('companyName', onboardingData.company_name || '')
          
          // Clear the saved data since we're using it now
          localStorage.removeItem('pendingOnboardingData')
        }
      } catch (error) {
        console.error('Error loading saved onboarding data:', error)
      }
    }
  }, [currentStep, form])

  const steps = [
    {
      id: 'sync',
      title: 'Configuración de Cuenta',
      description: 'Sincronizando tu información',
      icon: <User className="h-5 w-5" />
    },
    {
      id: 'company',
      title: 'Datos de Empresa',
      description: 'Información básica de tu organización',
      icon: <Building className="h-5 w-5" />
    },
    {
      id: 'complete',
      title: 'Todo Listo',
      description: 'Acceso a tu dashboard',
      icon: <CheckCircle className="h-5 w-5" />
    }
  ]

  // Auto-sync user when component mounts
  useEffect(() => {
    const performSync = async () => {
      console.log('🔄 performSync called with:', {
        clerkUser: !!clerkUser,
        syncCompleted,
        currentStep,
        isProcessing
      })
      
      // Allow sync if we have clerkUser OR if we have checkoutData (user paid via Stripe)
      const canSync = (clerkUser || checkoutData) && !syncCompleted && currentStep === 0 && !syncStarted
      
      console.log('🔍 Sync conditions:', {
        clerkUser: !!clerkUser,
        checkoutData: !!checkoutData,
        syncCompleted,
        currentStep,
        syncStarted,
        canSync
      })
      
      if (canSync) {
        console.log('🚀 Starting Express Onboarding sync...')
        setSyncStarted(true)
        try {
          setIsProcessing(true)
          
          // Get Stripe data from URL params or props
          const sessionId = searchParams.get('session_id')
          console.log('📋 Session ID:', sessionId)
          console.log('📋 Checkout data:', checkoutData)
          
          const stripeData = sessionId ? {
            sessionId,
            customerId: checkoutData ? 'pending' : undefined, // Will be fetched from session
            planId: checkoutData?.plan_id
          } : undefined

          console.log('📤 Syncing with backend, stripe data:', stripeData)
          
          if (clerkUser) {
            // Normal sync if we have clerkUser
            const result = await syncUserWithBackend()
            console.log('📥 Sync result:', result)
          } else {
            // If no clerkUser but we have checkoutData, skip sync and continue
            console.log('⚠️ No clerkUser available, but we have checkoutData - skipping sync')
            await new Promise(resolve => setTimeout(resolve, 1000)) // Small delay for UX
          }
          
          console.log('✅ Sync completed, moving to step 1')
          setSyncCompleted(true)
          setCurrentStep(1)
          setIsProcessing(false)
        } catch (error) {
          console.error('💥 Sync error:', error)
          const errorMessage = error instanceof Error ? error.message : 'Error de sincronización'
          setSyncError(errorMessage)
          setIsProcessing(false)
          // Don't advance on error - let user see what happened
        }
      }
    }

    performSync()
  }, [clerkUser, syncCompleted, syncStarted, searchParams, checkoutData, syncUserWithBackend, currentStep, isProcessing])


  const handleCompanySubmit = async (data: CompanyFormData) => {
    try {
      setIsProcessing(true)
      
      if (clerkUser) {
        const onboardingData = {
          company_name: data.companyName,
          industry: data.industry,
          team_size: data.teamSize,
          use_case: data.useCase,
        }
        console.log('📤 Completing onboarding with data:', onboardingData)
        const success = await markOnboardingComplete(onboardingData)
        console.log('📥 Onboarding completion result:', success)
        
        if (!success) {
          throw new Error('Failed to complete onboarding')
        }
        
        // Refetch user data to ensure onboarding status is updated
        console.log('🔄 Refreshing user data after onboarding completion')
        await refetchUser()
      } else {
        // If no clerkUser, just continue to completion
        console.log('⚠️ No clerkUser - skipping backend onboarding completion')
      }
      
      setCurrentStep(2)
      
      // Auto-redirect after 2 seconds
      setTimeout(() => {
        handleGoToDashboard()
      }, 2000)
      
    } catch (error) {
      console.error('Error completing onboarding:', error)
      // Even if onboarding fails, redirect to dashboard
      setTimeout(() => {
        handleGoToDashboard()
      }, 2000)
    } finally {
      setIsProcessing(false)
    }
  }

  const handleGoToDashboard = () => {
    const tenantId = backendUser?.tenant_id
    console.log('🚀 Attempting to go to dashboard')
    console.log('👤 Backend user:', backendUser)
    console.log('🏢 Tenant ID:', tenantId)
    console.log('📞 onComplete callback:', !!onComplete)
    
    if (onComplete) {
      console.log('✅ Using onComplete callback with tenantId:', tenantId)
      onComplete(tenantId)
    } else {
      if (tenantId) {
        console.log('✅ Redirecting to tenant dashboard:', `/${tenantId}/dashboard`)
        router.push(`/${tenantId}/dashboard`)
      } else {
        console.log('⚠️ No tenant ID, redirecting to general dashboard')
        router.push('/dashboard')
      }
    }
  }

  const progressPercentage = ((currentStep + 1) / steps.length) * 100

  const getPlanIcon = (planId: string) => {
    return planId === 'enterprise' ? <Crown className="h-4 w-4" /> : <Sparkles className="h-4 w-4" />
  }

  const getPlanColor = (planId: string) => {
    return planId === 'enterprise' 
      ? 'bg-purple-100 text-purple-800 border-purple-200' 
      : 'bg-blue-100 text-blue-800 border-blue-200'
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800">
      <div className="container mx-auto px-4 py-8">
        {/* Header */}
        <div className="text-center mb-8">
          {checkoutData && (
            <div className="mb-4">
              <Badge className={`${getPlanColor(checkoutData.plan_id)} mb-2`}>
                {getPlanIcon(checkoutData.plan_id)}
                <span className="ml-2">
                  {checkoutData.plan_id === 'pro' ? 'Pro Plan' : 'Enterprise Plan'}
                </span>
              </Badge>
            </div>
          )}
          
          <h1 className="text-3xl md:text-4xl font-bold mb-4 bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
            ¡Bienvenido a Nexus!
          </h1>
          <p className="text-lg text-gray-600 dark:text-gray-300 max-w-2xl mx-auto mb-6">
            Tu cuenta premium está lista. Solo necesitamos configurar algunos detalles finales.
          </p>
          
          {/* Progress */}
          <div className="max-w-md mx-auto">
            <div className="flex items-center justify-between text-sm font-medium text-gray-600 dark:text-gray-300 mb-3">
              <span>Progreso de configuración</span>
              <span>{currentStep + 1} de {steps.length}</span>
            </div>
            <Progress value={progressPercentage} className="h-2" />
          </div>
        </div>

        {/* Steps Overview */}
        <div className="flex justify-center mb-8">
          <div className="flex items-center space-x-4">
            {steps.map((step, index) => (
              <div key={step.id} className="flex items-center">
                <div
                  className={`flex items-center justify-center w-10 h-10 rounded-full transition-all duration-300 ${
                    index <= currentStep
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-200 dark:bg-gray-700 text-gray-400'
                  }`}
                >
                  {index < currentStep ? (
                    <CheckCircle className="h-5 w-5" />
                  ) : (
                    step.icon
                  )}
                </div>
                {index < steps.length - 1 && (
                  <div className={`w-16 h-0.5 mx-2 ${
                    index < currentStep ? 'bg-blue-600' : 'bg-gray-200 dark:bg-gray-700'
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
              <div className="inline-flex items-center justify-center w-12 h-12 bg-gradient-to-r from-blue-500 to-purple-500 rounded-full mb-4">
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
              {/* Step 0: User Sync */}
              {currentStep === 0 && (
                <div className="text-center py-8">
                  {!clerkUser && checkoutData ? (
                    <>
                      <div className="w-16 h-16 bg-blue-100 dark:bg-blue-900 rounded-full flex items-center justify-center mx-auto mb-4">
                        <User className="h-8 w-8 text-blue-600 dark:text-blue-400" />
                      </div>
                      <p className="text-lg font-medium mb-2 text-blue-600 dark:text-blue-400">Completa tu registro</p>
                      <p className="text-gray-600 dark:text-gray-300 mb-6">
                        ¡Tu pago fue exitoso! Ahora necesitas completar tu registro para acceder a tu cuenta premium.
                      </p>
                      <div className="mt-6 space-y-3">
                        <Button 
                          onClick={() => {
                            console.log('🔑 Redirecting to sign up')
                            // Preserve the session_id when redirecting to sign up
                            const sessionId = searchParams.get('session_id')
                            const redirectUrl = sessionId 
                              ? `/auth/sign-up?redirect_url=${encodeURIComponent(window.location.href)}`
                              : '/auth/sign-up'
                            router.push(redirectUrl)
                          }}
                          className="w-full"
                        >
                          Completar registro
                        </Button>
                        <Button 
                          variant="outline" 
                          onClick={() => {
                            console.log('🔑 Redirecting to sign in')
                            const sessionId = searchParams.get('session_id')
                            const redirectUrl = sessionId 
                              ? `/auth/sign-in?redirect_url=${encodeURIComponent(window.location.href)}`
                              : '/auth/sign-in'
                            router.push(redirectUrl)
                          }}
                          className="w-full"
                        >
                          Ya tengo cuenta - Iniciar sesión
                        </Button>
                      </div>
                    </>
                  ) : !clerkUser && !checkoutData ? (
                    <>
                      <div className="w-16 h-16 bg-yellow-100 dark:bg-yellow-900 rounded-full flex items-center justify-center mx-auto mb-4">
                        <span className="text-yellow-600 dark:text-yellow-400 text-2xl">⚠️</span>
                      </div>
                      <p className="text-lg font-medium mb-2 text-yellow-600 dark:text-yellow-400">Sesión requerida</p>
                      <p className="text-gray-600 dark:text-gray-300 mb-6">
                        Necesitas iniciar sesión para continuar con el onboarding.
                      </p>
                      <div className="mt-6">
                        <Button 
                          onClick={() => router.push('/auth/sign-in')}
                          className="w-full"
                        >
                          Iniciar sesión
                        </Button>
                      </div>
                    </>
                  ) : syncError ? (
                    <>
                      <div className="w-16 h-16 bg-red-100 dark:bg-red-900 rounded-full flex items-center justify-center mx-auto mb-4">
                        <span className="text-red-600 dark:text-red-400 text-2xl">⚠️</span>
                      </div>
                      <p className="text-lg font-medium mb-2 text-red-600 dark:text-red-400">Error de configuración</p>
                      <p className="text-gray-600 dark:text-gray-300 mb-6">
                        {syncError}
                      </p>
                      <div className="mt-6 space-y-3">
                        <Button 
                          onClick={() => {
                            setSyncError(null)
                            setSyncCompleted(false)
                            setSyncStarted(false)
                            setIsProcessing(false)
                            // Trigger retry
                          }}
                          className="w-full"
                        >
                          Reintentar
                        </Button>
                        <Button 
                          variant="outline" 
                          onClick={() => {
                            console.log('⚡ Manual continue after error')
                            setSyncCompleted(true)
                            setCurrentStep(1)
                            setSyncError(null)
                          }}
                          className="w-full"
                        >
                          Continuar de todas formas
                        </Button>
                      </div>
                    </>
                  ) : (
                    <>
                      <Loader2 className="h-8 w-8 animate-spin mx-auto text-blue-600 mb-4" />
                      <p className="text-lg font-medium mb-2">Configurando tu cuenta premium...</p>
                      <p className="text-gray-600 dark:text-gray-300">
                        Estamos preparando todo para que puedas aprovechar al máximo Nexus
                      </p>
                    </>
                  )}
                </div>
              )}

              {/* Step 1: Company Data */}
              {currentStep === 1 && (
                <div className="space-y-6">
                  {/* Debug info for step 1 */}
                  <div className="text-xs text-gray-500 p-2 bg-gray-100 rounded mb-4">
                    Debug: Step 1 - isProcessing: {isProcessing.toString()}, syncCompleted: {syncCompleted.toString()}
                  </div>
                  <Form {...form}>
                    <form onSubmit={form.handleSubmit(handleCompanySubmit)} className="space-y-4">
                      <FormField
                        control={form.control}
                        name="companyName"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>Nombre de la Empresa *</FormLabel>
                            <FormControl>
                              <Input placeholder="Ej: Mi Empresa SL" {...field} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                      
                      <FormField
                        control={form.control}
                        name="industry"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>Industria</FormLabel>
                            <FormControl>
                              <Input placeholder="Ej: Tecnología, Consultoría, etc." {...field} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />

                      <FormField
                        control={form.control}
                        name="teamSize"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>Tamaño del Equipo</FormLabel>
                            <FormControl>
                              <Input placeholder="Ej: 1-10, 11-50, 50+, etc." {...field} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />

                      <FormField
                        control={form.control}
                        name="useCase"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>¿Cómo planeas usar Nexus?</FormLabel>
                            <FormControl>
                              <Textarea 
                                placeholder="Cuéntanos brevemente cómo planeas usar la plataforma..."
                                rows={3}
                                {...field} 
                              />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />

                      <Button 
                        type="submit" 
                        className="w-full" 
                        size="lg"
                        disabled={isProcessing}
                      >
                        {isProcessing ? (
                          <>
                            <Loader2 className="h-4 w-4 animate-spin mr-2" />
                            Configurando...
                          </>
                        ) : (
                          <>
                            Completar Configuración
                            <ArrowRight className="h-4 w-4 ml-2" />
                          </>
                        )}
                      </Button>
                    </form>
                  </Form>
                </div>
              )}

              {/* Step 2: Complete */}
              {currentStep === 2 && (
                <div className="text-center py-8 space-y-6">
                  <div className="w-16 h-16 bg-green-100 dark:bg-green-900 rounded-full flex items-center justify-center mx-auto">
                    <CheckCircle className="h-8 w-8 text-green-600 dark:text-green-400" />
                  </div>
                  
                  <div>
                    <h3 className="text-2xl font-bold text-green-600 dark:text-green-400 mb-2">
                      ¡Todo listo!
                    </h3>
                    <p className="text-gray-600 dark:text-gray-300 mb-6">
                      Tu cuenta premium está configurada y lista para usar. 
                      ¡Explora todas las funcionalidades que tienes disponibles!
                    </p>
                  </div>

                  <Button 
                    onClick={handleGoToDashboard}
                    size="lg"
                    className="bg-gradient-to-r from-green-600 to-blue-600 hover:from-green-700 hover:to-blue-700 text-white px-8"
                  >
                    Ir al Dashboard
                    <ArrowRight className="h-5 w-5 ml-2" />
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}