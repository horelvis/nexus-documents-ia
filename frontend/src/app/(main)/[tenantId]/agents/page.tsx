'use client'

import { useState, useEffect } from 'react'
import { useSearchParams } from 'next/navigation'
import { useAgentSelection } from '@/hooks/use-agent-selection'
import { AgentsMainSidebar } from '@/components/layout/agents-main-sidebar'
import { AgentsSidebar } from '@/components/layout/agents-sidebar'
import { DigitalSignatureAssistant } from '@/components/agents/digital-signature-assistant'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb"
import { Separator } from "@/components/ui/separator"
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { MessageCircle, Activity, FileSignature, FileText, Bot, Zap, Plus } from 'lucide-react'
import { Agent, useAgentsService } from '@/lib/services/agents.service'
import { useNotifications } from '@/contexts/notifications-context'

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  
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
    <SidebarProvider
      style={
        {
          "--sidebar-width": "350px",
        } as React.CSSProperties
      }
    >
      {/* Main Navigation Sidebar */}
      <AgentsMainSidebar onCreateAgent={handleCreateAgent} />
      
      {/* Agents List Sidebar */}
      <AgentsSidebar 
        selectedAgent={selectedAgent}
        onAgentSelect={selectAgent}
        onCreateAgent={handleCreateAgent}
      />
      
      {/* Main Content */}
      <SidebarInset>
        <header className="bg-background sticky top-0 flex shrink-0 items-center gap-2 border-b p-4">
          <SidebarTrigger className="-ml-1" />
          <Separator orientation="vertical" className="mr-2 h-4" />
          <Breadcrumb>
            <BreadcrumbList>
              <BreadcrumbItem className="hidden md:block">
                <BreadcrumbLink href="#">AI Hub</BreadcrumbLink>
              </BreadcrumbItem>
              <BreadcrumbSeparator className="hidden md:block" />
              <BreadcrumbItem>
                <BreadcrumbPage>
                  {selectedAgent ? selectedAgent.name : 'Agentes'}
                </BreadcrumbPage>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>
        </header>
        
        {renderAgentContent()}
      </SidebarInset>
    </SidebarProvider>
  )
}