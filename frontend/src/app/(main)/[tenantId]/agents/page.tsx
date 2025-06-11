'use client'

import * as React from 'react'
import { useState, useEffect } from 'react'
import { useAgentSelection } from '@/hooks/use-agent-selection'
import { DigitalSignatureAssistant } from '@/components/agents/digital-signature-assistant'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { MessageCircle, Activity, FileSignature, FileText, Bot, Plus, Search } from 'lucide-react'
import { Agent, useAgentsService } from '@/lib/services/agents.service'
import { useNotifications } from '@/contexts/notifications-context'

export default function AgentsPage() {
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

  const handleCreateAgent = () => {
    console.log('Create agent dialog would open here')
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


  return (
    <div className="flex flex-1 flex-col gap-4 p-4">
      {selectedAgent ? (
        // Show selected agent interface
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Button 
                variant="outline" 
                size="sm" 
                onClick={clearSelection}
                className="flex items-center gap-2"
              >
                ← Volver
              </Button>
              <div className="flex items-center gap-2">
                {getAgentIcon(selectedAgent.type)}
                <h1 className="text-2xl font-bold">{selectedAgent.name || getAgentDisplayName(selectedAgent.type)}</h1>
                <Badge 
                  variant={selectedAgent.is_active ? "default" : "secondary"}
                  className="text-xs"
                >
                  {selectedAgent.is_active ? 'Activo' : 'Inactivo'}
                </Badge>
              </div>
            </div>
          </div>
          
          {selectedAgent.type === 'digital_signature' ? (
            <DigitalSignatureAssistant agent={selectedAgent} onBack={clearSelection} />
          ) : (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  {getAgentIcon(selectedAgent.type)}
                  Interfaz del Agente
                </CardTitle>
                <CardDescription>
                  {selectedAgent.description || `Configuración y interacción con ${selectedAgent.name || getAgentDisplayName(selectedAgent.type)}`}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex items-center justify-center py-12">
                  <div className="text-center space-y-4">
                    <div className="w-16 h-16 bg-muted rounded-full flex items-center justify-center mx-auto">
                      {getAgentIcon(selectedAgent.type)}
                    </div>
                    <p className="text-muted-foreground">
                      Interfaz para {selectedAgent.name || getAgentDisplayName(selectedAgent.type)} en desarrollo...
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      ) : (
        // Show agents list
        <div className="space-y-6">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Bot className="h-8 w-8" />
              <div>
                <h1 className="text-3xl font-bold">AI Agents</h1>
                <p className="text-muted-foreground">
                  Gestiona tus agentes de inteligencia artificial
                </p>
              </div>
            </div>
            <Button onClick={handleCreateAgent} className="flex items-center gap-2">
              <Plus className="h-4 w-4" />
              Crear Agente
            </Button>
          </div>
          
          {/* Search and Filters */}
          <div className="flex items-center gap-4">
            <div className="relative flex-1 max-w-md">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Buscar agentes..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-9"
              />
            </div>
            {agents.length > 0 && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <span>Total:</span>
                <Badge variant="outline">{filteredAgents.length} de {agents.length}</Badge>
              </div>
            )}
          </div>
          
          {/* Agents Grid */}
          {isLoading ? (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {[1, 2, 3, 4, 5, 6].map((i) => (
                <Card key={i} className="animate-pulse">
                  <CardHeader>
                    <div className="flex items-center gap-3">
                      <div className="h-10 w-10 bg-gray-200 rounded" />
                      <div className="flex-1">
                        <div className="h-4 bg-gray-200 rounded w-3/4 mb-2" />
                        <div className="h-3 bg-gray-200 rounded w-1/2" />
                      </div>
                    </div>
                  </CardHeader>
                </Card>
              ))}
            </div>
          ) : filteredAgents.length === 0 ? (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-12">
                <Bot className="h-12 w-12 text-muted-foreground mb-4" />
                <h3 className="text-lg font-medium mb-2">
                  {agents.length === 0 ? 'No hay agentes' : 'No se encontraron agentes'}
                </h3>
                <p className="text-muted-foreground text-center mb-6">
                  {agents.length === 0 
                    ? 'Crea tu primer agente de IA para comenzar'
                    : 'Intenta con otros términos de búsqueda'
                  }
                </p>
                {agents.length === 0 && (
                  <Button onClick={handleCreateAgent}>
                    <Plus className="h-4 w-4 mr-2" />
                    Crear Primer Agente
                  </Button>
                )}
              </CardContent>
            </Card>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {filteredAgents.map((agent) => (
                <Card 
                  key={agent.id} 
                  className="cursor-pointer hover:shadow-md transition-shadow"
                  onClick={() => selectAgent(agent)}
                >
                  <CardHeader>
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-3">
                        <div className="p-2 rounded-lg bg-muted">
                          {getAgentIcon(agent.type)}
                        </div>
                        <div className="flex-1">
                          <CardTitle className="text-base">
                            {agent.name || getAgentDisplayName(agent.type)}
                          </CardTitle>
                          <div className="flex items-center gap-2 mt-1">
                            <Badge variant="outline" className="text-xs">
                              {getAgentDisplayName(agent.type)}
                            </Badge>
                            <div className={`h-2 w-2 rounded-full ${
                              agent.is_active ? 'bg-green-500' : 'bg-gray-400'
                            }`} />
                          </div>
                        </div>
                      </div>
                    </div>
                    {agent.description && (
                      <CardDescription className="mt-2">
                        {agent.description}
                      </CardDescription>
                    )}
                  </CardHeader>
                </Card>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}