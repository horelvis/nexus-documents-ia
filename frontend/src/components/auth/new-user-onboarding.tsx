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
  Loader2,
  Sparkles,
  Crown,
  Star,
  Zap,
  Check
} from 'lucide-react'
import { useUserContext } from '@/contexts/user-context'
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { getAllPlans, formatPrice, calculateYearlyDiscount, type Plan } from '@/lib/stripe-plans'

const personalDataSchema = z.object({
  firstName: z.string().min(2, "El nombre debe tener al menos 2 caracteres"),
  lastName: z.string().min(2, "El apellido debe tener al menos 2 caracteres"),
  phone: z.string().optional(),
  role: z.string().min(2, "El rol es requerido"),
})

const companyDataSchema = z.object({
  companyName: z.string().min(2, "El nombre debe tener al menos 2 caracteres"),
  industry: z.string().optional(),
  teamSize: z.string().optional(),
  useCase: z.string().optional(),
})

type PersonalFormData = z.infer<typeof personalDataSchema>
type CompanyFormData = z.infer<typeof companyDataSchema>

interface NewUserOnboardingProps {
  onComplete?: (tenantId?: string) => void
}

export function NewUserOnboarding({ onComplete }: NewUserOnboardingProps) {
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
  const [selectedPlan, setSelectedPlan] = useState<Plan | null>(null)
  const [selectedInterval, setSelectedInterval] = useState<'month' | 'year'>('month')

  const personalForm = useForm<PersonalFormData>({
    resolver: zodResolver(personalDataSchema),
    defaultValues: {
      firstName: clerkUser?.firstName || '',
      lastName: clerkUser?.lastName || '',
      phone: '',
      role: '',
    }
  })

  const companyForm = useForm<CompanyFormData>({
    resolver: zodResolver(companyDataSchema),
    defaultValues: {
      companyName: '',
      industry: '',
      teamSize: '',
      useCase: '',
    }
  })

  const plans = getAllPlans()

  const steps = [
    {
      id: 'sync',
      title: 'Configuración de Cuenta',
      description: 'Sincronizando tu información',
      icon: <User className="h-5 w-5" />
    },
    {
      id: 'personal',
      title: 'Datos Personales',
      description: 'Información personal y de contacto',
      icon: <User className="h-5 w-5" />
    },
    {
      id: 'company',
      title: 'Datos de Empresa',
      description: 'Información de tu organización',
      icon: <Building className="h-5 w-5" />
    },
    {
      id: 'plan',
      title: 'Selecciona tu Plan',
      description: 'Elige el plan que mejor se adapte a tus necesidades',
      icon: <Sparkles className="h-5 w-5" />
    },
    {
      id: 'payment',
      title: 'Proceso de Pago',
      description: 'Configuración de facturación',
      icon: <CheckCircle className="h-5 w-5" />
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
          console.error('Error syncing user:', error)
        } finally {
          setIsProcessing(false)
        }
      }
    }

    performSync()
  }, [clerkUser, syncCompleted, currentStep, syncUserWithBackend])

  const handleNext = async () => {
    if (currentStep === 1) {
      const isValid = await personalForm.trigger()
      if (!isValid) return
    }
    
    if (currentStep === 2) {
      const isValid = await companyForm.trigger()
      if (!isValid) return
    }

    if (currentStep === 3) {
      if (!selectedPlan) return
      
      // If free plan selected, skip payment step
      if (selectedPlan.id === 'free') {
        setCurrentStep(5) // Go directly to complete
        await handleComplete()
        return
      }
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
    if (!selectedPlan || selectedPlan.id === 'free') return

    try {
      setIsProcessing(true)
      
      const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
      const response = await fetch(`${API_BASE}/api/v1/stripe/create-checkout-session`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          planId: selectedPlan.id,
          interval: selectedInterval,
          email: clerkUser?.emailAddresses[0]?.emailAddress,
        }),
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const { url } = await response.json()
      
      if (url) {
        // Save onboarding data before redirecting to payment
        const personalData = personalForm.getValues()
        const companyData = companyForm.getValues()
        
        // Store in sessionStorage to preserve across redirect
        sessionStorage.setItem('onboarding_data', JSON.stringify({
          personal: personalData,
          company: companyData,
          plan: selectedPlan.id,
          interval: selectedInterval
        }))
        
        window.location.href = url
      }
    } catch (error) {
      console.error('Error creating checkout session:', error)
    } finally {
      setIsProcessing(false)
    }
  }

  const handleComplete = async () => {
    try {
      setIsProcessing(true)
      
      // Combine all form data
      const personalData = personalForm.getValues()
      const companyData = companyForm.getValues()
      
      const onboardingData = {
        first_name: personalData.firstName,
        last_name: personalData.lastName,
        phone: personalData.phone,
        role: personalData.role,
        company_name: companyData.companyName,
        industry: companyData.industry,
        team_size: companyData.teamSize,
        use_case: companyData.useCase,
        selected_plan: selectedPlan?.id || 'free',
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
      console.error('Error completing onboarding:', error)
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

  const getPlanIcon = (planId: string) => {
    switch (planId) {
      case 'enterprise':
        return <Crown className="h-4 w-4" />
      case 'pro':
        return <Zap className="h-4 w-4" />
      default:
        return <Star className="h-4 w-4" />
    }
  }

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

              {/* Step 1: Personal Data */}
              {currentStep === 1 && (
                <div className="space-y-6">
                  <Form {...personalForm}>
                    <form className="space-y-4">
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <FormField
                          control={personalForm.control}
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
                          control={personalForm.control}
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
                      
                      <FormField
                        control={personalForm.control}
                        name="phone"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>Teléfono</FormLabel>
                            <FormControl>
                              <Input placeholder="Ej: +34 123 456 789" {...field} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />

                      <FormField
                        control={personalForm.control}
                        name="role"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>Tu rol *</FormLabel>
                            <FormControl>
                              <Input placeholder="Ej: CEO, Manager, Developer, etc." {...field} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    </form>
                  </Form>
                </div>
              )}

              {/* Step 2: Company Data */}
              {currentStep === 2 && (
                <div className="space-y-6">
                  <Form {...companyForm}>
                    <form className="space-y-4">
                      <FormField
                        control={companyForm.control}
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
                        control={companyForm.control}
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
                        control={companyForm.control}
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
                        control={companyForm.control}
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
                    </form>
                  </Form>
                </div>
              )}

              {/* Step 3: Plan Selection */}
              {currentStep === 3 && (
                <div className="space-y-6">
                  <div className="text-center mb-6">
                    <h3 className="text-xl font-semibold mb-2">Elige el plan perfecto para ti</h3>
                    <p className="text-gray-600 dark:text-gray-300">
                      Puedes cambiar o cancelar en cualquier momento
                    </p>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    {plans.map((plan) => (
                      <div
                        key={plan.id}
                        className={`relative cursor-pointer transition-all duration-300 ${
                          selectedPlan?.id === plan.id
                            ? 'ring-2 ring-blue-500 scale-105'
                            : 'hover:scale-105'
                        }`}
                        onClick={() => handlePlanSelection(plan)}
                      >
                        <Card className={`h-full ${plan.popular ? 'border-blue-500' : ''}`}>
                          {plan.popular && (
                            <div className="absolute -top-3 left-1/2 transform -translate-x-1/2">
                              <Badge className="bg-blue-600 text-white">
                                <Star className="w-3 h-3 mr-1" />
                                Más Popular
                              </Badge>
                            </div>
                          )}

                          <CardHeader className="text-center">
                            <div className="flex items-center justify-center mb-2">
                              {getPlanIcon(plan.id)}
                              <CardTitle className="text-lg font-bold ml-2">{plan.name}</CardTitle>
                            </div>
                            <div className="text-3xl font-bold">
                              {plan.price === 0 ? 'Gratis' : formatPrice(plan.price)}
                              {plan.price > 0 && (
                                <span className="text-base text-gray-500">/{plan.interval}</span>
                              )}
                            </div>
                            <CardDescription>{plan.description}</CardDescription>
                          </CardHeader>

                          <CardContent>
                            <ul className="space-y-2">
                              {plan.features.slice(0, 4).map((feature, index) => (
                                <li key={index} className="flex items-start">
                                  <Check className="w-4 h-4 text-green-500 mr-2 mt-0.5 flex-shrink-0" />
                                  <span className="text-sm">{feature}</span>
                                </li>
                              ))}
                              {plan.features.length > 4 && (
                                <li className="text-sm text-gray-500">
                                  Y {plan.features.length - 4} funciones más...
                                </li>
                              )}
                            </ul>

                            {selectedPlan?.id === plan.id && (
                              <div className="mt-4 p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
                                <div className="flex items-center text-blue-600 dark:text-blue-400">
                                  <CheckCircle className="w-4 h-4 mr-2" />
                                  <span className="text-sm font-medium">Plan seleccionado</span>
                                </div>
                              </div>
                            )}
                          </CardContent>
                        </Card>
                      </div>
                    ))}
                  </div>

                  {selectedPlan && selectedPlan.yearlyPrice && selectedPlan.price > 0 && (
                    <div className="text-center">
                      <Separator className="my-4" />
                      <p className="text-sm text-gray-600 mb-2">¿Prefieres pago anual?</p>
                      <div className="flex justify-center space-x-4">
                        <Button
                          variant={selectedInterval === 'month' ? 'default' : 'outline'}
                          size="sm"
                          onClick={() => setSelectedInterval('month')}
                        >
                          Mensual
                        </Button>
                        <Button
                          variant={selectedInterval === 'year' ? 'default' : 'outline'}
                          size="sm"
                          onClick={() => setSelectedInterval('year')}
                        >
                          Anual
                          <Badge variant="secondary" className="ml-2">
                            -{calculateYearlyDiscount(selectedPlan.price * 12, selectedPlan.yearlyPrice)}%
                          </Badge>
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Step 4: Payment */}
              {currentStep === 4 && (
                <div className="text-center py-8 space-y-6">
                  <div className="w-16 h-16 bg-blue-100 dark:bg-blue-900 rounded-full flex items-center justify-center mx-auto">
                    {getPlanIcon(selectedPlan?.id || 'pro')}
                  </div>
                  
                  <div>
                    <h3 className="text-2xl font-bold mb-2">Confirma tu Plan</h3>
                    <p className="text-gray-600 dark:text-gray-300 mb-4">
                      Has seleccionado el plan <strong>{selectedPlan?.name}</strong>
                    </p>
                    <div className="text-3xl font-bold text-blue-600 mb-2">
                      {selectedInterval === 'year' && selectedPlan?.yearlyPrice 
                        ? formatPrice(selectedPlan.yearlyPrice)
                        : formatPrice(selectedPlan?.price || 0)
                      }
                      <span className="text-base text-gray-500">
                        /{selectedInterval === 'year' ? 'año' : 'mes'}
                      </span>
                    </div>
                    {selectedInterval === 'year' && selectedPlan?.yearlyPrice && (
                      <p className="text-sm text-green-600">
                        Ahorras {calculateYearlyDiscount(selectedPlan.price * 12, selectedPlan.yearlyPrice)}% con el pago anual
                      </p>
                    )}
                  </div>

                  <Button 
                    onClick={handlePayment}
                    size="lg"
                    disabled={isProcessing}
                    className="bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 text-white px-8"
                  >
                    {isProcessing ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin mr-2" />
                        Procesando...
                      </>
                    ) : (
                      <>
                        Proceder al Pago
                        <ArrowRight className="h-4 w-4 ml-2" />
                      </>
                    )}
                  </Button>
                  
                  <p className="text-xs text-gray-500">
                    Serás redirigido a Stripe para completar el pago de forma segura
                  </p>
                </div>
              )}

              {/* Step 5: Complete */}
              {currentStep === 5 && (
                <div className="text-center py-8 space-y-6">
                  <div className="w-16 h-16 bg-green-100 dark:bg-green-900 rounded-full flex items-center justify-center mx-auto">
                    <CheckCircle className="h-8 w-8 text-green-600 dark:text-green-400" />
                  </div>
                  
                  <div>
                    <h3 className="text-2xl font-bold text-green-600 dark:text-green-400 mb-2">
                      ¡Cuenta configurada!
                    </h3>
                    <p className="text-gray-600 dark:text-gray-300 mb-6">
                      Tu cuenta está lista para usar. ¡Comienza a explorar Nexus!
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
                    disabled={isProcessing || (currentStep === 3 && !selectedPlan)}
                  >
                    {isProcessing ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin mr-2" />
                        Procesando...
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