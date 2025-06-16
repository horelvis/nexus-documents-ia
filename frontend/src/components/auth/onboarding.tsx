'use client'

import { useState, useEffect } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
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
import { useApiClient } from '@/lib/api-client'
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
// Plan imports removed - no longer needed for simplified onboarding

// Schema simplificado - solo datos esenciales
const unifiedDataSchema = z.object({
  firstName: z.string().min(2, "El nombre debe tener al menos 2 caracteres"),
  lastName: z.string().min(2, "El apellido debe tener al menos 2 caracteres"),
  companyName: z.string().min(2, "El nombre de la empresa es requerido"),
  cif: z.string().min(8, "El CIF debe tener al menos 8 caracteres"),
})

type UnifiedFormData = z.infer<typeof unifiedDataSchema>

interface NewUserOnboardingProps {
  onComplete?: (tenantId?: string) => void
}

export function NewUserOnboarding({ onComplete }: NewUserOnboardingProps) {
  const router = useRouter()
  const searchParams = useSearchParams()
  const apiClient = useApiClient()
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
  // Plan selection removed - users start with free plan

  const unifiedForm = useForm<UnifiedFormData>({
    resolver: zodResolver(unifiedDataSchema),
    defaultValues: {
      firstName: clerkUser?.firstName || '',
      lastName: clerkUser?.lastName || '',
      companyName: '',
      cif: '',
    }
  })

  // Plans removed from onboarding flow

  const steps = [
    {
      id: 'sync',
      title: 'Configuración de Cuenta',
      description: 'Sincronizando tu información',
      icon: <User className="h-5 w-5" />
    },
    {
      id: 'data',
      title: 'Información Personal',
      description: 'Completa tu perfil',
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
      if (clerkUser && !syncCompleted && currentStep === 0) {
        try {
          setIsProcessing(true)
          await syncUserWithBackend()
          setSyncCompleted(true)
          setCurrentStep(1)
        } catch (error) {
          console.log('Error syncing user:', error)
        } finally {
          setIsProcessing(false)
        }
      }
    }

    performSync()
  }, [clerkUser, syncCompleted, currentStep, syncUserWithBackend])

  const handleNext = async () => {
    if (currentStep === 1) {
      // Validar el formulario unificado
      const isValid = await unifiedForm.trigger()
      if (!isValid) return
      
      // Después de validar, completar el onboarding
      await handleComplete()
      return
    }

    if (currentStep < steps.length - 1) {
      setCurrentStep(currentStep + 1)
    }
  }

  const handlePrevious = () => {
    if (currentStep > 1) {
      setCurrentStep(currentStep - 1)
    }
  }

  const handlePlanSelection = (plan: Plan, interval: 'month' | 'year' = 'month') => {
    setSelectedPlan(plan)
    setSelectedInterval(interval)
    
    if (plan.id === 'enterprise') {
      // For enterprise, redirect to contact
      window.location.href = 'mailto:sales@nexus.com?subject=Enterprise%20Plan%20Inquiry'
      return
    }
  }

  const handlePayment = async () => {
    if (!selectedPlan || selectedPlan.id === 'free') {
      console.log('❌ No plan selected or free plan selected')
      return
    }

    console.log('🚀 Iniciando proceso de pago para:', selectedPlan.id, selectedInterval)

    try {
      setIsProcessing(true)
      
      // STEP 1: Save onboarding data to backend FIRST (including plan selection)
      console.log('💾 Step 1: Saving onboarding data to backend...')
      const formData = unifiedForm.getValues()
      
      const onboardingData = {
        first_name: formData.firstName,
        last_name: formData.lastName,
        company_name: formData.companyName,
        cif: formData.cif,
        selected_plan: selectedPlan.id,
        payment_interval: selectedInterval,
        onboarding_step: 'payment_pending' // Track where user is in the flow
      }
      
      console.log('📝 Saving onboarding data:', onboardingData)
      
      // Save to backend first - this ensures data persistence
      const onboardingResponse = await markOnboardingComplete(onboardingData)
      if (!onboardingResponse) {
        throw new Error('Failed to save onboarding data to backend')
      }
      
      console.log('✅ Onboarding data saved to backend successfully')
      
      // STEP 2: Create Stripe checkout session
      console.log('💳 Step 2: Creating Stripe checkout session...')
      const requestBody = {
        planId: selectedPlan.id,
        interval: selectedInterval,
        email: clerkUser?.emailAddresses[0]?.emailAddress,
      }
      
      console.log('📤 Stripe request body:', requestBody)
      
      const response = await apiClient.post('/stripe/create-checkout-session', requestBody)

      console.log('📥 Stripe response status:', response.status)

      if (response.error) {
        console.log('❌ Stripe error response:', response.error)
        throw new Error(response.error)
      }

      console.log('✅ Stripe response data:', response.data)
      
      if (response.data?.url) {
        // STEP 3: Store backup data in sessionStorage for redundancy
        const backupData = {
          formData: formData,
          plan: selectedPlan.id,
          interval: selectedInterval,
          timestamp: new Date().toISOString()
        }
        
        sessionStorage.setItem('onboarding_backup', JSON.stringify(backupData))
        
        console.log('🔗 Redirecting to Stripe payment:', response.data.url)
        window.location.href = response.data.url
      } else {
        throw new Error('No checkout URL received from server')
      }
    } catch (error) {
      console.log('💥 Error in payment process:', error)
      alert(`Error al procesar el pago: ${error.message}`)
    } finally {
      setIsProcessing(false)
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
        selected_plan: 'free', // Always free during initial onboarding
      }
      
      console.log('Completing onboarding with data:', onboardingData)
      await markOnboardingComplete(onboardingData)
      
      // Refetch user data
      await refetchUser()
      
      setCurrentStep(steps.length - 1)
      
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
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800">
      <div className="container mx-auto px-4 py-8">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-3xl md:text-4xl font-bold mb-4 bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
            ¡Bienvenido a Nexus!
          </h1>
          <p className="text-lg text-gray-600 dark:text-gray-300 max-w-2xl mx-auto mb-6">
            Configura tu cuenta en unos simples pasos
          </p>
          
          {/* Progress */}
          <div className="max-w-md mx-auto">
            <div className="flex items-center justify-between text-sm font-medium text-gray-600 dark:text-gray-300 mb-3">
              <span>Progreso</span>
              <span>{currentStep + 1} de {steps.length}</span>
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
                  <div className={`w-8 h-0.5 mx-2 ${
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
                  <Loader2 className="h-8 w-8 animate-spin mx-auto text-blue-600 mb-4" />
                  <p className="text-lg font-medium mb-2">Configurando tu cuenta...</p>
                  <p className="text-gray-600 dark:text-gray-300">
                    Sincronizando tu información de usuario
                  </p>
                </div>
              )}

              {/* Step 1: Unified Data Form */}
              {currentStep === 1 && (
                <div className="space-y-6">
                  <Form {...unifiedForm}>
                    <form className="space-y-6">
                      {/* Datos personales */}
                      <div className="space-y-4">
                        <div className="flex items-center space-x-2 mb-3">
                          <User className="h-4 w-4 text-gray-500" />
                          <h3 className="font-medium text-gray-900 dark:text-gray-100">Datos Personales</h3>
                        </div>
                        
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          <FormField
                            control={unifiedForm.control}
                            name="firstName"
                            render={({ field }) => (
                              <FormItem>
                                <FormLabel>Nombre *</FormLabel>
                                <FormControl>
                                  <Input placeholder="Tu nombre" {...field} />
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
                                <FormLabel>Apellidos *</FormLabel>
                                <FormControl>
                                  <Input placeholder="Tus apellidos" {...field} />
                                </FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                        </div>
                      </div>

                      {/* Datos de empresa */}
                      <div className="space-y-4 border-t pt-6">
                        <div className="flex items-center space-x-2 mb-3">
                          <Building className="h-4 w-4 text-gray-500" />
                          <h3 className="font-medium text-gray-900 dark:text-gray-100">Datos de Facturación</h3>
                        </div>
                        
                        <FormField
                          control={unifiedForm.control}
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
                          control={unifiedForm.control}
                          name="cif"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>CIF/NIF *</FormLabel>
                              <FormControl>
                                <Input placeholder="Ej: B12345678" {...field} />
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
                      Tu cuenta está configurada. ¡Bienvenido a Nexus!
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

              {/* Navigation Buttons */}
              {currentStep > 0 && currentStep < steps.length - 1 && (
                <div className="flex justify-between pt-6 border-t mt-8">
                  <Button
                    variant="outline"
                    onClick={handlePrevious}
                    disabled={currentStep <= 1}
                  >
                    <ArrowLeft className="h-4 w-4 mr-2" />
                    Anterior
                  </Button>

                  <Button
                    onClick={handleNext}
                    disabled={isProcessing}
                  >
                    {isProcessing ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin mr-2" />
                        Procesando...
                      </>
                    ) : currentStep === 1 ? (
                      <>
                        Completar
                        <CheckCircle className="h-4 w-4 ml-2" />
                      </>
                    ) : (
                      <>
                        Siguiente
                        <ArrowRight className="h-4 w-4 ml-2" />
                      </>
                    )}
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