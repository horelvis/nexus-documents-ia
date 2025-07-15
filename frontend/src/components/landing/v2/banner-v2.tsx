"use client"

import { motion } from "framer-motion"
import { useRouter } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import { Button } from "@/components/ui/button"
import { IconRocket, IconArrowRight } from "@tabler/icons-react"

export function BannerV2() {
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
    <section className="relative px-6 py-24 lg:px-8">
      <div className="mx-auto max-w-7xl">
        <motion.div
          className="relative overflow-hidden bg-gradient-to-r from-blue-600 via-purple-600 to-indigo-600 rounded-3xl shadow-2xl"
          initial={{ opacity: 0, y: 40 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8 }}
          viewport={{ once: true }}
        >
          {/* Background decoration */}
          <div className="absolute inset-0 bg-gradient-to-r from-blue-600/90 via-purple-600/90 to-indigo-600/90"></div>
          <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNDAiIGhlaWdodD0iNDAiIHZpZXdCb3g9IjAgMCA0MCA0MCIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPGNpcmNsZSBjeD0iMjAiIGN5PSIyMCIgcj0iMiIgZmlsbD0iI2ZmZmZmZiIgZmlsbC1vcGFjaXR5PSIwLjEiLz4KPC9zdmc+')] opacity-20"></div>
          
          <div className="relative px-8 py-16 text-center">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6 }}
              viewport={{ once: true }}
            >
              <h2 className="text-3xl font-bold text-white sm:text-4xl lg:text-5xl mb-6">
                ¿Listo para revolucionar tu
                <br />
                <span className="bg-gradient-to-r from-yellow-200 to-orange-200 bg-clip-text text-transparent">
                  gestión documental?
                </span>
              </h2>
              <p className="text-xl text-blue-100 mb-8 max-w-2xl mx-auto">
                Únete a miles de organizaciones que ya están transformando su forma de trabajar 
                con documentos usando la potencia de la inteligencia artificial.
              </p>
            </motion.div>

            <motion.div
              className="flex flex-col sm:flex-row items-center justify-center gap-4"
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.2 }}
              viewport={{ once: true }}
            >
              <Button
                size="lg"
                onClick={handleGetStarted}
                className="bg-white text-blue-600 hover:bg-blue-50 px-8 py-4 text-lg font-semibold border-0 shadow-lg hover:shadow-xl transition-all duration-300"
              >
                <IconRocket className="mr-2 h-5 w-5" />
                {isSignedIn ? 'Ir al Dashboard' : 'Comenzar Gratis'}
              </Button>
              <Button
                variant="outline"
                size="lg"
                onClick={() => router.push('/pricing')}
                className="border-white text-white hover:bg-white hover:text-blue-600 px-8 py-4 text-lg font-semibold transition-all duration-300"
              >
                Ver Planes
                <IconArrowRight className="ml-2 h-5 w-5" />
              </Button>
            </motion.div>

            <motion.div
              className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-6 text-blue-100"
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.4 }}
              viewport={{ once: true }}
            >
              <div className="flex items-center text-sm">
                <IconRocket className="mr-2 h-4 w-4" />
                Configuración en 2 minutos
              </div>
              <div className="flex items-center text-sm">
                <IconRocket className="mr-2 h-4 w-4" />
                Soporte 24/7
              </div>
              <div className="flex items-center text-sm">
                <IconRocket className="mr-2 h-4 w-4" />
                Garantía de satisfacción
              </div>
            </motion.div>
          </div>
        </motion.div>
      </div>
    </section>
  )
}