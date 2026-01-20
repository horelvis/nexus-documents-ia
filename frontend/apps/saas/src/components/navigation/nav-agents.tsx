"use client"

import { useState, useEffect } from "react"
import { ChevronRight, FileSignature, FileText, Bot, MessageCircle, Activity, Zap, CheckCircle } from "lucide-react"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import {
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
} from "@/components/ui/sidebar"
import { Badge } from "@/components/ui/badge"
import { Agent, useAgentsService } from "@/lib/services/agents.service"
import { useNotifications } from "@/contexts/app-state-context"
import { useParams, useSearchParams } from "next/navigation"
import { useNavigation } from "@/hooks/use-navigation"

export function NavAgents() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isOpen, setIsOpen] = useState(false)
  
  const agentsService = useAgentsService()
  const { addNotification } = useNotifications()
  const { navigate } = useNavigation()
  const params = useParams()
  const searchParams = useSearchParams()
  const tenantId = params.tenantId as string
  const selectedAgentId = searchParams.get('agentId')

  useEffect(() => {
    loadAgents()
  }, [])

  // Auto-expand when there are agents or when an agent is selected
  useEffect(() => {
    if (agents.length > 0 || selectedAgentId) {
      setIsOpen(true)
    }
  }, [agents.length, selectedAgentId])

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
        return <MessageCircle className="h-4 w-4" />
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

  const handleAgentClick = (agent: Agent) => {
    // Navigate to agents page with agent selection
    navigate(`/${tenantId}/agents?agentId=${agent.id}`)
  }

  const getStatusBadge = (isActive: boolean) => {
    return isActive ? (
      <Badge variant="secondary" className="bg-green-100 text-green-800 text-xs">
        Activo
      </Badge>
    ) : (
      <Badge variant="secondary" className="bg-gray-100 text-gray-600 text-xs">
        Inactivo
      </Badge>
    )
  }

  return (
    <SidebarGroup>
      <SidebarGroupLabel>AI Agents</SidebarGroupLabel>
      <SidebarMenu>
        <Collapsible
          open={isOpen}
          onOpenChange={setIsOpen}
          className="group/collapsible"
        >
          <SidebarMenuItem>
            <CollapsibleTrigger asChild>
              <SidebarMenuButton tooltip="Available Agents" className="w-full">
                <Bot className="h-4 w-4" />
                <span>Agentes Disponibles</span>
                <div className="ml-auto flex items-center gap-2">
                  {!isLoading && agents.length > 0 && (
                    <Badge variant="secondary" className="text-xs">
                      {agents.length}
                    </Badge>
                  )}
                  <ChevronRight className="h-4 w-4 transition-transform duration-200 group-data-[state=open]/collapsible:rotate-90" />
                </div>
              </SidebarMenuButton>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <SidebarMenuSub>
                {isLoading ? (
                  <SidebarMenuSubItem>
                    <SidebarMenuSubButton className="text-muted-foreground">
                      <div className="flex items-center gap-2">
                        <div className="h-2 w-2 rounded-full bg-gray-300 animate-pulse" />
                        Cargando agentes...
                      </div>
                    </SidebarMenuSubButton>
                  </SidebarMenuSubItem>
                ) : agents.length === 0 ? (
                  <SidebarMenuSubItem>
                    <SidebarMenuSubButton 
                      onClick={() => router.push(`/${tenantId}/agents`)}
                      className="text-muted-foreground hover:text-foreground cursor-pointer"
                    >
                      <div className="flex items-center gap-2">
                        <Zap className="h-3 w-3" />
                        Crear primer agente
                      </div>
                    </SidebarMenuSubButton>
                  </SidebarMenuSubItem>
                ) : (
                  agents.map((agent) => {
                    const isSelected = selectedAgentId === agent.id
                    return (
                      <SidebarMenuSubItem key={agent.id}>
                        <SidebarMenuSubButton 
                          onClick={() => handleAgentClick(agent)}
                          className={`cursor-pointer group/agent ${
                            isSelected ? 'bg-blue-50 border-l-2 border-l-blue-500' : ''
                          }`}
                        >
                          <div className="flex items-center gap-2 w-full">
                            <div className="flex items-center gap-2 flex-1 min-w-0">
                              {isSelected ? (
                                <CheckCircle className="h-4 w-4 text-blue-600" />
                              ) : (
                                getAgentIcon(agent.type)
                              )}
                              <span className={`truncate text-sm ${
                                isSelected ? 'text-blue-700 font-medium' : ''
                              }`}>
                                {agent.name || getAgentDisplayName(agent.type)}
                              </span>
                            </div>
                            <div className="flex items-center gap-1">
                              {getStatusBadge(agent.is_active)}
                              <div className={`h-2 w-2 rounded-full ${
                                agent.is_active ? 'bg-green-500' : 'bg-gray-400'
                              }`} />
                            </div>
                          </div>
                        </SidebarMenuSubButton>
                      </SidebarMenuSubItem>
                    )
                  })
                )}
                
                {/* Quick actions */}
                <SidebarMenuSubItem>
                  <SidebarMenuSubButton 
                    onClick={() => router.push(`/${tenantId}/agents`)}
                    className="text-blue-600 hover:text-blue-700 cursor-pointer mt-2 border-t pt-2"
                  >
                    <div className="flex items-center gap-2">
                      <Bot className="h-3 w-3" />
                      Ver todos los agentes
                    </div>
                  </SidebarMenuSubButton>
                </SidebarMenuSubItem>
              </SidebarMenuSub>
            </CollapsibleContent>
          </SidebarMenuItem>
        </Collapsible>
      </SidebarMenu>
    </SidebarGroup>
  )
}