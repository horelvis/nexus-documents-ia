"use client"

import { motion } from "framer-motion"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import { 
  IconFileSearch, 
  IconRobot, 
  IconShieldCheck, 
  IconBrandOpenai,
  IconAnalyze,
  IconCloudUpload,
  IconUsers,
  IconChartBar,
  IconSparkles,
  IconBrain,
  IconLanguage,
  IconDocument
} from "@tabler/icons-react"

const features = [
  {
    icon: IconFileSearch,
    title: "Búsqueda Semántica Inteligente",
    description: "Encuentra documentos por significado, no solo por palabras clave. Nuestra IA entiende el contexto y contenido.",
    color: "from-blue-500 to-cyan-500",
    bgColor: "from-blue-50 to-cyan-50 dark:from-blue-900/20 dark:to-cyan-900/20"
  },
  {
    icon: IconRobot,
    title: "Agentes IA Especializados",
    description: "Agentes dedicados para análisis contractual, financiero, legal y resúmenes automáticos de documentos.",
    color: "from-purple-500 to-pink-500",
    bgColor: "from-purple-50 to-pink-50 dark:from-purple-900/20 dark:to-pink-900/20"
  },
  {
    icon: IconAnalyze,
    title: "Análisis Automático de Contenido",
    description: "Extracción automática de entidades, fechas clave, términos importantes y análisis de sentimientos.",
    color: "from-green-500 to-emerald-500",
    bgColor: "from-green-50 to-emerald-50 dark:from-green-900/20 dark:to-emerald-900/20"
  },
  {
    icon: IconShieldCheck,
    title: "Firmas Digitales Seguras",
    description: "Integración con proveedores de firma digital y workflows de aprobación multi-nivel.",
    color: "from-orange-500 to-red-500",
    bgColor: "from-orange-50 to-red-50 dark:from-orange-900/20 dark:to-red-900/20"
  }
]

const featureBadges = [
  "Análisis Inteligente", "Creación de Contenido", "Engagement de Usuarios",
  "Gestión Documental", "Monitoreo de Marca", "Reportes de Rendimiento",
  "Programación de Contenido", "Feedback de Usuarios", "Integraciones Personalizadas",
  "Optimización de Contenido", "Búsqueda Semántica", "Agentes IA", "Firma Digital"
]

export function FeaturesV2() {
  return (
    <section id="features" className="relative px-6 py-24 lg:px-8">
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
            Características Avanzadas
          </Badge>
          <h2 className="text-3xl font-bold tracking-tight text-gray-900 dark:text-white sm:text-4xl lg:text-5xl">
            Potencia tu gestión documental con{' '}
            <span className="bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
              IA de vanguardia
            </span>
          </h2>
          <p className="mt-4 text-lg text-gray-600 dark:text-gray-300 max-w-2xl mx-auto">
            Descubre cómo nuestras herramientas de inteligencia artificial transforman 
            la manera en que organizas, buscas y analizas tus documentos.
          </p>
        </motion.div>

        {/* Feature Badges Marquee */}
        <motion.div
          className="relative overflow-hidden mb-16"
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          transition={{ duration: 0.6, delay: 0.2 }}
          viewport={{ once: true }}
        >
          <div className="flex animate-marquee space-x-4">
            {[...featureBadges, ...featureBadges].map((badge, index) => (
              <Badge
                key={index}
                variant="outline"
                className="whitespace-nowrap px-4 py-2 text-sm font-medium"
              >
                {badge}
              </Badge>
            ))}
          </div>
        </motion.div>

        {/* Main Features Grid */}
        <motion.div
          className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-16"
          initial={{ opacity: 0, y: 40 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.3 }}
          viewport={{ once: true }}
        >
          {features.map((feature, index) => (
            <motion.div
              key={index}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.1 * index }}
              viewport={{ once: true }}
            >
              <Card className="h-full border-0 shadow-lg hover:shadow-xl transition-shadow duration-300">
                <CardContent className="p-8">
                  <div className={`inline-flex p-3 rounded-lg bg-gradient-to-r ${feature.bgColor} mb-4`}>
                    <feature.icon className={`h-8 w-8 bg-gradient-to-r ${feature.color} bg-clip-text text-transparent`} />
                  </div>
                  <h3 className="text-xl font-semibold text-gray-900 dark:text-white mb-3">
                    {feature.title}
                  </h3>
                  <p className="text-gray-600 dark:text-gray-300 leading-relaxed">
                    {feature.description}
                  </p>
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </motion.div>

        {/* Statistics */}
        <motion.div
          className="grid grid-cols-1 md:grid-cols-3 gap-8 text-center"
          initial={{ opacity: 0, y: 40 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.4 }}
          viewport={{ once: true }}
        >
          <div className="space-y-2">
            <div className="text-4xl font-bold bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
              10,000+
            </div>
            <div className="text-sm text-gray-600 dark:text-gray-300">
              Equipos confían en nosotros
            </div>
          </div>
          <div className="space-y-2">
            <div className="text-4xl font-bold bg-gradient-to-r from-green-600 to-blue-600 bg-clip-text text-transparent">
              5M+
            </div>
            <div className="text-sm text-gray-600 dark:text-gray-300">
              Documentos procesados
            </div>
          </div>
          <div className="space-y-2">
            <div className="text-4xl font-bold bg-gradient-to-r from-purple-600 to-pink-600 bg-clip-text text-transparent">
              98%
            </div>
            <div className="text-sm text-gray-600 dark:text-gray-300">
              Precisión en análisis
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  )
}