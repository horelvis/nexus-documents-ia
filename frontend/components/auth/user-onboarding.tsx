'use client'

import { useState, useEffect } from 'react'
import { useUser } from '@clerk/nextjs'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { 
  CheckCircle, 
  User, 
  Building, 
  Shield, 
  FileText, 
  Bot,
  ArrowRight,
  Loader2,
  AlertCircle
} from 'lucide-react'
import { apiClient } from '@/lib/api-client'

interface OnboardingStep {
  id: string
  title: string
  description: string
  icon: React.ReactNode
  completed: boolean
  action?: () => Promise<void>
}

interface UserOnboardingProps {
  onComplete?: () => void
}

export function UserOnboarding({ onComplete }: UserOnboardingProps) {
  const { user, isLoaded } = useUser()
  const [currentStep, setCurrentStep] = useState(0)
  const [isProcessing, setIsProcessing] = useState(false)
  const [syncStatus, setSyncStatus] = useState<'pending' | 'success' | 'error'>('pending')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const [steps, setSteps] = useState<OnboardingStep[]>([
    {
      id: 'user-sync',
      title: 'Sincronizar Usuario',
      description: 'Sincronizamos tu información con nuestro sistema',
      icon: <User className="h-5 w-5" />,
      completed: false,
      action: syncUserWithBackend
    },
    {
      id: 'welcome',
      title: 'Bienvenida',
      description: 'Conoce las características principales de Nexus',
      icon: <Building className="h-5 w-5" />,
      completed: false
    },
    {
      id: 'permissions',
      title: 'Configurar Permisos',
      description: 'Revisa tus permisos y configuraciones de seguridad',
      icon: <Shield className="h-5 w-5" />,
      completed: false
    },
    {
      id: 'first-document',
      title: 'Subir Primer Documento',
      description: 'Prueba subiendo tu primer documento al sistema',
      icon: <FileText className="h-5 w-5" />,
      completed: false
    },
    {
      id: 'ai-agents',
      title: 'Explorar Agentes IA',
      description: 'Descubre cómo los agentes de IA pueden ayudarte',
      icon: <Bot className="h-5 w-5" />,
      completed: false
    }
  ])

  useEffect(() => {
    if (isLoaded && user) {
      // Auto-start with user sync
      handleStepAction(0)
    }
  }, [isLoaded, user])

  async function syncUserWithBackend(): Promise<void> {
    if (!user) throw new Error('No user found')

    try {
      setIsProcessing(true)
      setSyncStatus('pending')

      const response = await apiClient.post('/auth/sync-user', {
        clerk_user_id: user.id,
        email: user.emailAddresses[0]?.emailAddress,
        full_name: `${user.firstName || ''} ${user.lastName || ''}`.trim()
      })

      if (response.error) {
        throw new Error(response.error)
      }

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

  const handleStepAction = async (stepIndex: number) => {
    const step = steps[stepIndex]
    
    if (step.action) {
      try {
        setIsProcessing(true)
        await step.action()
        
        // Mark step as completed
        const updatedSteps = [...steps]
        updatedSteps[stepIndex].completed = true
        setSteps(updatedSteps)
        
        // Move to next step
        if (stepIndex < steps.length - 1) {
          setCurrentStep(stepIndex + 1)
        }
      } catch (error) {
        console.error(`Error in step ${step.id}:`, error)
      } finally {
        setIsProcessing(false)
      }
    } else {
      // Mark manual step as completed
      const updatedSteps = [...steps]
      updatedSteps[stepIndex].completed = true
      setSteps(updatedSteps)
      
      // Move to next step
      if (stepIndex < steps.length - 1) {
        setCurrentStep(stepIndex + 1)
      }
    }
  }

  const handleSkipStep = () => {
    if (currentStep < steps.length - 1) {
      setCurrentStep(currentStep + 1)
    }
  }

  const handleCompleteOnboarding = () => {
    // Mark all remaining steps as completed
    const updatedSteps = steps.map(step => ({ ...step, completed: true }))
    setSteps(updatedSteps)
    onComplete?.()
  }

  const completedSteps = steps.filter(step => step.completed).length
  const progressPercentage = (completedSteps / steps.length) * 100

  if (!isLoaded) {
    return (
      <div className="flex items-center justify-center p-8">
        <Loader2 className="h-8 w-8 animate-spin" />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 py-8">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">
            ¡Bienvenido a Nexus! 
          </h1>
          <p className="text-lg text-gray-600 mb-4">
            Configuremos tu cuenta para que puedas aprovechar al máximo nuestra plataforma
          </p>
          
          {/* Progress Bar */}
          <div className="max-w-md mx-auto">
            <div className="flex items-center justify-between text-sm text-gray-600 mb-2">
              <span>Progreso</span>
              <span>{completedSteps} de {steps.length} completados</span>
            </div>
            <Progress value={progressPercentage} className="w-full" />
          </div>
        </div>

        {/* Main Content */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Steps Sidebar */}
          <div className="lg:col-span-1">
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Pasos de Configuración</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {steps.map((step, index) => (
                  <div
                    key={step.id}
                    className={`flex items-center space-x-3 p-3 rounded-lg border transition-colors ${
                      index === currentStep
                        ? 'border-blue-200 bg-blue-50'
                        : step.completed
                        ? 'border-green-200 bg-green-50'
                        : 'border-gray-200 bg-white'
                    }`}
                  >
                    <div className={`flex-shrink-0 ${
                      step.completed ? 'text-green-600' : 
                      index === currentStep ? 'text-blue-600' : 'text-gray-400'
                    }`}>
                      {step.completed ? <CheckCircle className="h-5 w-5" /> : step.icon}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className={`text-sm font-medium ${
                        step.completed ? 'text-green-900' :
                        index === currentStep ? 'text-blue-900' : 'text-gray-900'
                      }`}>
                        {step.title}
                      </p>
                      <p className={`text-xs ${
                        step.completed ? 'text-green-700' :
                        index === currentStep ? 'text-blue-700' : 'text-gray-500'
                      }`}>
                        {step.description}
                      </p>
                    </div>
                    {step.completed && (
                      <Badge variant="secondary" className="bg-green-100 text-green-800">
                        ✓
                      </Badge>
                    )}
                  </div>
                ))}
              </CardContent>
            </Card>
          </div>

          {/* Current Step Content */}
          <div className="lg:col-span-2">
            <Card>
              <CardHeader>
                <div className="flex items-center space-x-3">
                  {steps[currentStep]?.icon}
                  <div>
                    <CardTitle>{steps[currentStep]?.title}</CardTitle>
                    <CardDescription>{steps[currentStep]?.description}</CardDescription>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                {/* Step-specific content */}
                {currentStep === 0 && (
                  <div className="space-y-4">
                    <div className="text-center py-8">
                      {syncStatus === 'pending' && (
                        <div className="space-y-4">
                          <Loader2 className="h-12 w-12 mx-auto animate-spin text-blue-600" />
                          <p className="text-lg font-medium">Sincronizando tu usuario...</p>
                          <p className="text-sm text-gray-600">
                            Estamos configurando tu cuenta en nuestro sistema
                          </p>
                        </div>
                      )}
                      
                      {syncStatus === 'success' && (
                        <div className="space-y-4">
                          <CheckCircle className="h-12 w-12 mx-auto text-green-600" />
                          <p className="text-lg font-medium text-green-900">¡Usuario sincronizado!</p>
                          <p className="text-sm text-gray-600">
                            Tu cuenta ha sido configurada correctamente
                          </p>
                          <Button onClick={() => handleStepAction(currentStep + 1)}>
                            Continuar
                            <ArrowRight className="h-4 w-4 ml-2" />
                          </Button>
                        </div>
                      )}
                      
                      {syncStatus === 'error' && (
                        <div className="space-y-4">
                          <AlertCircle className="h-12 w-12 mx-auto text-red-600" />
                          <p className="text-lg font-medium text-red-900">Error de sincronización</p>
                          <p className="text-sm text-red-600">{errorMessage}</p>
                          <div className="flex space-x-3 justify-center">
                            <Button 
                              variant="outline" 
                              onClick={() => handleStepAction(0)}
                              disabled={isProcessing}
                            >
                              Reintentar
                            </Button>
                            <Button 
                              variant="outline" 
                              onClick={handleSkipStep}
                            >
                              Omitir por ahora
                            </Button>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {currentStep === 1 && (
                  <div className="space-y-6">
                    <div className="text-center">
                      <h3 className="text-xl font-semibold mb-4">¡Bienvenido a Nexus!</h3>
                      <p className="text-gray-600 mb-6">
                        Nexus es tu plataforma de gestión documental potenciada por IA. 
                        Aquí podrás organizar, buscar y analizar tus documentos de manera inteligente.
                      </p>
                    </div>
                    
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="p-4 border rounded-lg">
                        <FileText className="h-8 w-8 text-blue-600 mb-2" />
                        <h4 className="font-semibold">Gestión de Documentos</h4>
                        <p className="text-sm text-gray-600">Sube, organiza y busca tus documentos</p>
                      </div>
                      <div className="p-4 border rounded-lg">
                        <Bot className="h-8 w-8 text-purple-600 mb-2" />
                        <h4 className="font-semibold">Agentes de IA</h4>
                        <p className="text-sm text-gray-600">Automatiza tareas con asistentes inteligentes</p>
                      </div>
                    </div>
                    
                    <div className="flex justify-center space-x-3">
                      <Button onClick={() => handleStepAction(currentStep)}>
                        Continuar
                        <ArrowRight className="h-4 w-4 ml-2" />
                      </Button>
                    </div>
                  </div>
                )}

                {currentStep === 2 && (
                  <div className="space-y-6">
                    <div>
                      <h3 className="text-xl font-semibold mb-4">Configuración de Seguridad</h3>
                      <p className="text-gray-600 mb-6">
                        Tu cuenta tiene los siguientes permisos configurados:
                      </p>
                    </div>
                    
                    <div className="space-y-3">
                      <div className="flex items-center justify-between p-3 bg-green-50 rounded-lg">
                        <div className="flex items-center space-x-3">
                          <CheckCircle className="h-5 w-5 text-green-600" />
                          <span>Acceso a documentos</span>
                        </div>
                        <Badge className="bg-green-100 text-green-800">Activo</Badge>
                      </div>
                      <div className="flex items-center justify-between p-3 bg-green-50 rounded-lg">
                        <div className="flex items-center space-x-3">
                          <CheckCircle className="h-5 w-5 text-green-600" />
                          <span>Uso de agentes IA</span>
                        </div>
                        <Badge className="bg-green-100 text-green-800">Activo</Badge>
                      </div>
                      <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                        <div className="flex items-center space-x-3">
                          <AlertCircle className="h-5 w-5 text-gray-600" />
                          <span>Administración (requiere upgrade)</span>
                        </div>
                        <Badge variant="secondary">Inactivo</Badge>
                      </div>
                    </div>
                    
                    <div className="flex justify-center space-x-3">
                      <Button onClick={() => handleStepAction(currentStep)}>
                        Continuar
                        <ArrowRight className="h-4 w-4 ml-2" />
                      </Button>
                    </div>
                  </div>
                )}

                {/* Remaining steps (4 and 5) can be implemented similarly */}
                {currentStep >= 3 && (
                  <div className="space-y-6 text-center">
                    <div>
                      <h3 className="text-xl font-semibold mb-4">¡Configuración Completa!</h3>
                      <p className="text-gray-600 mb-6">
                        Tu cuenta está lista. Puedes explorar las funcionalidades restantes 
                        directamente desde el dashboard.
                      </p>
                    </div>
                    
                    <Button onClick={handleCompleteOnboarding} size="lg">
                      Ir al Dashboard
                      <ArrowRight className="h-4 w-4 ml-2" />
                    </Button>
                  </div>
                )}

                {/* Skip option */}
                {currentStep < steps.length - 1 && syncStatus !== 'pending' && (
                  <div className="flex justify-center pt-4">
                    <Button variant="ghost" onClick={handleCompleteOnboarding}>
                      Omitir configuración
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  )
}