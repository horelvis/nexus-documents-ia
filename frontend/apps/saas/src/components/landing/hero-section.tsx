"use client"

import { useRouter } from 'next/navigation'
import { useAuth } from '@clerk/nextjs'
import { Button } from "@/components/ui/button"
import { IconFileSearch, IconRocket, IconShieldCheck } from "@tabler/icons-react"

export function HeroSection() {
  const router = useRouter()
  const { isSignedIn } = useAuth()

  const handleGetStarted = () => {
    if (isSignedIn) {
      router.push('/dashboard')
    } else {
      router.push('/auth/sign-up')
    }
  }

  return (
    <section className="relative overflow-hidden bg-gradient-to-br from-blue-50 via-indigo-50 to-purple-50 px-6 py-24 sm:py-32 lg:px-8">
      {/* Background decoration */}
      <div className="absolute inset-0 -z-10 overflow-hidden">
        <svg
          className="absolute left-[max(50%,25rem)] top-0 h-[64rem] w-[128rem] -translate-x-1/2 stroke-gray-200 [mask-image:radial-gradient(64rem_64rem_at_top,white,transparent)]"
          aria-hidden="true"
        >
          <defs>
            <pattern
              id="e813992c-7d03-4cc4-a2bd-151760b470a0"
              width={200}
              height={200}
              x="50%"
              y={-1}
              patternUnits="userSpaceOnUse"
            >
              <path d="M100 200V.5M.5 .5H200" fill="none" />
            </pattern>
          </defs>
          <rect width="100%" height="100%" strokeWidth={0} fill="url(#e813992c-7d03-4cc4-a2bd-151760b470a0)" />
        </svg>
      </div>

      <div className="mx-auto max-w-7xl text-center">
        <div className="mx-auto max-w-4xl">
          <h1 className="text-4xl font-bold tracking-tight text-gray-900 sm:text-6xl">
            Gestiona tus documentos con{' '}
            <span className="text-indigo-600">inteligencia artificial</span>
          </h1>
          <p className="mt-6 text-lg leading-8 text-gray-600 sm:text-xl">
            Nexus Documents 360 es la plataforma de gestión documental que utiliza IA para organizar, buscar y analizar 
            tus documentos de manera inteligente. Sube, busca semánticamente y obtén insights automáticos.
          </p>
        </div>

        <div className="mt-10 flex items-center justify-center gap-x-6">
          <Button 
            onClick={handleGetStarted}
            size="lg"
            className="px-8 py-3 text-lg"
          >
            <IconRocket className="mr-2 h-5 w-5" />
            {isSignedIn ? 'Ir al Dashboard' : 'Comenzar Gratis'}
          </Button>
          <Button 
            variant="outline" 
            size="lg"
            onClick={() => {
              const featuresElement = document.getElementById('features')
              featuresElement?.scrollIntoView({ behavior: 'smooth' })
            }}
            className="px-8 py-3 text-lg"
          >
            Ver características
          </Button>
        </div>

        {/* Feature highlights */}
        <div className="mt-16 grid grid-cols-1 gap-8 sm:grid-cols-3">
          <div className="flex flex-col items-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-indigo-100">
              <IconFileSearch className="h-6 w-6 text-indigo-600" />
            </div>
            <h3 className="mt-4 text-lg font-semibold text-gray-900">Búsqueda Semántica</h3>
            <p className="mt-2 text-sm text-gray-600">
              Encuentra documentos por contenido, no solo por nombre
            </p>
          </div>
          <div className="flex flex-col items-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-green-100">
              <IconShieldCheck className="h-6 w-6 text-green-600" />
            </div>
            <h3 className="mt-4 text-lg font-semibold text-gray-900">Seguro y Privado</h3>
            <p className="mt-2 text-sm text-gray-600">
              Tus documentos están protegidos con encriptación de nivel empresarial
            </p>
          </div>
          <div className="flex flex-col items-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-purple-100">
              <IconRocket className="h-6 w-6 text-purple-600" />
            </div>
            <h3 className="mt-4 text-lg font-semibold text-gray-900">IA Integrada</h3>
            <p className="mt-2 text-sm text-gray-600">
              Generación automática de resúmenes y análisis de contenido
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}
