"use client"

import { useRouter } from 'next/navigation'
import { useAuth } from '@clerk/nextjs'
import { motion } from 'framer-motion'
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { 
  IconFileSearch, 
  IconRocket, 
  IconShieldCheck, 
  IconBrandGithub,
  IconBrandLinkedin,
  IconBrandTwitter,
  IconBrandFacebook,
  IconSparkles
} from "@tabler/icons-react"

export function HeroV2() {
  const router = useRouter()
  const { isSignedIn } = useAuth()

  const handleGetStarted = () => {
    if (isSignedIn) {
      router.push('/dashboard')
    } else {
      router.push('/auth/sign-up')
    }
  }

  const handleLearnMore = () => {
    const featuresElement = document.getElementById('features')
    featuresElement?.scrollIntoView({ behavior: 'smooth' })
  }

  return (
    <section className="relative px-6 py-24 sm:py-32 lg:px-8">
      <div className="mx-auto max-w-7xl">
        <div className="mx-auto max-w-4xl text-center">
          
          {/* NEW Badge */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
          >
            <Badge variant="secondary" className="mb-8 px-4 py-2 text-sm font-medium">
              <IconSparkles className="mr-2 h-4 w-4" />
              Nuevo: Agentes de IA para análisis documental
            </Badge>
          </motion.div>

          {/* Main Headline */}
          <motion.h1 
            className="text-4xl font-bold tracking-tight text-gray-900 dark:text-white sm:text-6xl lg:text-7xl"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.1 }}
          >
            Revoluciona tu{' '}
            <span className="bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">
              gestión documental
            </span>{' '}
            con{' '}
            <span className="bg-gradient-to-r from-purple-600 to-pink-600 bg-clip-text text-transparent">
              IA
            </span>
          </motion.h1>

          {/* Description */}
          <motion.p 
            className="mt-6 text-lg leading-8 text-gray-600 dark:text-gray-300 sm:text-xl"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.2 }}
          >
            Eleva tu gestión documental con herramientas de IA avanzadas. NexusDocs360 es una plataforma
            poderosa que utiliza inteligencia artificial para{' '}
            <span className="hidden sm:inline">
              organizar, analizar y extraer insights de tus documentos.
            </span>
            <span className="sm:hidden">
              gestionar tus documentos inteligentemente.
            </span>
          </motion.p>

          {/* CTA Buttons */}
          <motion.div 
            className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-4"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.3 }}
          >
            <Button 
              onClick={handleGetStarted}
              size="lg"
              className="px-8 py-3 text-lg bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white border-0 shadow-lg"
            >
              <IconRocket className="mr-2 h-5 w-5" />
              {isSignedIn ? 'Ir al Dashboard' : 'Comenzar Gratis'}
            </Button>
            <Button 
              variant="outline" 
              size="lg"
              onClick={handleLearnMore}
              className="px-8 py-3 text-lg border-gray-300 hover:bg-gray-50 dark:border-gray-600 dark:hover:bg-gray-800"
            >
              Cómo funciona
            </Button>
          </motion.div>

          {/* Trust Indicators */}
          <motion.div 
            className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-6 text-sm text-gray-600 dark:text-gray-400"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.4 }}
          >
            <div className="flex items-center">
              <IconShieldCheck className="mr-2 h-4 w-4 text-green-500" />
              Prueba gratuita de 14 días
            </div>
            <div className="flex items-center">
              <IconFileSearch className="mr-2 h-4 w-4 text-blue-500" />
              Sin tarjeta de crédito requerida
            </div>
          </motion.div>

          {/* Social Icons */}
          <motion.div 
            className="mt-12 flex items-center justify-center gap-6"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.5 }}
          >
            {[
              { icon: IconBrandGithub, href: "#", label: "GitHub" },
              { icon: IconBrandLinkedin, href: "#", label: "LinkedIn" },
              { icon: IconBrandTwitter, href: "#", label: "Twitter" },
              { icon: IconBrandFacebook, href: "#", label: "Facebook" }
            ].map((social, index) => (
              <motion.a
                key={social.label}
                href={social.href}
                className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.95 }}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.6 + index * 0.1 }}
              >
                <span className="sr-only">{social.label}</span>
                <social.icon className="h-6 w-6" />
              </motion.a>
            ))}
          </motion.div>
        </div>
      </div>
    </section>
  )
}