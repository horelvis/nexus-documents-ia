"use client"

import { motion } from "framer-motion"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { IconStar, IconSparkles } from "@tabler/icons-react"

const testimonials = [
  {
    name: "Ana García",
    role: "Directora de Operaciones",
    company: "TechCorp",
    content: "NexusDocs360 transformó completamente nuestra gestión documental. La búsqueda semántica nos permite encontrar cualquier documento en segundos, no importa cuán complejo sea.",
    rating: 5
  },
  {
    name: "Carlos Mendoza",
    role: "CEO",
    company: "StartupLegal",
    content: "Los agentes IA para análisis legal son increíbles. Ahora podemos revisar contratos en minutos en lugar de horas. Es como tener un asistente jurídico 24/7.",
    rating: 5
  },
  {
    name: "María López",
    role: "Gerente de Finanzas",
    company: "FinanceGlobal",
    content: "La automatización de informes financieros nos ahorra 20 horas a la semana. La precisión del análisis de IA es superior a cualquier herramienta que hayamos usado.",
    rating: 5
  },
  {
    name: "Roberto Silva",
    role: "Director de IT",
    company: "InnovateTech",
    content: "La seguridad y el cumplimiento normativo son excepcionales. Finalmente tenemos una solución que combina potencia de IA con la seguridad que necesitamos.",
    rating: 5
  }
]

export function TestimonialV2() {
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
            Testimonios
          </Badge>
          <h2 className="text-3xl font-bold tracking-tight text-gray-900 dark:text-white sm:text-4xl lg:text-5xl">
            Lo que dicen nuestros{' '}
            <span className="bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
              clientes
            </span>
          </h2>
          <p className="mt-4 text-lg text-gray-600 dark:text-gray-300 max-w-2xl mx-auto">
            Descubre cómo organizaciones de todos los tamaños están transformando 
            su gestión documental con NexusDocs360.
          </p>
        </motion.div>

        {/* Testimonials Grid */}
        <motion.div
          className="grid grid-cols-1 md:grid-cols-2 gap-8"
          initial={{ opacity: 0, y: 40 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.2 }}
          viewport={{ once: true }}
        >
          {testimonials.map((testimonial, index) => (
            <motion.div
              key={index}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.1 * index }}
              viewport={{ once: true }}
            >
              <Card className="h-full border-0 shadow-lg hover:shadow-xl transition-all duration-300">
                <CardContent className="p-8">
                  {/* Rating */}
                  <div className="flex items-center space-x-1 mb-4">
                    {[...Array(testimonial.rating)].map((_, i) => (
                      <IconStar key={i} className="h-5 w-5 text-yellow-400 fill-current" />
                    ))}
                  </div>
                  
                  {/* Content */}
                  <blockquote className="text-gray-600 dark:text-gray-300 leading-relaxed mb-6">
                    "{testimonial.content}"
                  </blockquote>
                  
                  {/* Author */}
                  <div className="flex items-center space-x-4">
                    <Avatar>
                      <AvatarFallback className="bg-gradient-to-r from-blue-500 to-purple-500 text-white">
                        {testimonial.name.split(' ').map(n => n[0]).join('')}
                      </AvatarFallback>
                    </Avatar>
                    <div>
                      <div className="font-semibold text-gray-900 dark:text-white">
                        {testimonial.name}
                      </div>
                      <div className="text-sm text-gray-600 dark:text-gray-400">
                        {testimonial.role} • {testimonial.company}
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  )
}