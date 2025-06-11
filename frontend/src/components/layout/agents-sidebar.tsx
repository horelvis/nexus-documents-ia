"use client"

import * as React from "react"
import { useState, useEffect } from "react"
import { 
  Bot, 
  FileSignature, 
  FileText, 
  MessageCircle, 
  Activity, 
  Zap,
  CheckCircle,
  Search,
  Plus
} from "lucide-react"

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInput,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Agent, useAgentsService } from "@/lib/services/agents.service"
import { useNotifications } from "@/contexts/notifications-context"
import { useParams } from "next/navigation"

interface AgentsSidebarProps {
  selectedAgent?: Agent | null
  onAgentSelect?: (agent: Agent) => void
  onCreateAgent?: () => void
}

export function AgentsSidebar({ 
  selectedAgent, 
  onAgentSelect, 
  onCreateAgent,
  ...props 
}: AgentsSidebarProps & React.ComponentProps<typeof Sidebar>) {
  const [agents, setAgents] = useState<Agent[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState("")
  
  const agentsService = useAgentsService()
  const { addNotification } = useNotifications()
  const params = useParams()
  const tenantId = params.tenantId as string

  useEffect(() => {
    loadAgents()
  }, [])

  const loadAgents = async () => {
    try {
      setIsLoading(true)
      const response = await agentsService.getAgents()
      
      if (response.error) {
        console.error('Error loading agents:', response.error)
        setAgents([])
      } else {
        const agentsData = response.data?.agents || response.data || []
        setAgents(agentsData)
      }
    } catch (error) {
      console.error('Error loading agents:', error)
      setAgents([])
    } finally {
      setIsLoading(false)
    }
  }

  const getAgentIcon = (type: string) => {
    switch (type) {
      case 'digital_signature':
        return <FileSignature className="h-4 w-4" />
      case 'document_analyzer':
        return <FileText className="h-4 w-4" />
      case 'rag_assistant':
        return <Bot className="h-4 w-4" />
      case 'legal_compliance':
        return <MessageCircle className="h-4 w-4" />
      case 'financial_analysis':
        return <Activity className="h-4 w-4" />
      default:
        return <Bot className="h-4 w-4" />
    }
  }

  const getAgentDisplayName = (type: string) => {
    switch (type) {
      case 'digital_signature':
        return 'Firma Digital'
      case 'document_analyzer':
        return 'Análisis Documentos'
      case 'rag_assistant':
        return 'Asistente RAG'
      case 'legal_compliance':
        return 'Legal & Compliance'
      case 'financial_analysis':
        return 'Análisis Financiero'
      default:
        return type.replace('_', ' ')
    }
  }

  const getStatusBadge = (isActive: boolean) => {
    return isActive ? (
      <div className="h-2 w-2 rounded-full bg-green-500" />
    ) : (
      <div className="h-2 w-2 rounded-full bg-gray-400" />
    )
  }

  const filteredAgents = agents.filter(agent => {
    if (!searchQuery) return true
    const query = searchQuery.toLowerCase()
    return (
      agent.name?.toLowerCase().includes(query) ||
      getAgentDisplayName(agent.type).toLowerCase().includes(query) ||
      agent.description?.toLowerCase().includes(query)
    )
  })

  const handleCreateNewAgent = async (agentType: string) => {
    try {
      let response
      
      switch (agentType) {
        case 'digital_signature':
          response = await agentsService.createDigitalSignatureAgent()
          break
        case 'legal_compliance':
          response = await agentsService.createLegalComplianceAgent()
          break
        case 'financial_analysis':
          response = await agentsService.createFinancialAnalysisAgent()
          break
        case 'document_analyzer':
          response = await agentsService.createDocumentAnalyzerAgent()
          break
        case 'rag_assistant':
          response = await agentsService.createRAGAssistantAgent()
          break
        default:
          return
      }

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
          message: `Agente ${getAgentDisplayName(agentType)} creado exitosamente`
        })
        await loadAgents()
      }
    } catch (error) {
      addNotification({
        type: 'error',
        title: 'Error',
        message: 'No se pudo crear el agente'
      })
    }
  }

  const quickCreateOptions = [
    { type: 'digital_signature', icon: FileSignature, name: 'Firma Digital' },
    { type: 'legal_compliance', icon: MessageCircle, name: 'Legal' },
    { type: 'financial_analysis', icon: Activity, name: 'Financiero' },
    { type: 'document_analyzer', icon: FileText, name: 'Documentos' },
    { type: 'rag_assistant', icon: Bot, name: 'RAG' },
  ]

  return (
    <Sidebar collapsible="none" className="hidden flex-1 md:flex" {...props}>
      <SidebarHeader className="gap-3.5 border-b p-4">
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
            onClick={onCreateAgent}
            className="h-8 px-2"
          >
            <Plus className="h-3 w-3" />
          </Button>
        </div>
        <SidebarInput 
          placeholder="Buscar agentes..." 
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="h-8"
        />
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup className="px-0">
          <SidebarGroupContent>
            {isLoading ? (
              // Loading state
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
              // Empty state
              <div className="p-4 text-center">
                {searchQuery ? (
                  <div className="space-y-3">
                    <Search className="h-8 w-8 mx-auto text-muted-foreground" />
                    <p className="text-sm text-muted-foreground">
                      No se encontraron agentes con "{searchQuery}"
                    </p>
                  </div>
                ) : agents.length === 0 ? (
                  <div className="space-y-4">
                    <div className="space-y-2">
                      <Bot className="h-12 w-12 mx-auto text-muted-foreground" />
                      <h3 className="font-medium">No hay agentes</h3>
                      <p className="text-sm text-muted-foreground">
                        Crea tu primer agente de IA para automatizar tareas
                      </p>
                    </div>
                    <div className="space-y-2">
                      <p className="text-xs font-medium text-muted-foreground">CREAR RÁPIDO:</p>
                      <div className="grid grid-cols-2 gap-1">
                        {quickCreateOptions.map((option) => (
                          <Button
                            key={option.type}
                            variant="ghost"
                            size="sm"
                            onClick={() => handleCreateNewAgent(option.type)}
                            className="h-8 px-2 text-xs justify-start"
                          >
                            <option.icon className="h-3 w-3 mr-1" />
                            {option.name}
                          </Button>
                        ))}
                      </div>
                    </div>
                  </div>
                ) : null}
              </div>
            ) : (
              // Agents list
              filteredAgents.map((agent) => {
                const isSelected = selectedAgent?.id === agent.id
                return (
                  <button
                    key={agent.id}
                    onClick={() => onAgentSelect?.(agent)}
                    className={`w-full flex flex-col items-start gap-2 border-b p-4 text-sm leading-tight whitespace-nowrap last:border-b-0 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground transition-colors ${
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
                        {getStatusBadge(agent.is_active)}
                        <span className={`text-xs ${
                          agent.is_active ? 'text-green-600' : 'text-gray-500'
                        }`}>
                          {agent.is_active ? 'Activo' : 'Inactivo'}
                        </span>
                      </div>
                    </div>
                    
                    {agent.description && (
                      <span className="line-clamp-2 w-full text-xs text-muted-foreground text-left">
                        {agent.description}
                      </span>
                    )}
                    
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <span>Tipo: {getAgentDisplayName(agent.type)}</span>
                      {agent.tools && (
                        <>
                          <span>•</span>
                          <span>{agent.tools.length} herramientas</span>
                        </>
                      )}
                    </div>
                  </button>
                )
              })
            )}
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter className="p-4 border-t">
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>Total de agentes:</span>
            <Badge variant="outline" className="text-xs">
              {agents.length}
            </Badge>
          </div>
          {agents.length > 0 && (
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>Activos:</span>
              <Badge variant="outline" className="text-xs">
                {agents.filter(a => a.is_active).length}
              </Badge>
            </div>
          )}
        </div>
      </SidebarFooter>
    </Sidebar>
  )
}