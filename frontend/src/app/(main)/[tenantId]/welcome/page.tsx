'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { OnboardingWizard } from '@/components/auth/onboarding-wizard'
import { useUserContext } from '@/contexts/user-context'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { AuthGuard } from "@/components/auth/auth-guard"
import { Sparkles, ArrowRight, Building, Users, FileText, Bot } from 'lucide-react'

export default function WelcomePage() {
  const router = useRouter()
  const { onboarding, clerkUser } = useUserContext()
  const [showOnboardingWizard, setShowOnboardingWizard] = useState(false)

  useEffect(() => {
    // If user doesn't need onboarding, redirect to dashboard
    if (!onboarding.loading && !onboarding.needsOnboarding) {
      router.replace('/dashboard')
    }
  }, [onboarding.loading, onboarding.needsOnboarding, router])

  const handleStartOnboarding = () => {
    setShowOnboardingWizard(true)
  }

  const handleOnboardingComplete = () => {
    setShowOnboardingWizard(false)
    router.push('/dashboard')
  }

  const handleSkipOnboarding = () => {
    router.push('/dashboard')
  }

  // Show loading while checking onboarding status
  if (onboarding.loading) {
    return (
      <AuthGuard>
        <div className="min-h-screen bg-black flex items-center justify-center">
          <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-blue-400"></div>
        </div>
      </AuthGuard>
    )
  }

  // If user doesn't need onboarding, this will redirect (handled in useEffect)
  if (!onboarding.needsOnboarding) {
    return (
      <AuthGuard>
        <div className="min-h-screen bg-black flex items-center justify-center">
          <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-blue-400"></div>
        </div>
      </AuthGuard>
    )
  }

  return (
    <AuthGuard>
      <div className="min-h-screen bg-black">
        <div className="container mx-auto px-4 py-16">
          <div className="max-w-6xl mx-auto">
            {/* Header */}
            <div className="text-center mb-12">
              <div className="inline-flex items-center justify-center w-20 h-20 bg-blue-600 rounded-full mb-6">
                <Sparkles className="h-10 w-10 text-white" />
              </div>
              <h1 className="text-4xl font-bold text-white mb-4">
                ¡Bienvenido a Nexus!
              </h1>
              <p className="text-xl text-gray-300 mb-2">
                Hola {clerkUser?.firstName || 'Usuario'}, estamos emocionados de tenerte aquí
              </p>
              <p className="text-lg text-gray-400">
                Configuremos tu cuenta para que puedas aprovechar al máximo nuestra plataforma
              </p>
            </div>

            {/* Features Preview */}
            <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6 mb-12">
              <Card className="text-center hover:shadow-xl transition-all bg-gray-900 border-gray-800 hover:border-blue-500">
                <CardHeader className="pb-4">
                  <div className="w-12 h-12 bg-blue-500/20 rounded-lg flex items-center justify-center mx-auto mb-3">
                    <Building className="h-6 w-6 text-blue-400" />
                  </div>
                  <CardTitle className="text-lg text-white">Gestión Empresarial</CardTitle>
                </CardHeader>
                <CardContent>
                  <CardDescription className="text-gray-400">
                    Organiza la información de tu empresa y equipos
                  </CardDescription>
                </CardContent>
              </Card>

              <Card className="text-center hover:shadow-xl transition-all bg-gray-900 border-gray-800 hover:border-purple-500">
                <CardHeader className="pb-4">
                  <div className="w-12 h-12 bg-purple-500/20 rounded-lg flex items-center justify-center mx-auto mb-3">
                    <FileText className="h-6 w-6 text-purple-400" />
                  </div>
                  <CardTitle className="text-lg text-white">Documentos Inteligentes</CardTitle>
                </CardHeader>
                <CardContent>
                  <CardDescription className="text-gray-400">
                    Gestiona y analiza documentos con IA avanzada
                  </CardDescription>
                </CardContent>
              </Card>

              <Card className="text-center hover:shadow-xl transition-all bg-gray-900 border-gray-800 hover:border-green-500">
                <CardHeader className="pb-4">
                  <div className="w-12 h-12 bg-green-500/20 rounded-lg flex items-center justify-center mx-auto mb-3">
                    <Bot className="h-6 w-6 text-green-400" />
                  </div>
                  <CardTitle className="text-lg text-white">Agentes IA</CardTitle>
                </CardHeader>
                <CardContent>
                  <CardDescription className="text-gray-400">
                    Automatiza tareas con asistentes inteligentes
                  </CardDescription>
                </CardContent>
              </Card>

              <Card className="text-center hover:shadow-xl transition-all bg-gray-900 border-gray-800 hover:border-orange-500">
                <CardHeader className="pb-4">
                  <div className="w-12 h-12 bg-orange-500/20 rounded-lg flex items-center justify-center mx-auto mb-3">
                    <Users className="h-6 w-6 text-orange-400" />
                  </div>
                  <CardTitle className="text-lg text-white">Colaboración</CardTitle>
                </CardHeader>
                <CardContent>
                  <CardDescription className="text-gray-400">
                    Trabaja en equipo de forma eficiente y segura
                  </CardDescription>
                </CardContent>
              </Card>
            </div>

            {/* CTA Section */}
            <Card className="text-center max-w-2xl mx-auto shadow-xl bg-gray-900 border-gray-800">
              <CardHeader>
                <CardTitle className="text-2xl text-white">¿Listo para comenzar?</CardTitle>
                <CardDescription className="text-lg text-gray-300">
                  La configuración inicial solo toma unos minutos y te ayudará a aprovechar al máximo Nexus
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex flex-col sm:flex-row gap-4 justify-center">
                  <Button 
                    onClick={handleStartOnboarding}
                    size="lg"
                    className="bg-blue-600 hover:bg-blue-700"
                  >
                    <Sparkles className="h-5 w-5 mr-2" />
                    Configurar mi cuenta
                    <ArrowRight className="h-5 w-5 ml-2" />
                  </Button>
                  <Button 
                    variant="outline" 
                    onClick={handleSkipOnboarding}
                    size="lg"
                    className="border-gray-600 text-gray-300 hover:bg-gray-800 hover:text-white"
                  >
                    Omitir por ahora
                  </Button>
                </div>
                <p className="text-sm text-gray-400">
                  Puedes completar la configuración en cualquier momento desde tu perfil
                </p>
              </CardContent>
            </Card>
          </div>
        </div>

        {/* Onboarding Wizard Modal */}
        <OnboardingWizard
          open={showOnboardingWizard}
          onOpenChange={setShowOnboardingWizard}
          onComplete={handleOnboardingComplete}
        />
      </div>
    </AuthGuard>
  )
}