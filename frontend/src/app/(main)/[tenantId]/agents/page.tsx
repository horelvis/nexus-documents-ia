'use client'

import { useState, useEffect } from 'react'
import { useSearchParams, useRouter, useParams } from 'next/navigation'
import { useAgentSelection } from '@/hooks/use-agent-selection'
import { DigitalSignatureAssistant } from '@/components/agents/digital-signature-assistant'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { MessageCircle, Activity, FileSignature, FileText, Bot, Zap, Plus, CheckCircle } from 'lucide-react'
import { Agent, useAgentsService } from '@/lib/services/agents.service'
import { useNotifications } from '@/contexts/notifications-context'

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  
  const router = useRouter()
  const params = useParams()
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

  const handleCreateAgent = () => {
    setShowCreateDialog(true)
  }

  // Agent interaction content based on selection
  const renderAgentContent = () => {
    if (!selectedAgent) {
      return (
        <div className="flex flex-1 flex-col gap-4 p-4">
          <div className="mx-auto max-w-2xl text-center">
            <Bot className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
            <h2 className="text-2xl font-bold mb-2">Selecciona un Agente</h2>
            <p className="text-muted-foreground mb-6">
              Elige un agente de IA del panel lateral para interactuar con él o crear uno nuevo.
            </p>
            <Button onClick={handleCreateAgent} size="lg">
              <Plus className="h-4 w-4 mr-2" />
              Crear Nuevo Agente
            </Button>
          </div>
        </div>
      )
    }

    if (selectedAgent.type === 'digital_signature') {
      return <DigitalSignatureAssistant agent={selectedAgent} onBack={clearSelection} />
    }

    // Generic agent interface for other types
    return (
      <div className="flex flex-1 flex-col gap-4 p-4">
        <div className="space-y-6">
          <div>
            <h1 className="text-3xl font-bold">{selectedAgent.name}</h1>
            <p className="text-muted-foreground">{selectedAgent.description}</p>
          </div>
          
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                {getAgentIcon(selectedAgent.type)}
                Interfaz del Agente
              </CardTitle>
              <CardDescription>
                Configuración y interacción con {selectedAgent.name}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex items-center justify-center py-12">
                <div className="text-center space-y-4">
                  <div className="w-16 h-16 bg-muted rounded-full flex items-center justify-center mx-auto">
                    {getAgentIcon(selectedAgent.type)}
                  </div>
                  <p className="text-muted-foreground">
                    Interfaz para {selectedAgent.name} en desarrollo...
                  </p>
                  <Button variant="outline" onClick={clearSelection}>
                    ← Volver a la lista
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
      {/* Agents Sidebar */}
      <div className="fixed inset-y-0 left-[--sidebar-width] z-10 hidden h-svh w-80 border-r bg-sidebar md:flex flex-col">
        <div className="gap-3.5 border-b p-4">
          <div className="flex w-full items-center justify-between">
            <div className="text-foreground text-base font-medium flex items-center gap-2">
              <Bot className="h-5 w-5" />
              AI Agents
              {agents.length > 0 && (
                <Badge variant="secondary" className="text-xs">
                  {agents.length}
                </Badge>
              )}
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={handleCreateAgent}
              className="h-8 px-2"
            >
              <Plus className="h-3 w-3" />
            </Button>
          </div>
          <div className="mt-4">
            <input 
              placeholder="Buscar agentes..." 
              className="bg-background h-8 w-full shadow-none border rounded-md px-3 text-sm"
            />
          </div>
        </div>
        
        <div className="flex-1 overflow-auto">
          <div className="w-full text-sm">
            {isLoading ? (
              <div className="p-4">
                <div className="space-y-3">
                  {[1, 2, 3].map((i) => (
                    <div key={i} className="flex items-center gap-3 animate-pulse">
                      <div className="h-8 w-8 bg-gray-200 rounded" />
                      <div className="flex-1">
                        <div className="h-4 bg-gray-200 rounded w-3/4 mb-2" />
                        <div className="h-3 bg-gray-200 rounded w-1/2" />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : agents.length === 0 ? (
              <div className="p-4 text-center">
                <div className="space-y-4">
                  <Bot className="h-12 w-12 mx-auto text-muted-foreground" />
                  <h3 className="font-medium">No hay agentes</h3>
                  <p className="text-sm text-muted-foreground">
                    Crea tu primer agente de IA
                  </p>
                  <Button onClick={handleCreateAgent} size="sm">
                    <Plus className="h-3 w-3 mr-1" />
                    Crear Agente
                  </Button>
                </div>
              </div>
            ) : (
              agents.map((agent) => {
                const isSelected = selectedAgent?.id === agent.id
                return (
                  <button
                    key={agent.id}
                    onClick={() => selectAgent(agent)}
                    className={`w-full flex flex-col items-start gap-2 border-b p-4 text-sm leading-tight last:border-b-0 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground transition-colors text-left ${
                      isSelected ? 'bg-sidebar-accent border-l-2 border-l-blue-500' : ''
                    }`}
                  >
                    <div className="flex w-full items-center gap-3">
                      <div className="flex items-center gap-2">
                        {isSelected ? (
                          <CheckCircle className="h-4 w-4 text-blue-600" />
                        ) : (
                          getAgentIcon(agent.type)
                        )}
                        <span className={`font-medium ${isSelected ? 'text-blue-700' : ''}`}>
                          {agent.name || getAgentDisplayName(agent.type)}
                        </span>
                      </div>
                      <div className="ml-auto flex items-center gap-2">
                        <div className={`h-2 w-2 rounded-full ${
                          agent.is_active ? 'bg-green-500' : 'bg-gray-400'
                        }`} />
                      </div>
                    </div>
                    
                    {agent.description && (
                      <span className="line-clamp-2 w-full text-xs text-muted-foreground text-left">
                        {agent.description}
                      </span>
                    )}
                  </button>
                )
              })
            )}
          </div>
        </div>
        
        <div className="p-4 border-t">
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>Total:</span>
              <Badge variant="outline" className="text-xs">{agents.length}</Badge>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content with left margin for sidebar */}
      <div className="ml-80 flex flex-1 flex-col">
        {renderAgentContent()}
      </div>
    </div>
  )
}