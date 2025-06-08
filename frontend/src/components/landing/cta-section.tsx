"use client"

import { useRouter } from 'next/navigation'
import { useAuth } from '@clerk/nextjs'
import { Button } from "@/components/ui/button"
import { IconArrowRight, IconCheck } from "@tabler/icons-react"

const benefits = [
  'Configuración en menos de 5 minutos',
  'Sin límite de almacenamiento en plan premium',
  'Soporte 24/7 especializado',
  'Integraciones con +100 herramientas'
]

export function CTASection() {
  const router = useRouter()
  const { isSignedIn } = useAuth()

  const handleGetStarted = () => {
    if (isSignedIn) {
      router.push('/dashboard')
    } else {
      router.push('/pricing')
    }
  }

  return (
    <section className="bg-indigo-600">
      <div className="px-6 py-24 sm:px-6 sm:py-32 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-bold tracking-tight text-white sm:text-4xl">
            ¿Listo para revolucionar tu gestión documental?
          </h2>
          <p className="mx-auto mt-6 max-w-xl text-lg leading-8 text-indigo-200">
            Únete a miles de empresas que ya utilizan Nexus para optimizar su flujo de trabajo documental.
          </p>
          
          <div className="mt-8 flex flex-col items-center space-y-4">
            <ul className="space-y-2 text-sm text-indigo-200">
              {benefits.map((benefit) => (
                <li key={benefit} className="flex items-center">
                  <IconCheck className="mr-2 h-4 w-4 text-indigo-300" />
                  {benefit}
                </li>
              ))}
            </ul>
          </div>

          <div className="mt-10 flex items-center justify-center gap-x-6">
            <Button 
              onClick={handleGetStarted}
              size="lg"
              variant="secondary"
              className="bg-white text-indigo-600 hover:bg-gray-50 px-8 py-3 text-lg"
            >
              {isSignedIn ? 'Ir al Dashboard' : 'Comenzar Gratis'}
              <IconArrowRight className="ml-2 h-5 w-5" />
            </Button>
            <Button 
              variant="ghost"
              size="lg"
              onClick={() => router.push('/auth/sign-in')}
              className="text-white hover:text-indigo-200 px-8 py-3 text-lg"
            >
              {isSignedIn ? 'Dashboard' : 'Iniciar Sesión'}
            </Button>
          </div>

          <p className="mt-6 text-xs text-indigo-300">
            Plan gratuito disponible. Sin tarjeta de crédito requerida.
          </p>
        </div>
      </div>
    </section>
  )
}