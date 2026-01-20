'use client'

import { useEffect, useState, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useAuth, useUser } from '@clerk/nextjs'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Loader2, CheckCircle, AlertCircle, User, CreditCard, Building, Rocket } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { Badge } from '@/components/ui/badge'

interface ProcessStep {
  id: string
  title: string
  description: string
  icon: React.ReactNode
  status: 'pending' | 'processing' | 'completed' | 'error'
}

function PostSignUpContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { isLoaded, isSignedIn } = useAuth()
  const { user } = useUser()
  
  const [currentStep, setCurrentStep] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [retryCount, setRetryCount] = useState(0)
  
  // Obtener plan desde metadata o params
  const plan = user?.unsafeMetadata?.plan as string || searchParams.get('plan') || 'free'
  const rawInterval =
    (user?.unsafeMetadata?.interval as string) ||
    searchParams.get('interval') ||
    'month'
  const interval =
    rawInterval?.toLowerCase() === 'yearly'
      ? 'year'
      : rawInterval?.toLowerCase() === 'monthly'
        ? 'month'
        : rawInterval?.toLowerCase() ?? 'month'
  const isPaidPlan = plan !== 'free' && plan !== 'enterprise'
  
  // Definir los pasos del proceso
  const [steps, setSteps] = useState<ProcessStep[]>([
    {
      id: 'account',
      title: 'Cuenta creada',
      description: 'Tu cuenta ha sido creada exitosamente',
      icon: <User className="h-5 w-5" />,
      status: 'completed'
    },
    {
      id: 'verification',
      title: 'Verificando información',
      description: 'Confirmando los datos de tu cuenta',
      icon: <CheckCircle className="h-5 w-5" />,
      status: 'pending'
    },
    ...(isPaidPlan ? [{
      id: 'payment',
      title: 'Configurando suscripción',
      description: `Preparando tu plan ${plan}`,
      icon: <CreditCard className="h-5 w-5" />,
      status: 'pending' as const
    }] : []),
    {
      id: 'workspace',
      title: 'Preparando tu espacio',
      description: 'Configurando tu workspace',
      icon: <Building className="h-5 w-5" />,
      status: 'pending'
    },
    {
      id: 'complete',
      title: '¡Todo listo!',
      description: 'Redirigiendo a tu dashboard',
      icon: <Rocket className="h-5 w-5" />,
      status: 'pending'
    }
  ])

  // Calcular progreso
  const progress = ((steps.filter(s => s.status === 'completed').length) / steps.length) * 100

  useEffect(() => {
    if (!isLoaded) return
    
    if (!isSignedIn) {
      router.push('/auth/sign-in')
      return
    }

    // Iniciar el proceso
    processSteps()
  }, [isLoaded, isSignedIn, user])

  const updateStepStatus = (stepId: string, status: ProcessStep['status']) => {
    setSteps(prev => prev.map(step => 
      step.id === stepId ? { ...step, status } : step
    ))
  }

  const processSteps = async () => {
    try {
      // Paso 1: Verificación (ya completado, usuario creado)
      setCurrentStep(1)
      updateStepStatus('verification', 'processing')
      await new Promise(resolve => setTimeout(resolve, 1500))
      updateStepStatus('verification', 'completed')

      // Paso 2: Configurar pago si es necesario
      if (isPaidPlan) {
        setCurrentStep(2)
        updateStepStatus('payment', 'processing')
        
        // Esperar un poco más para asegurar sincronización
        await new Promise(resolve => setTimeout(resolve, 2000))
        
        const response = await fetch('/api/stripe/create-checkout-session', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            plan,
            interval,
            userEmail: user?.emailAddresses?.[0]?.emailAddress,
            successUrl: `${window.location.origin}/onboarding?session_id={CHECKOUT_SESSION_ID}`,
            cancelUrl: `${window.location.origin}/pricing`,
          }),
        })

        if (response.ok) {
          const { url } = await response.json()
          updateStepStatus('payment', 'completed')
          
          // Mostrar mensaje de redirección
          setCurrentStep(steps.length - 1)
          updateStepStatus('workspace', 'completed')
          updateStepStatus('complete', 'processing')
          
          await new Promise(resolve => setTimeout(resolve, 1000))
          updateStepStatus('complete', 'completed')
          
          // Redirigir a Stripe
          setTimeout(() => {
            window.location.href = url
          }, 500)
          return
        } else {
          throw new Error('No se pudo configurar la suscripción')
        }
      }

      // Paso 3: Preparar workspace
      setCurrentStep(isPaidPlan ? 3 : 2)
      updateStepStatus('workspace', 'processing')
      
      // Crear registro en backend si es necesario
      try {
        await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/v1/users/complete-registration`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            clerk_user_id: user?.id,
            email: user?.emailAddresses?.[0]?.emailAddress,
            plan: plan,
          }),
        })
      } catch (err) {
        console.log('Backend registration will be handled by webhook')
      }
      
      await new Promise(resolve => setTimeout(resolve, 1500))
      updateStepStatus('workspace', 'completed')

      // Paso 4: Completar y redirigir
      setCurrentStep(steps.length - 1)
      updateStepStatus('complete', 'processing')
      await new Promise(resolve => setTimeout(resolve, 1000))
      updateStepStatus('complete', 'completed')
      
      // Redirigir a onboarding
      setTimeout(() => {
        router.push('/onboarding')
      }, 500)
      
    } catch (error) {
      console.error('Error in registration process:', error)
      setError(error instanceof Error ? error.message : 'Error desconocido')
      
      // Marcar el paso actual como error
      const currentStepId = steps[currentStep]?.id
      if (currentStepId) {
        updateStepStatus(currentStepId, 'error')
      }
    }
  }

  const handleRetry = () => {
    setError(null)
    setRetryCount(prev => prev + 1)
    
    // Reset steps
    setSteps(prev => prev.map((step, index) => ({
      ...step,
      status: index === 0 ? 'completed' : 'pending'
    })))
    
    processSteps()
  }

  const handleContinueWithFree = () => {
    router.push('/onboarding?plan=free')
  }

  const getStepIcon = (step: ProcessStep) => {
    if (step.status === 'completed') {
      return <CheckCircle className="h-5 w-5 text-green-600" />
    }
    if (step.status === 'processing') {
      return <Loader2 className="h-5 w-5 animate-spin text-blue-600" />
    }
    if (step.status === 'error') {
      return <AlertCircle className="h-5 w-5 text-red-600" />
    }
    return step.icon
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800 p-4">
      <Card className="max-w-2xl w-full shadow-xl">
        <CardHeader className="text-center pb-4">
          <div className="flex justify-center mb-4">
            <div className="relative">
              <div className="h-20 w-20 rounded-full bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center">
                {error ? (
                  <AlertCircle className="h-10 w-10 text-red-600" />
                ) : currentStep === steps.length - 1 && steps[currentStep].status === 'completed' ? (
                  <CheckCircle className="h-10 w-10 text-green-600" />
                ) : (
                  <Loader2 className="h-10 w-10 animate-spin text-blue-600" />
                )}
              </div>
            </div>
          </div>
          
          <CardTitle className="text-2xl">
            {error ? 'Hubo un problema' : '¡Bienvenido a Nexus Documents!'}
          </CardTitle>
          
          <CardDescription className="mt-2 text-base">
            {error ? (
              error
            ) : (
              <>
                Hola <span className="font-semibold">{user?.firstName || user?.emailAddresses?.[0]?.emailAddress}</span>
                <br />
                Estamos configurando tu cuenta
              </>
            )}
          </CardDescription>
          
          {plan !== 'free' && !error && (
            <div className="mt-3">
              <Badge variant="default" className="text-sm">
                Plan {plan} - {interval === 'year' ? 'Anual' : 'Mensual'}
              </Badge>
            </div>
          )}
        </CardHeader>
        
        <CardContent className="space-y-6">
          {!error && (
            <>
              {/* Progress bar */}
              <div className="space-y-2">
                <div className="flex justify-between text-sm text-muted-foreground">
                  <span>Progreso</span>
                  <span>{Math.round(progress)}%</span>
                </div>
                <Progress value={progress} className="h-2" />
              </div>
              
              {/* Steps */}
              <div className="space-y-3">
                {steps.map((step, index) => (
                  <div
                    key={step.id}
                    className={`flex items-start space-x-3 p-3 rounded-lg transition-all ${
                      step.status === 'processing' 
                        ? 'bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800' 
                        : step.status === 'completed'
                        ? 'bg-green-50 dark:bg-green-900/20'
                        : step.status === 'error'
                        ? 'bg-red-50 dark:bg-red-900/20'
                        : 'bg-gray-50 dark:bg-gray-900/20'
                    }`}
                  >
                    <div className="flex-shrink-0 mt-0.5">
                      {getStepIcon(step)}
                    </div>
                    <div className="flex-1">
                      <p className={`font-medium ${
                        step.status === 'processing' ? 'text-blue-900 dark:text-blue-100' :
                        step.status === 'completed' ? 'text-green-900 dark:text-green-100' :
                        step.status === 'error' ? 'text-red-900 dark:text-red-100' :
                        'text-gray-500'
                      }`}>
                        {step.title}
                      </p>
                      <p className={`text-sm ${
                        step.status === 'processing' ? 'text-blue-700 dark:text-blue-300' :
                        step.status === 'completed' ? 'text-green-700 dark:text-green-300' :
                        step.status === 'error' ? 'text-red-700 dark:text-red-300' :
                        'text-gray-400'
                      }`}>
                        {step.description}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
          
          {/* Error actions */}
          {error && (
            <div className="space-y-3 pt-4">
              <Button 
                onClick={handleRetry}
                className="w-full"
                variant="default"
                disabled={retryCount > 2}
              >
                {retryCount > 2 ? 'Máximo de reintentos alcanzado' : 'Reintentar'}
              </Button>
              
              {isPaidPlan && (
                <Button 
                  onClick={handleContinueWithFree}
                  className="w-full"
                  variant="outline"
                >
                  Continuar con plan gratuito
                </Button>
              )}
              
              <Button 
                onClick={() => router.push('/pricing')}
                className="w-full"
                variant="ghost"
              >
                Volver a elegir plan
              </Button>
              
              <p className="text-xs text-center text-muted-foreground">
                Si el problema persiste, contacta a soporte: support@nexusdocs360.app
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

/**
 * Página de confirmación y procesamiento post-registro
 * Muestra el progreso paso a paso del proceso de configuración
 */
export default function PostSignUpPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
      </div>
    }>
      <PostSignUpContent />
    </Suspense>
  )
}
