"use client"

import { motion } from "framer-motion"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { 
  IconTrendingUp, 
  IconMoodSmile, 
  IconRefresh, 
  IconBrain,
  IconLanguage,
  IconChartBar,
  IconSparkles
} from "@tabler/icons-react"

const offerings = [
  {
    icon: IconTrendingUp,
    title: "Predicción de Tendencias",
    description: "Analiza patrones en tus documentos para identificar tendencias emergentes y oportunidades de negocio.",
    color: "from-blue-500 to-cyan-500"
  },
  {
    icon: IconMoodSmile,
    title: "Análisis de Sentimientos",
    description: "Evalúa el tono y sentimiento de documentos como contratos, emails y feedback de clientes.",
    color: "from-purple-500 to-pink-500"
  },
  {
    icon: IconRefresh,
    title: "Reciclaje de Contenido",
    description: "Reutiliza y adapta contenido existente para crear nuevos documentos y plantillas inteligentes.",
    color: "from-green-500 to-emerald-500"
  },
  {
    icon: IconBrain,
    title: "Insights Inteligentes",
    description: "Extrae conocimiento valioso de tus documentos con análisis profundo y recomendaciones automáticas.",
    color: "from-orange-500 to-red-500"
  },
  {
    icon: IconLanguage,
    title: "Procesamiento Multiidioma",
    description: "Soporte completo para documentos en múltiples idiomas con traducción automática.",
    color: "from-indigo-500 to-purple-500"
  },
  {
    icon: IconChartBar,
    title: "Análisis Predictivo",
    description: "Predice resultados y tendencias basándose en el análisis histórico de tus documentos.",
    color: "from-teal-500 to-blue-500"
  }
]

export function OfferingsV2() {
  return (
    <section className="relative px-6 py-24 lg:px-8 bg-gray-50 dark:bg-gray-900">
      <div className="mx-auto max-w-7xl">
        {/* Header */}
        <motion.div
          className="text-center mb-16"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          viewport={{ once: true }}
        >
          <Badge variant="secondary" className="mb-4 px-4 py-2">
            <IconSparkles className="mr-2 h-4 w-4" />
            Capacidades Avanzadas
          </Badge>
          <h2 className="text-3xl font-bold tracking-tight text-gray-900 dark:text-white sm:text-4xl lg:text-5xl">
            Funcionalidades que{' '}
            <span className="bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
              transforman
            </span>{' '}
            tu trabajo
          </h2>
          <p className="mt-4 text-lg text-gray-600 dark:text-gray-300 max-w-2xl mx-auto">
            Descubre las capacidades avanzadas de IA que hacen de NexusDocs360 
            la plataforma más completa para gestión documental inteligente.
          </p>
        </motion.div>

        {/* Offerings Grid */}
        <motion.div
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8"
          initial={{ opacity: 0, y: 40 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.2 }}
          viewport={{ once: true }}
        >
          {offerings.map((offering, index) => (
            <motion.div
              key={index}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.1 * index }}
              viewport={{ once: true }}
            >
              <Card className="h-full border-0 shadow-lg hover:shadow-xl transition-all duration-300 hover:scale-105">
                <CardContent className="p-6">
                  <div className="flex items-center space-x-4 mb-4">
                    <div className={`p-3 rounded-lg bg-gradient-to-r ${offering.color} bg-opacity-10`}>
                      <offering.icon className={`h-6 w-6 bg-gradient-to-r ${offering.color} bg-clip-text text-transparent`} />
                    </div>
                    <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                      {offering.title}
                    </h3>
                  </div>
                  <p className="text-gray-600 dark:text-gray-300 leading-relaxed text-sm">
                    {offering.description}
                  </p>
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  )
}