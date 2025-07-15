"use client"

import { motion } from "framer-motion"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import { 
  IconFileText, 
  IconFileSpreadsheet, 
  IconPresentation, 
  IconPhoto,
  IconCode,
  IconFileDatabase,
  IconSparkles
} from "@tabler/icons-react"

const supportedTools = [
  {
    name: "Documentos PDF",
    icon: IconFileText,
    description: "Análisis completo de PDFs con extracción de texto y metadatos",
    color: "from-red-500 to-pink-500"
  },
  {
    name: "Hojas de Cálculo",
    icon: IconFileSpreadsheet,
    description: "Procesamiento de Excel y Google Sheets con análisis de datos",
    color: "from-green-500 to-emerald-500"
  },
  {
    name: "Presentaciones",
    icon: IconPresentation,
    description: "Extracción de contenido de PowerPoint y Google Slides",
    color: "from-orange-500 to-red-500"
  },
  {
    name: "Imágenes",
    icon: IconPhoto,
    description: "OCR avanzado y reconocimiento de texto en imágenes",
    color: "from-purple-500 to-pink-500"
  },
  {
    name: "Código Fuente",
    icon: IconCode,
    description: "Análisis de documentación técnica y código fuente",
    color: "from-blue-500 to-cyan-500"
  },
  {
    name: "Bases de Datos",
    icon: IconFileDatabase,
    description: "Integración con bases de datos y sistemas documentales",
    color: "from-indigo-500 to-purple-500"
  }
]

export function ToolsV2() {
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
            Formatos Compatibles
          </Badge>
          <h2 className="text-3xl font-bold tracking-tight text-gray-900 dark:text-white sm:text-4xl lg:text-5xl">
            Trabaja con todos tus{' '}
            <span className="bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
              formatos favoritos
            </span>
          </h2>
          <p className="mt-4 text-lg text-gray-600 dark:text-gray-300 max-w-2xl mx-auto">
            NexusDocs360 soporta una amplia gama de formatos de documentos, 
            desde PDFs hasta bases de datos, todo con análisis IA integrado.
          </p>
        </motion.div>

        {/* Tools Grid */}
        <motion.div
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8"
          initial={{ opacity: 0, y: 40 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.2 }}
          viewport={{ once: true }}
        >
          {supportedTools.map((tool, index) => (
            <motion.div
              key={index}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.1 * index }}
              viewport={{ once: true }}
            >
              <Card className="h-full border-0 shadow-lg hover:shadow-xl transition-all duration-300 hover:scale-105">
                <CardContent className="p-6 text-center">
                  <div className={`inline-flex p-4 rounded-full bg-gradient-to-r ${tool.color} bg-opacity-10 mb-4`}>
                    <tool.icon className={`h-8 w-8 bg-gradient-to-r ${tool.color} bg-clip-text text-transparent`} />
                  </div>
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
                    {tool.name}
                  </h3>
                  <p className="text-gray-600 dark:text-gray-300 text-sm leading-relaxed">
                    {tool.description}
                  </p>
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </motion.div>

        {/* Stats */}
        <motion.div
          className="mt-16 text-center"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.4 }}
          viewport={{ once: true }}
        >
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div className="space-y-2">
              <div className="text-3xl font-bold bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
                50+
              </div>
              <div className="text-sm text-gray-600 dark:text-gray-300">
                Formatos soportados
              </div>
            </div>
            <div className="space-y-2">
              <div className="text-3xl font-bold bg-gradient-to-r from-green-600 to-blue-600 bg-clip-text text-transparent">
                99.9%
              </div>
              <div className="text-sm text-gray-600 dark:text-gray-300">
                Precisión en OCR
              </div>
            </div>
            <div className="space-y-2">
              <div className="text-3xl font-bold bg-gradient-to-r from-purple-600 to-pink-600 bg-clip-text text-transparent">
                &lt;1s
              </div>
              <div className="text-sm text-gray-600 dark:text-gray-300">
                Tiempo de procesamiento
              </div>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  )
}