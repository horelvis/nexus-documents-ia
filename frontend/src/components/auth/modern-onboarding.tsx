'use client'

import { useState, useEffect, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { 
  CheckCircle, 
  User, 
  Building, 
  Shield, 
  FileText, 
  Bot,
  ArrowRight,
  Loader2,
  AlertCircle,
  Sparkles,
  Zap,
  Target
} from 'lucide-react'
import { useUserContext } from '@/contexts/user-context'

interface OnboardingStep {
  id: string
  title: string
  description: string
  icon: React.ReactNode
  completed: boolean
  action?: () => Promise<void>
}

interface ModernOnboardingProps {
  onComplete?: () => void
}

export function ModernOnboarding({ onComplete }: ModernOnboardingProps) {
  const { 
    clerkUser, 
    isClerkLoaded, 
    syncUserWithBackend, 
    markOnboardingComplete 
  } = useUserContext()
  const [currentStep, setCurrentStep] = useState(0)
  const [isProcessing, setIsProcessing] = useState(false)
  const [syncStatus, setSyncStatus] = useState<'pending' | 'success' | 'error'>('pending')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  async function handleUserSync(): Promise<void> {
    try {
      setIsProcessing(true)
      setSyncStatus('pending')
      await syncUserWithBackend()
      setSyncStatus('success')
      return Promise.resolve()
    } catch (error) {
      setSyncStatus('error')
      const errorMsg = error instanceof Error ? error.message : 'Error desconocido'
      setErrorMessage(errorMsg)
      throw error
    } finally {
      setIsProcessing(false)
    }
  }

  const [steps, setSteps] = useState<OnboardingStep[]>([
    {
      id: 'user-sync',
      title: 'Configuración de Usuario',
      description: 'Sincronizamos tu información con nuestro sistema',
      icon: <User className="h-6 w-6" />,
      completed: false,
      action: handleUserSync
    },
    {
      id: 'welcome',
      title: 'Bienvenida a Nexus',
      description: 'Descubre las funcionalidades principales',
      icon: <Sparkles className="h-6 w-6" />,
      completed: false
    },
    {
      id: 'permissions',
      title: 'Configuración de Permisos',
      description: 'Revisa y configura tus permisos de acceso',
      icon: <Shield className="h-6 w-6" />,
      completed: false
    },
    {
      id: 'first-document',
      title: 'Tu Primer Documento',
      description: 'Aprende a subir y gestionar documentos',
      icon: <FileText className="h-6 w-6" />,
      completed: false
    },
    {
      id: 'ai-agents',
      title: 'Agentes de IA',
      description: 'Explora nuestros asistentes inteligentes',
      icon: <Bot className="h-6 w-6" />,
      completed: false
    }
  ])

  useEffect(() => {
    if (isClerkLoaded && clerkUser) {
      handleStepAction(0)
    }
  }, [isClerkLoaded, clerkUser, handleStepAction])

  const handleStepAction = useCallback(async (stepIndex: number) => {
    const step = steps[stepIndex]
    
    if (step.action) {
      try {
        setIsProcessing(true)
        await step.action()
        
        const updatedSteps = [...steps]
        updatedSteps[stepIndex].completed = true
        setSteps(updatedSteps)
        
        if (stepIndex < steps.length - 1) {
          setCurrentStep(stepIndex + 1)
        }
      } catch (error) {
        console.error(`Error in step ${step.id}:`, error)
      } finally {
        setIsProcessing(false)
      }
    } else {
      const updatedSteps = [...steps]
      updatedSteps[stepIndex].completed = true
      setSteps(updatedSteps)
      
      if (stepIndex < steps.length - 1) {
        setCurrentStep(stepIndex + 1)
      }
    }
  }, [steps])

  const handleCompleteOnboarding = async () => {
    try {
      await markOnboardingComplete()
      const updatedSteps = steps.map(step => ({ ...step, completed: true }))
      setSteps(updatedSteps)
      onComplete?.()
    } catch (error) {
      console.error('Error completing onboarding:', error)
      const updatedSteps = steps.map(step => ({ ...step, completed: true }))
      setSteps(updatedSteps)
      onComplete?.()
    }
  }

  const completedSteps = steps.filter(step => step.completed).length
  const progressPercentage = (completedSteps / steps.length) * 100

  if (!isClerkLoaded) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 via-indigo-50 to-purple-50 flex items-center justify-center">
        <div className="text-center space-y-4">
          <Loader2 className="h-12 w-12 animate-spin mx-auto text-blue-600" />
          <p className="text-lg font-medium text-gray-700">Cargando...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-indigo-50 to-purple-50">
      <div className="container mx-auto px-4 py-8">
        {/* Header */}
        <div className="text-center mb-12">
          <div className="inline-flex items-center justify-center w-20 h-20 bg-gradient-to-r from-blue-600 to-purple-600 rounded-full mb-6">
            <Building className="h-10 w-10 text-white" />
          </div>
          
          <h1 className="text-4xl md:text-5xl font-bold bg-gradient-to-r from-gray-900 to-gray-600 bg-clip-text text-transparent mb-4">
            ¡Bienvenido a Nexus!
          </h1>
          
          <p className="text-xl text-gray-600 max-w-2xl mx-auto mb-8">
            Tu plataforma de gestión documental inteligente. Configuremos tu cuenta en unos simples pasos.
          </p>
          
          {/* Progress */}
          <div className="max-w-md mx-auto">
            <div className="flex items-center justify-between text-sm font-medium text-gray-600 mb-3">
              <span>Progreso de configuración</span>
              <span>{completedSteps} de {steps.length}</span>
            </div>
            <Progress value={progressPercentage} className="h-3" />
          </div>
        </div>

        {/* Main Content */}
        <div className="max-w-4xl mx-auto">
          {/* Steps Overview */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-12">
            {steps.map((step, index) => (
              <div
                key={step.id}
                className={`relative p-4 rounded-xl text-center transition-all ${
                  step.completed
                    ? 'bg-green-100 border-2 border-green-200'
                    : index === currentStep
                    ? 'bg-blue-100 border-2 border-blue-200 scale-105'
                    : 'bg-white border-2 border-gray-200'
                }`}
              >
                <div className={`inline-flex items-center justify-center w-12 h-12 rounded-full mb-3 ${
                  step.completed
                    ? 'bg-green-500 text-white'
                    : index === currentStep
                    ? 'bg-blue-500 text-white'
                    : 'bg-gray-200 text-gray-500'
                }`}>
                  {step.completed ? <CheckCircle className="h-6 w-6" /> : step.icon}
                </div>
                <p className={`text-sm font-medium ${
                  step.completed ? 'text-green-800' :
                  index === currentStep ? 'text-blue-800' : 'text-gray-600'
                }`}>
                  {step.title}
                </p>
                
                {index === currentStep && (
                  <div className="absolute -bottom-2 left-1/2 transform -translate-x-1/2">
                    <div className="w-4 h-4 bg-blue-500 rotate-45"></div>
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Current Step Content */}
          <Card className="border-0 shadow-xl bg-white/80 backdrop-blur-sm">
            <CardHeader className="text-center pb-6">
              <div className="inline-flex items-center justify-center w-16 h-16 bg-gradient-to-r from-blue-500 to-purple-500 rounded-full mb-4">
                {steps[currentStep]?.icon && (
                  <div className="text-white">
                    {steps[currentStep].icon}
                  </div>
                )}
              </div>
              <CardTitle className="text-2xl font-bold">{steps[currentStep]?.title}</CardTitle>
              <CardDescription className="text-lg">{steps[currentStep]?.description}</CardDescription>
            </CardHeader>
            
            <CardContent className="pt-0">
              {/* Step Content */}
              {currentStep === 0 && (
                <div className="text-center py-8">
                  {syncStatus === 'pending' && (
                    <div className="space-y-6">
                      <Loader2 className="h-16 w-16 mx-auto animate-spin text-blue-600" />
                      <div>
                        <p className="text-xl font-semibold mb-2">Configurando tu cuenta...</p>
                        <p className="text-gray-600">
                          Estamos sincronizando tu información con nuestro sistema
                        </p>
                      </div>
                    </div>
                  )}
                  
                  {syncStatus === 'success' && (
                    <div className="space-y-6">
                      <div className="inline-flex items-center justify-center w-20 h-20 bg-green-100 rounded-full">
                        <CheckCircle className="h-12 w-12 text-green-600" />
                      </div>
                      <div>
                        <p className="text-xl font-semibold text-green-800 mb-2">¡Cuenta configurada!</p>
                        <p className="text-gray-600 mb-6">
                          Tu perfil ha sido sincronizado correctamente
                        </p>
                        <Button 
                          onClick={() => handleStepAction(currentStep + 1)}
                          size="lg"
                          className="bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700"
                        >
                          Continuar
                          <ArrowRight className="h-5 w-5 ml-2" />
                        </Button>
                      </div>
                    </div>
                  )}
                  
                  {syncStatus === 'error' && (
                    <div className="space-y-6">
                      <div className="inline-flex items-center justify-center w-20 h-20 bg-red-100 rounded-full">
                        <AlertCircle className="h-12 w-12 text-red-600" />
                      </div>
                      <div>
                        <p className="text-xl font-semibold text-red-800 mb-2">Error de configuración</p>
                        <p className="text-red-600 mb-6">{errorMessage}</p>
                        <div className="flex gap-3 justify-center">
                          <Button 
                            onClick={() => handleStepAction(0)}
                            disabled={isProcessing}
                            variant="outline"
                          >
                            Reintentar
                          </Button>
                          <Button 
                            onClick={() => handleStepAction(1)}
                            variant="outline"
                          >
                            Omitir por ahora
                          </Button>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {currentStep === 1 && (
                <div className="space-y-8">
                  <div className="text-center">
                    <h3 className="text-2xl font-bold mb-4">Tu plataforma de documentos inteligente</h3>
                    <p className="text-lg text-gray-600 mb-8">
                      Nexus combina gestión documental tradicional con inteligencia artificial para 
                      revolucionar la forma en que trabajas con tus documentos.
                    </p>
                  </div>
                  
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    <div className="text-center p-6 rounded-xl bg-gradient-to-br from-blue-50 to-indigo-50 border border-blue-200">
                      <div className="inline-flex items-center justify-center w-12 h-12 bg-blue-500 rounded-full mb-4">
                        <FileText className="h-6 w-6 text-white" />
                      </div>
                      <h4 className="font-semibold text-blue-900 mb-2">Gestión Inteligente</h4>
                      <p className="text-sm text-blue-700">Organiza, busca y gestiona documentos con IA</p>
                    </div>
                    
                    <div className="text-center p-6 rounded-xl bg-gradient-to-br from-purple-50 to-pink-50 border border-purple-200">
                      <div className="inline-flex items-center justify-center w-12 h-12 bg-purple-500 rounded-full mb-4">
                        <Bot className="h-6 w-6 text-white" />
                      </div>
                      <h4 className="font-semibold text-purple-900 mb-2">Agentes IA</h4>
                      <p className="text-sm text-purple-700">Asistentes que automatizan tus tareas</p>
                    </div>
                    
                    <div className="text-center p-6 rounded-xl bg-gradient-to-br from-green-50 to-emerald-50 border border-green-200">
                      <div className="inline-flex items-center justify-center w-12 h-12 bg-green-500 rounded-full mb-4">
                        <Zap className="h-6 w-6 text-white" />
                      </div>
                      <h4 className="font-semibold text-green-900 mb-2">Búsqueda Semántica</h4>
                      <p className="text-sm text-green-700">Encuentra contenido por significado, no solo palabras</p>
                    </div>
                  </div>
                  
                  <div className="text-center">
                    <Button 
                      onClick={() => handleStepAction(currentStep)}
                      size="lg"
                      className="bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700"
                    >
                      ¡Empecemos!
                      <ArrowRight className="h-5 w-5 ml-2" />
                    </Button>
                  </div>
                </div>
              )}

              {currentStep === 2 && (
                <div className="space-y-8">
                  <div className="text-center">
                    <h3 className="text-2xl font-bold mb-4">Configuración de Seguridad</h3>
                    <p className="text-lg text-gray-600 mb-8">
                      Tu cuenta tiene configurados los siguientes permisos de acceso
                    </p>
                  </div>
                  
                  <div className="space-y-4">
                    <div className="flex items-center justify-between p-4 rounded-xl bg-green-50 border border-green-200">
                      <div className="flex items-center space-x-4">
                        <CheckCircle className="h-6 w-6 text-green-600" />
                        <div>
                          <p className="font-semibold text-green-900">Acceso a Documentos</p>
                          <p className="text-sm text-green-700">Puedes subir, ver y gestionar documentos</p>
                        </div>
                      </div>
                      <Badge className="bg-green-100 text-green-800 border-green-300">Activo</Badge>
                    </div>
                    
                    <div className="flex items-center justify-between p-4 rounded-xl bg-green-50 border border-green-200">
                      <div className="flex items-center space-x-4">
                        <CheckCircle className="h-6 w-6 text-green-600" />
                        <div>
                          <p className="font-semibold text-green-900">Agentes de IA</p>
                          <p className="text-sm text-green-700">Acceso a asistentes inteligentes</p>
                        </div>
                      </div>
                      <Badge className="bg-green-100 text-green-800 border-green-300">Activo</Badge>
                    </div>
                    
                    <div className="flex items-center justify-between p-4 rounded-xl bg-gray-50 border border-gray-200">
                      <div className="flex items-center space-x-4">
                        <Target className="h-6 w-6 text-gray-600" />
                        <div>
                          <p className="font-semibold text-gray-900">Funciones Administrativas</p>
                          <p className="text-sm text-gray-700">Disponible con planes premium</p>
                        </div>
                      </div>
                      <Badge variant="secondary">Pendiente</Badge>
                    </div>
                  </div>
                  
                  <div className="text-center">
                    <Button 
                      onClick={() => handleStepAction(currentStep)}
                      size="lg"
                      className="bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700"
                    >
                      Continuar
                      <ArrowRight className="h-5 w-5 ml-2" />
                    </Button>
                  </div>
                </div>
              )}

              {/* Similar modern designs for steps 3 and 4... */}
              {(currentStep === 3 || currentStep === 4) && (
                <div className="text-center py-8">
                  <div className="space-y-6">
                    <div className="inline-flex items-center justify-center w-20 h-20 bg-blue-100 rounded-full">
                      {steps[currentStep].icon}
                    </div>
                    <div>
                      <h3 className="text-2xl font-bold mb-4">{steps[currentStep].title}</h3>
                      <p className="text-lg text-gray-600 mb-8">
                        Estas funcionalidades estarán disponibles una vez que completes la configuración
                      </p>
                      <Button 
                        onClick={() => handleStepAction(currentStep)}
                        size="lg"
                        className="bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700"
                      >
                        Continuar
                        <ArrowRight className="h-5 w-5 ml-2" />
                      </Button>
                    </div>
                  </div>
                </div>
              )}

              {currentStep >= 5 && (
                <div className="text-center py-8">
                  <div className="space-y-8">
                    <div className="inline-flex items-center justify-center w-24 h-24 bg-gradient-to-r from-green-400 to-blue-500 rounded-full">
                      <CheckCircle className="h-14 w-14 text-white" />
                    </div>
                    <div>
                      <h3 className="text-3xl font-bold mb-4">¡Configuración Completa!</h3>
                      <p className="text-xl text-gray-600 mb-8">
                        Tu cuenta está lista para usar. ¡Comienza a explorar Nexus!
                      </p>
                      <Button 
                        onClick={handleCompleteOnboarding}
                        size="lg"
                        className="bg-gradient-to-r from-green-600 to-blue-600 hover:from-green-700 hover:to-blue-700 px-8 py-4 text-lg"
                      >
                        Ir al Dashboard
                        <ArrowRight className="h-6 w-6 ml-2" />
                      </Button>
                    </div>
                  </div>
                </div>
              )}

              {/* Skip option */}
              {currentStep < steps.length - 1 && syncStatus !== 'pending' && (
                <div className="text-center pt-8 border-t">
                  <Button 
                    variant="ghost" 
                    onClick={handleCompleteOnboarding}
                    className="text-gray-500 hover:text-gray-700"
                  >
                    Omitir configuración y continuar
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