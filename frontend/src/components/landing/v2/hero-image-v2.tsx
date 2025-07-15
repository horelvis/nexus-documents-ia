"use client"

import { useEffect, useState } from "react"
import { motion } from "framer-motion"
import Image from "next/image"

export function HeroImageV2() {
  const [scrollY, setScrollY] = useState(0)

  useEffect(() => {
    const handleScroll = () => setScrollY(window.scrollY)
    window.addEventListener('scroll', handleScroll)
    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

  return (
    <section className="relative px-6 py-16 lg:px-8">
      <div className="mx-auto max-w-7xl">
        <motion.div
          className="relative mx-auto max-w-5xl"
          initial={{ opacity: 0, y: 60 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.2 }}
        >
          {/* Main Dashboard Image */}
          <motion.div
            className="relative transform-gpu"
            style={{
              transform: `perspective(1000px) rotateX(${scrollY * 0.01}deg) rotateY(${scrollY * 0.005}deg)`,
            }}
            whileHover={{ 
              scale: 1.02,
              rotateX: 5,
              rotateY: 5,
              transition: { duration: 0.3 }
            }}
          >
            <div className="relative overflow-hidden rounded-2xl bg-white dark:bg-gray-800 shadow-2xl border border-gray-200 dark:border-gray-700">
              <div className="absolute inset-0 bg-gradient-to-br from-blue-50 to-indigo-100 dark:from-blue-900/20 dark:to-indigo-900/20"></div>
              
              {/* Mock Dashboard Content */}
              <div className="relative p-8">
                {/* Header */}
                <div className="flex items-center justify-between mb-6">
                  <div className="flex items-center space-x-4">
                    <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-lg flex items-center justify-center">
                      <span className="text-white font-bold text-sm">N</span>
                    </div>
                    <h3 className="text-xl font-semibold text-gray-900 dark:text-white">
                      NexusDocs360
                    </h3>
                  </div>
                  <div className="flex items-center space-x-2">
                    <div className="w-2 h-2 bg-green-500 rounded-full"></div>
                    <div className="w-2 h-2 bg-yellow-500 rounded-full"></div>
                    <div className="w-2 h-2 bg-red-500 rounded-full"></div>
                  </div>
                </div>

                {/* Stats Cards */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
                  <div className="bg-gradient-to-br from-blue-50 to-blue-100 dark:from-blue-900/30 dark:to-blue-800/30 p-4 rounded-lg">
                    <div className="text-2xl font-bold text-blue-600 dark:text-blue-400">1,247</div>
                    <div className="text-sm text-gray-600 dark:text-gray-300">Documentos</div>
                  </div>
                  <div className="bg-gradient-to-br from-green-50 to-green-100 dark:from-green-900/30 dark:to-green-800/30 p-4 rounded-lg">
                    <div className="text-2xl font-bold text-green-600 dark:text-green-400">98%</div>
                    <div className="text-sm text-gray-600 dark:text-gray-300">Precisión IA</div>
                  </div>
                  <div className="bg-gradient-to-br from-purple-50 to-purple-100 dark:from-purple-900/30 dark:to-purple-800/30 p-4 rounded-lg">
                    <div className="text-2xl font-bold text-purple-600 dark:text-purple-400">2.3s</div>
                    <div className="text-sm text-gray-600 dark:text-gray-300">Tiempo búsqueda</div>
                  </div>
                </div>

                {/* Document List */}
                <div className="space-y-3">
                  <div className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
                    Documentos Recientes
                  </div>
                  {[
                    { name: "Contrato_Servicios_2024.pdf", type: "PDF", size: "2.4 MB", confidence: "95%" },
                    { name: "Informe_Financiero_Q1.docx", type: "Word", size: "1.8 MB", confidence: "92%" },
                    { name: "Propuesta_Proyecto_Alpha.pptx", type: "PowerPoint", size: "5.2 MB", confidence: "98%" },
                  ].map((doc, index) => (
                    <div key={index} className="flex items-center justify-between p-3 bg-white dark:bg-gray-700 rounded-lg border border-gray-200 dark:border-gray-600">
                      <div className="flex items-center space-x-3">
                        <div className="w-8 h-8 bg-gradient-to-br from-gray-100 to-gray-200 dark:from-gray-600 dark:to-gray-700 rounded flex items-center justify-center">
                          <span className="text-xs font-medium text-gray-600 dark:text-gray-300">
                            {doc.type === "PDF" ? "PDF" : doc.type === "Word" ? "DOC" : "PPT"}
                          </span>
                        </div>
                        <div>
                          <div className="text-sm font-medium text-gray-900 dark:text-white">{doc.name}</div>
                          <div className="text-xs text-gray-500 dark:text-gray-400">{doc.size}</div>
                        </div>
                      </div>
                      <div className="text-xs text-green-600 dark:text-green-400 font-medium">
                        {doc.confidence}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </motion.div>

          {/* Supporting Elements */}
          <motion.div
            className="absolute -left-16 top-16 hidden lg:block"
            initial={{ opacity: 0, x: -100 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.8, delay: 0.4 }}
          >
            <div className="w-48 h-32 bg-gradient-to-br from-blue-100 to-blue-200 dark:from-blue-900/40 dark:to-blue-800/40 rounded-lg p-4 shadow-lg">
              <div className="text-sm font-medium text-blue-800 dark:text-blue-200 mb-2">
                Análisis IA
              </div>
              <div className="text-xs text-blue-600 dark:text-blue-300">
                Extrayendo insights automáticamente...
              </div>
              <div className="mt-2 w-full bg-blue-200 dark:bg-blue-700 rounded-full h-2">
                <div className="bg-blue-600 dark:bg-blue-400 h-2 rounded-full w-3/4"></div>
              </div>
            </div>
          </motion.div>

          <motion.div
            className="absolute -right-16 top-32 hidden lg:block"
            initial={{ opacity: 0, x: 100 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.8, delay: 0.6 }}
          >
            <div className="w-48 h-32 bg-gradient-to-br from-green-100 to-green-200 dark:from-green-900/40 dark:to-green-800/40 rounded-lg p-4 shadow-lg">
              <div className="text-sm font-medium text-green-800 dark:text-green-200 mb-2">
                Búsqueda Semántica
              </div>
              <div className="text-xs text-green-600 dark:text-green-300">
                Encontrando documentos relevantes...
              </div>
              <div className="mt-2 space-y-1">
                <div className="w-full bg-green-200 dark:bg-green-700 rounded h-1"></div>
                <div className="w-3/4 bg-green-200 dark:bg-green-700 rounded h-1"></div>
                <div className="w-1/2 bg-green-200 dark:bg-green-700 rounded h-1"></div>
              </div>
            </div>
          </motion.div>
        </motion.div>
      </div>
    </section>
  )
}