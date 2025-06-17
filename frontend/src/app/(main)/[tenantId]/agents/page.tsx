'use client'

import React from 'react'
import { useParams, useRouter } from 'next/navigation'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import {
  IconSparkles,
  IconSearch,
  IconRobot,
  IconBrain,
  IconArrowRight
} from '@tabler/icons-react'

export default function AgentsPage() {
  const params = useParams()
  const router = useRouter()
  const tenantId = params.tenantId as string


  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-6 py-4 border-b">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <IconRobot className="h-6 w-6 text-blue-500" />
          AI Agents
        </h1>
        <p className="text-muted-foreground text-sm mt-1">
          Descubre cómo nuestros agentes de IA pueden ayudarte a trabajar más eficientemente
        </p>
      </div>

      <div className="flex-1 overflow-auto px-6 py-6">
        {/* Introduction */}
        <Card className="mb-6 bg-gradient-to-r from-blue-50 to-purple-50 border-blue-200">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <IconSparkles className="h-5 w-5 text-yellow-600" />
              Potencia tu productividad con IA
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-muted-foreground mb-4">
              Nuestros agentes de inteligencia artificial están diseñados para automatizar tareas complejas,
              analizar documentos y proporcionar insights valiosos. Cada agente está especializado en un área
              específica para brindarte los mejores resultados.
            </p>
            <Button 
              onClick={() => router.push(`/${tenantId}/search`)}
              className="flex items-center gap-2"
            >
              <IconSearch className="h-4 w-4" />
              Ir a búsqueda con IA
              <IconArrowRight className="h-4 w-4" />
            </Button>
          </CardContent>
        </Card>

        {/* How to Use Section */}
        <Card className="mt-8">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <IconBrain className="h-5 w-5" />
              ¿Cómo usar los agentes?
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 md:grid-cols-3">
              <div className="space-y-2">
                <div className="flex items-center gap-2 font-medium">
                  <div className="w-8 h-8 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center text-sm">
                    1
                  </div>
                  <span>Busca o sube documentos</span>
                </div>
                <p className="text-sm text-muted-foreground ml-10">
                  Usa la búsqueda para encontrar documentos existentes o sube nuevos archivos
                </p>
              </div>
              
              <div className="space-y-2">
                <div className="flex items-center gap-2 font-medium">
                  <div className="w-8 h-8 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center text-sm">
                    2
                  </div>
                  <span>Selecciona un agente</span>
                </div>
                <p className="text-sm text-muted-foreground ml-10">
                  Elige el agente más adecuado para tu tarea específica
                </p>
              </div>
              
              <div className="space-y-2">
                <div className="flex items-center gap-2 font-medium">
                  <div className="w-8 h-8 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center text-sm">
                    3
                  </div>
                  <span>Haz preguntas</span>
                </div>
                <p className="text-sm text-muted-foreground ml-10">
                  Interactúa con el agente para obtener análisis e insights
                </p>
              </div>
            </div>

            <Separator />

            <div className="bg-blue-50 dark:bg-blue-950/20 rounded-lg p-4">
              <h4 className="font-medium mb-2">💡 Tip: Mejora tus resultados</h4>
              <ul className="space-y-1 text-sm text-muted-foreground">
                <li>• Sé específico en tus preguntas para obtener respuestas más precisas</li>
                <li>• Usa los ejemplos sugeridos como punto de partida</li>
                <li>• Combina diferentes agentes para análisis más completos</li>
                <li>• Los agentes recuerdan el contexto de la conversación</li>
              </ul>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}