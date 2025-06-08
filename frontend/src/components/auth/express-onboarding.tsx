'use client'

import { useState, useEffect } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
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
}

export function ExpressOnboarding({ checkoutData }: ExpressOnboardingProps) {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { 
    clerkUser, 
    syncUserWithBackend, 
    markOnboardingComplete,
    backendUser 
  } = useUserContext()

  const [currentStep, setCurrentStep] = useState(0)
  const [isProcessing, setIsProcessing] = useState(false)
  const [syncCompleted, setSyncCompleted] = useState(false)

  const form = useForm<CompanyFormData>({
    resolver: zodResolver(companyFormSchema),
    defaultValues: {
      companyName: '',
      industry: '',
      teamSize: '',
      useCase: '',
    }
  })

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
      if (clerkUser && !syncCompleted) {
        try {
          setIsProcessing(true)
          
          // Get Stripe data from URL params or props
          const sessionId = searchParams.get('session_id')
          const stripeData = sessionId ? {
            sessionId,
            customerId: checkoutData ? 'pending' : undefined, // Will be fetched from session
            planId: checkoutData?.plan_id
          } : undefined

          await syncUserWithBackend(stripeData)
          setSyncCompleted(true)
          setCurrentStep(1)
        } catch (error) {
          console.error('Sync error:', error)
        } finally {
          setIsProcessing(false)
        }
      }
    }

    performSync()
  }, [clerkUser, syncCompleted, searchParams, checkoutData, syncUserWithBackend])

  const handleCompanySubmit = async (data: CompanyFormData) => {
    try {
      setIsProcessing(true)
      
      await markOnboardingComplete({
        company_name: data.companyName,
        industry: data.industry,
        team_size: data.teamSize,
        use_case: data.useCase,
      })
      
      setCurrentStep(2)
    } catch (error) {
      console.error('Error completing onboarding:', error)
    } finally {
      setIsProcessing(false)
    }
  }

  const handleGoToDashboard = () => {
    if (backendUser?.tenant_id) {
      router.push(`/${backendUser.tenant_id}/dashboard`)
    } else {
      router.push('/dashboard')
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
                  <Loader2 className="h-8 w-8 animate-spin mx-auto text-blue-600 mb-4" />
                  <p className="text-lg font-medium mb-2">Configurando tu cuenta premium...</p>
                  <p className="text-gray-600 dark:text-gray-300">
                    Estamos preparando todo para que puedas aprovechar al máximo Nexus
                  </p>
                </div>
              )}

              {/* Step 1: Company Data */}
              {currentStep === 1 && (
                <div className="space-y-6">
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