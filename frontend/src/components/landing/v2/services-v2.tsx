"use client"

import { motion } from "framer-motion"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { 
  IconTrendingUp, 
  IconZap, 
  IconShieldCheck, 
  IconUsers,
  IconSparkles
} from "@tabler/icons-react"

const services = [
  {
    icon: IconTrendingUp,
    title: "Mejora tu negocio",
    description: "Optimiza procesos documentales y reduce el tiempo de búsqueda en un 85% con IA avanzada.",
    color: "from-blue-500 to-cyan-500",
    bgColor: "from-blue-50 to-cyan-50 dark:from-blue-900/20 dark:to-cyan-900/20"
  },
  {
    icon: IconZap,
    title: "Automatización veloz",
    description: "Procesamiento automático de documentos con análisis instantáneo y clasificación inteligente.",
    color: "from-purple-500 to-pink-500",
    bgColor: "from-purple-50 to-pink-50 dark:from-purple-900/20 dark:to-pink-900/20"
  },
  {
    icon: IconShieldCheck,
    title: "Seguro y efectivo",
    description: "Cumplimiento normativo garantizado con encriptación de grado militar y auditoría completa.",
    color: "from-green-500 to-emerald-500",
    bgColor: "from-green-50 to-emerald-50 dark:from-green-900/20 dark:to-emerald-900/20"
  },
  {
    icon: IconUsers,
    title: "Controla tu equipo",
    description: "Gestión granular de permisos y colaboración en tiempo real con control de versiones.",
    color: "from-orange-500 to-red-500",
    bgColor: "from-orange-50 to-red-50 dark:from-orange-900/20 dark:to-red-900/20"
  }
]

export function ServicesV2() {
  return (
    <section className="relative px-6 py-24 lg:px-8">
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
            Nuestros Servicios
          </Badge>
          <h2 className="text-3xl font-bold tracking-tight text-gray-900 dark:text-white sm:text-4xl lg:text-5xl">
            Exploramos nuestros{' '}
            <span className="bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
              servicios
            </span>
          </h2>
          <p className="mt-4 text-lg text-gray-600 dark:text-gray-300 max-w-2xl mx-auto">
            Proporcionamos los mejores servicios para nuestros clientes con la más alta 
            calidad y tecnología de vanguardia en gestión documental.
          </p>
        </motion.div>

        {/* Services Grid */}
        <motion.div
          className="grid grid-cols-1 md:grid-cols-2 gap-8"
          initial={{ opacity: 0, y: 40 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.2 }}
          viewport={{ once: true }}
        >
          {services.map((service, index) => (
            <motion.div
              key={index}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.1 * index }}
              viewport={{ once: true }}
            >
              <Card className="h-full border-0 shadow-lg hover:shadow-xl transition-all duration-300 hover:scale-105">
                <CardContent className="p-8">
                  <div className={`inline-flex p-4 rounded-lg bg-gradient-to-r ${service.bgColor} mb-6`}>
                    <service.icon className={`h-8 w-8 bg-gradient-to-r ${service.color} bg-clip-text text-transparent`} />
                  </div>
                  <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-4">
                    {service.title}
                  </h3>
                  <p className="text-gray-600 dark:text-gray-300 leading-relaxed">
                    {service.description}
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