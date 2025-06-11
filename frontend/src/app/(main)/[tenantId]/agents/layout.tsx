'use client'

import { useState, useEffect } from 'react'
import { Bot, Plus, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
import { Agent, useAgentsService } from '@/lib/services/agents.service'
import { useNotifications } from '@/contexts/notifications-context'
import { useAgentSelection } from '@/hooks/use-agent-selection'

interface AgentsLayoutProps {
  children: React.ReactNode
}

export default function AgentsLayout({ children }: AgentsLayoutProps) {
  const [agents, setAgents] = useState<Agent[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState('')
  
  const agentsService = useAgentsService()
  const { addNotification } = useNotifications()
  const { selectedAgent, selectAgent, clearSelection } = useAgentSelection(agents)
  
  // Filter agents based on search term
  const filteredAgents = agents.filter(agent => 
    agent.name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    getAgentDisplayName(agent.type).toLowerCase().includes(searchTerm.toLowerCase()) ||
    agent.description?.toLowerCase().includes(searchTerm.toLowerCase())
  )

  // Simple data loading function following CLAUDE.md pattern
  const loadAgents = async () => {
    setIsLoading(true)
    
    try {
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

  useEffect(() => {
    loadAgents()
  }, [])

  const getAgentIcon = (type: string) => {
    switch (type) {
      case 'digital_signature':
        return <Bot className="h-5 w-5" />
      case 'document_analyzer':
        return <Bot className="h-5 w-5" />
      case 'rag_assistant':
        return <Bot className="h-5 w-5" />
      case 'legal_compliance':
        return <Bot className="h-5 w-5" />
      case 'financial_analysis':
        return <Bot className="h-5 w-5" />
      default:
        return <Bot className="h-5 w-5" />
    }
  }

  const getAgentDisplayName = (type: string) => {
    switch (type) {
      case 'digital_signature':
        return 'Asistente de Firmas Digitales'
      case 'document_analyzer':
        return 'Analizador de Documentos'
      case 'rag_assistant':
        return 'Asistente RAG'
      case 'legal_compliance':
        return 'Cumplimiento Legal'
      case 'financial_analysis':
        return 'Análisis Financiero'
      default:
        return 'Agente de IA'
    }
  }

  const handleCreateAgent = () => {
    console.log('Create agent dialog would open here')
  }

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 h-full">
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 flex-1 h-full">
        {/* Agents List Card - Left Side */}
        <div className="lg:col-span-1 flex flex-col h-full">
          <Card className="flex flex-col h-full">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="flex items-center gap-2">
                  <Bot className="h-5 w-5" />
                  AI Agents
                  {agents.length > 0 && (
                    <Badge variant="secondary" className="text-xs">
                      {agents.length}
                    </Badge>
                  )}
                </CardTitle>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleCreateAgent}
                  className="h-8 px-2"
                >
                  <Plus className="h-3 w-3" />
                </Button>
              </div>
              
              {/* Search Input */}
              <div className="relative">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder="Buscar agentes..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="pl-9 h-8"
                />
              </div>
            </CardHeader>
            
            <CardContent className="p-0 flex-1 flex flex-col">
              {/* Agents List */}
              <div className="flex-1 overflow-auto">
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
                ) : filteredAgents.length === 0 ? (
                  <div className="p-4 text-center">
                    <div className="space-y-4">
                      <Bot className="h-12 w-12 mx-auto text-muted-foreground" />
                      <div>
                        <h3 className="font-medium">
                          {agents.length === 0 ? 'No hay agentes' : 'No se encontraron agentes'}
                        </h3>
                        <p className="text-sm text-muted-foreground">
                          {agents.length === 0 
                            ? 'Crea tu primer agente de IA'
                            : 'Intenta con otros términos de búsqueda'
                          }
                        </p>
                      </div>
                      {agents.length === 0 && (
                        <Button onClick={handleCreateAgent} size="sm">
                          <Plus className="h-3 w-3 mr-1" />
                          Crear Agente
                        </Button>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="divide-y">
                    {filteredAgents.map((agent) => {
                      const isSelected = selectedAgent?.id === agent.id
                      return (
                        <button
                          key={agent.id}
                          onClick={() => selectAgent(agent)}
                          className={`w-full flex flex-col items-start gap-2 p-4 text-sm leading-tight hover:bg-muted/50 transition-colors text-left ${
                            isSelected ? 'bg-muted border-l-2 border-l-primary' : ''
                          }`}
                        >
                          <div className="flex w-full items-center gap-3">
                            <div className="flex items-center gap-2">
                              {getAgentIcon(agent.type)}
                              <span className={`font-medium ${isSelected ? 'text-primary' : ''}`}>
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
                    })}
                  </div>
                )}
              </div>
              
              {/* Footer */}
              {agents.length > 0 && (
                <div className="mt-auto">
                  <Separator />
                  <div className="p-4">
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <span>Total:</span>
                      <Badge variant="outline" className="text-xs">
                        {filteredAgents.length} de {agents.length}
                      </Badge>
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Main Content Area - Right Side */}
        <div className="lg:col-span-3 flex flex-col h-full">
          {children}
        </div>
      </div>
    </div>
  )
}