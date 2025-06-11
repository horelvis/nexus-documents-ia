'use client'

import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { MessageCircle, Activity, FileSignature, FileText, Bot, Zap } from 'lucide-react'
import { Agent, useAgentsService } from '@/lib/services/agents.service'
import { DigitalSignatureAssistant } from '@/components/agents/digital-signature-assistant'
import { AgentHealthCheck } from '@/components/agents/agent-health-check'
import { useNotifications } from '@/contexts/notifications-context'

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null)
  const [activeTab, setActiveTab] = useState('library')
  
  const agentsService = useAgentsService()
  const { addNotification } = useNotifications()

  useEffect(() => {
    loadAgents()
  }, [])

  const loadAgents = async () => {
    try {
      setIsLoading(true)
      console.log('🔄 Loading agents...')
      const response = await agentsService.getAgents()
      
      console.log('📊 Agents response:', response)
      
      if (response.error) {
        console.error('❌ Error loading agents:', response.error)
        setAgents([])
        addNotification({
          type: 'error',
          title: 'Error cargando agentes',
          message: response.error
        })
      } else {
        // La respuesta puede ser { agents: [...], total: ... } o directamente un array
        const agentsData = response.data?.agents || response.data || []
        console.log('✅ Loaded agents:', agentsData)
        setAgents(agentsData)
        
        if (agentsData.length === 0) {
          console.log('ℹ️ No agents found for tenant')
        }
      }
    } catch (error) {
      console.error('❌ Error loading agents:', error)
      setAgents([])
      addNotification({
        type: 'error',
        title: 'Error de conexión',
        message: 'No se pudo conectar con el servicio de agentes'
      })
    } finally {
      setIsLoading(false)
    }
  }


  const getAgentIcon = (type: string) => {
    switch (type) {
      case 'digital_signature':
        return <FileSignature className="h-5 w-5" />
      case 'document_analyzer':
        return <FileText className="h-5 w-5" />
      case 'rag_assistant':
        return <Bot className="h-5 w-5" />
      default:
        return <MessageCircle className="h-5 w-5" />
    }
  }

  const getAgentBadgeColor = (type: string) => {
    switch (type) {
      case 'digital_signature':
        return 'bg-blue-100 text-blue-800'
      case 'document_analyzer':
        return 'bg-green-100 text-green-800'
      case 'rag_assistant':
        return 'bg-purple-100 text-purple-800'
      default:
        return 'bg-gray-100 text-gray-800'
    }
  }

  if (selectedAgent) {
    if (selectedAgent.type === 'digital_signature') {
      return (
        <DigitalSignatureAssistant 
          agent={selectedAgent}
          onBack={() => setSelectedAgent(null)}
        />
      )
    }
    
    // For other agent types, show a generic interface
    return (
      <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6">
        <div className="px-4 lg:px-6">
          <div className="flex items-center gap-4 mb-6">
            <Button variant="outline" onClick={() => setSelectedAgent(null)}>
              ← Volver
            </Button>
            <div>
              <h1 className="text-3xl font-bold">{selectedAgent.name}</h1>
              <p className="text-muted-foreground">{selectedAgent.description}</p>
            </div>
          </div>
          
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-center py-12">
                <p className="text-muted-foreground">
                  Interfaz para {selectedAgent.name} en desarrollo...
                </p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6">
      <div className="px-4 lg:px-6">
        <div className="mb-8">
          <h1 className="text-3xl font-bold mb-2">AI Agent Library</h1>
          <p className="text-muted-foreground">
            Gestiona y despliega agentes de IA para procesamiento de documentos y automatización
          </p>
        </div>

        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="library">Biblioteca de Agentes</TabsTrigger>
            <TabsTrigger value="test">Pruebas de Integración</TabsTrigger>
            <TabsTrigger value="health">Estado del Sistema</TabsTrigger>
          </TabsList>

          <TabsContent value="library" className="space-y-6">
            {isLoading ? (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {[1, 2, 3].map((i) => (
                  <Card key={i} className="animate-pulse">
                    <CardHeader>
                      <div className="h-4 bg-gray-200 rounded w-3/4"></div>
                      <div className="h-3 bg-gray-200 rounded w-1/2 mt-2"></div>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-3">
                        <div className="h-3 bg-gray-200 rounded"></div>
                        <div className="h-3 bg-gray-200 rounded w-2/3"></div>
                        <div className="h-8 bg-gray-200 rounded"></div>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            ) : (
              <>
                {agents.length > 0 ? (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {agents.map((agent) => (
                      <Card key={agent.id} className="hover:shadow-lg transition-shadow cursor-pointer">
                        <CardHeader>
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              {getAgentIcon(agent.type)}
                              <CardTitle className="text-lg">{agent.name}</CardTitle>
                            </div>
                            <Badge className={getAgentBadgeColor(agent.type)}>
                              {agent.type.replace('_', ' ')}
                            </Badge>
                          </div>
                          <CardDescription>{agent.description}</CardDescription>
                        </CardHeader>
                        <CardContent>
                          <div className="space-y-3">
                            <div className="flex items-center gap-2 text-sm text-muted-foreground">
                              <Zap className="h-4 w-4" />
                              <span>{agent.tools?.length || 0} herramientas disponibles</span>
                            </div>
                            <div className="flex items-center gap-2">
                              <div className={`h-2 w-2 rounded-full ${agent.is_active ? 'bg-green-500' : 'bg-red-500'}`} />
                              <span className="text-sm text-muted-foreground">
                                {agent.is_active ? 'Activo' : 'Inactivo'}
                              </span>
                            </div>
                            <Button 
                              onClick={() => setSelectedAgent(agent)}
                              className="w-full"
                              variant={agent.type === 'digital_signature' ? 'default' : 'outline'}
                            >
                              {agent.type === 'digital_signature' ? (
                                <>
                                  <MessageCircle className="h-4 w-4 mr-2" />
                                  Probar Asistente
                                </>
                              ) : (
                                'Ver Detalles'
                              )}
                            </Button>
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                ) : (
                  <Card className="text-center py-12">
                    <CardContent>
                      <Bot className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
                      <h3 className="text-lg font-semibold mb-2">No hay agentes disponibles</h3>
                      <p className="text-muted-foreground mb-4">
                        Crea agentes de IA para automatizar tareas y procesar documentos.
                      </p>
                      <div className="flex flex-col sm:flex-row gap-3 justify-center">
                        <Button 
                          onClick={async () => {
                            try {
                              const response = await agentsService.createDigitalSignatureAgent()
                              if (response.error) {
                                addNotification({
                                  type: 'error',
                                  title: 'Error',
                                  message: response.error
                                })
                              } else {
                                addNotification({
                                  type: 'success',
                                  title: 'Agente creado',
                                  message: 'Agente de firma digital creado exitosamente'
                                })
                                loadAgents()
                              }
                            } catch (error) {
                              addNotification({
                                type: 'error',
                                title: 'Error',
                                message: 'No se pudo crear el agente'
                              })
                            }
                          }}
                          variant="default"
                        >
                          <FileSignature className="h-4 w-4 mr-2" />
                          Crear Agente de Firmas
                        </Button>
                        <Button onClick={loadAgents} variant="outline">
                          Recargar
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                )}
              </>
            )}
          </TabsContent>

          <TabsContent value="test" className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Prueba de Integración Langroid</CardTitle>
                <CardDescription>
                  Prueba la conectividad y funcionalidad del sistema de agentes
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div className="space-y-3">
                    <Button 
                      onClick={async () => {
                        try {
                          const result = await agentsService.checkLangroidHealth()
                          if (result.error) {
                            addNotification({
                              type: 'error',
                              title: 'Health Check Fallido',
                              message: result.error
                            })
                          } else {
                            addNotification({
                              type: 'success',
                              title: 'Health Check Exitoso',
                              message: 'El servicio Langroid está funcionando correctamente'
                            })
                          }
                        } catch (error) {
                          addNotification({
                            type: 'error',
                            title: 'Error en Health Check',
                            message: error instanceof Error ? error.message : 'Error desconocido'
                          })
                        }
                      }}
                      className="w-full"
                      variant="outline"
                    >
                      <Activity className="h-4 w-4 mr-2" />
                      Health Check
                    </Button>

                    <Button 
                      onClick={async () => {
                        try {
                          const result = await agentsService.testLangroidAgent()
                          if (result.error) {
                            addNotification({
                              type: 'error',
                              title: 'Prueba de integración fallida',
                              message: result.error
                            })
                          } else {
                            addNotification({
                              type: 'success',
                              title: 'Prueba de integración exitosa',
                              message: 'El sistema de agentes está funcionando correctamente'
                            })
                          }
                        } catch (error) {
                          addNotification({
                            type: 'error',
                            title: 'Error en la prueba',
                            message: error instanceof Error ? error.message : 'Error desconocido'
                          })
                        }
                      }}
                      className="w-full"
                    >
                      <Activity className="h-4 w-4 mr-2" />
                      Ejecutar Prueba de Integración
                    </Button>
                  </div>
                  
                  <div className="text-sm text-muted-foreground">
                    Esta prueba verificará:
                    <ul className="list-disc list-inside mt-2 space-y-1">
                      <li>Conectividad con el microservicio Langroid</li>
                      <li>Creación y eliminación de agentes</li>
                      <li>Ejecución de tareas básicas</li>
                      <li>Streaming de respuestas</li>
                    </ul>
                  </div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="health" className="space-y-6">
            <AgentHealthCheck />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  )
}