'use client'

import { useState, useEffect } from 'react'
import { useSearchParams } from 'next/navigation'
import { useAgentSelection } from '@/hooks/use-agent-selection'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { MessageCircle, Activity, FileSignature, FileText, Bot, Zap } from 'lucide-react'
import { Agent, useAgentsService } from '@/lib/services/agents.service'
import { DigitalSignatureAssistant } from '@/components/agents/digital-signature-assistant'
import { useNotifications } from '@/contexts/notifications-context'

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [isLoading, setIsLoading] = useState(true)
  
  const agentsService = useAgentsService()
  const { addNotification } = useNotifications()
  const { selectedAgent, selectAgent, clearSelection } = useAgentSelection(agents)

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
      case 'legal_compliance':
        return <MessageCircle className="h-5 w-5" />
      case 'financial_analysis':
        return <Activity className="h-5 w-5" />
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
      case 'legal_compliance':
        return 'bg-red-100 text-red-800'
      case 'financial_analysis':
        return 'bg-orange-100 text-orange-800'
      default:
        return 'bg-gray-100 text-gray-800'
    }
  }

  if (selectedAgent) {
    if (selectedAgent.type === 'digital_signature') {
      return (
        <DigitalSignatureAssistant 
          agent={selectedAgent}
          onBack={() => clearSelection()}
        />
      )
    }
    
    // For other agent types, show a generic interface
    return (
      <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6">
        <div className="px-4 lg:px-6">
          <div className="flex items-center gap-4 mb-6">
            <Button variant="outline" onClick={() => clearSelection()}>
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
        {/* Header with Actions */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-8 gap-4">
          <div>
            <h1 className="text-3xl font-bold mb-2">AI Agent Library</h1>
            <p className="text-muted-foreground">
              Gestiona y despliega agentes de IA especializados para automatización de documentos
            </p>
          </div>
          <div className="flex gap-2">
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
                      title: 'Sistema Funcionando',
                      message: 'Todos los servicios están operativos'
                    })
                  }
                } catch (error) {
                  addNotification({
                    type: 'error',
                    title: 'Error de Conexión',
                    message: 'No se pudo verificar el estado del sistema'
                  })
                }
              }}
              variant="outline"
              size="sm"
            >
              <Activity className="h-4 w-4 mr-2" />
              Estado del Sistema
            </Button>
            <Button onClick={loadAgents} variant="outline" size="sm">
              <MessageCircle className="h-4 w-4 mr-2" />
              Recargar
            </Button>
          </div>
        </div>

        {/* Stats Overview */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <Bot className="h-8 w-8 text-blue-500" />
                <div>
                  <p className="text-sm font-medium text-muted-foreground">Agentes Activos</p>
                  <p className="text-2xl font-bold">
                    {isLoading ? '...' : agents.length}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
          
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <FileSignature className="h-8 w-8 text-green-500" />
                <div>
                  <p className="text-sm font-medium text-muted-foreground">Firma Digital</p>
                  <p className="text-2xl font-bold">
                    {isLoading ? '...' : agents.filter(a => a.type === 'digital_signature').length}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
          
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <MessageCircle className="h-8 w-8 text-red-500" />
                <div>
                  <p className="text-sm font-medium text-muted-foreground">Legal & Compliance</p>
                  <p className="text-2xl font-bold">
                    {isLoading ? '...' : agents.filter(a => a.type === 'legal_compliance').length}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
          
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <Activity className="h-8 w-8 text-orange-500" />
                <div>
                  <p className="text-sm font-medium text-muted-foreground">Análisis Financiero</p>
                  <p className="text-2xl font-bold">
                    {isLoading ? '...' : agents.filter(a => a.type === 'financial_analysis').length}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
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
                              onClick={() => selectAgent(agent)}
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
                      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mb-4">
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
                          Firma Digital
                        </Button>

                        <Button 
                          onClick={async () => {
                            try {
                              const response = await agentsService.createLegalComplianceAgent()
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
                                  message: 'Agente legal creado exitosamente'
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
                          variant="outline"
                        >
                          <MessageCircle className="h-4 w-4 mr-2" />
                          Legal Compliance
                        </Button>

                        <Button 
                          onClick={async () => {
                            try {
                              const response = await agentsService.createFinancialAnalysisAgent()
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
                                  message: 'Agente financiero creado exitosamente'
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
                          variant="outline"
                        >
                          <Activity className="h-4 w-4 mr-2" />
                          Análisis Financiero
                        </Button>

                        <Button 
                          onClick={async () => {
                            try {
                              const response = await agentsService.createDocumentAnalyzerAgent()
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
                                  message: 'Analizador de documentos creado exitosamente'
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
                          variant="outline"
                        >
                          <FileText className="h-4 w-4 mr-2" />
                          Análisis Documentos
                        </Button>

                        <Button 
                          onClick={async () => {
                            try {
                              const response = await agentsService.createRAGAssistantAgent()
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
                                  message: 'Asistente RAG creado exitosamente'
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
                          variant="outline"
                        >
                          <Bot className="h-4 w-4 mr-2" />
                          Asistente RAG
                        </Button>

                        <Button onClick={loadAgents} variant="secondary">
                          <MessageCircle className="h-4 w-4 mr-2" />
                          Recargar
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                )}
              </>
            )}
        </div>
      </div>
    </div>
  )
}