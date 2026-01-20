'use client'

import React, { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
  IconRobot,
  IconPlus,
  IconRefresh,
  IconSettings,
  IconTrash,
  IconEdit,
  IconFileText,
  IconSignature,
  IconScale,
  IconChartBar,
  IconSearch,
  IconActivity,
  IconAlertCircle,
  IconCheck,
  IconLoader2,
  IconBrain,
  IconMessageCircle,
  IconPlayerPlay
} from '@tabler/icons-react'
import { useAgentService, type Agent } from '@/lib/services/agent.service'
import { useNotifications } from '@/contexts/notifications-context'

// NO HARDCODE - Obtener datos REALES de la API
const getAgentIconFromRole = (role: string) => {
  // Usar palabras clave del role REAL para determinar icono
  const roleWords = role.toLowerCase()
  if (roleWords.includes('virtual') || roleWords.includes('assistant')) return IconMessageCircle
  if (roleWords.includes('search') || roleWords.includes('find')) return IconSearch  
  if (roleWords.includes('document') || roleWords.includes('analyst')) return IconFileText
  if (roleWords.includes('compliance') || roleWords.includes('legal')) return IconScale
  if (roleWords.includes('communication') || roleWords.includes('specialist')) return IconMessageCircle
  if (roleWords.includes('workflow') || roleWords.includes('coordinator')) return IconSettings
  if (roleWords.includes('signature')) return IconSignature
  if (roleWords.includes('financial')) return IconChartBar
  return IconRobot
}

const getAgentColorFromRole = (role: string) => {
  // Usar palabras clave del role REAL para determinar color
  const roleWords = role.toLowerCase()
  if (roleWords.includes('virtual') || roleWords.includes('assistant')) return 'bg-blue-500'
  if (roleWords.includes('search') || roleWords.includes('find')) return 'bg-green-500'
  if (roleWords.includes('document') || roleWords.includes('analyst')) return 'bg-purple-500'
  if (roleWords.includes('compliance') || roleWords.includes('legal')) return 'bg-red-500'
  if (roleWords.includes('communication') || roleWords.includes('specialist')) return 'bg-orange-500'
  if (roleWords.includes('workflow') || roleWords.includes('coordinator')) return 'bg-cyan-500'
  if (roleWords.includes('signature')) return 'bg-purple-500'
  if (roleWords.includes('financial')) return 'bg-yellow-500'
  return 'bg-gray-500'
}

export default function AgentsPage() {
  const params = useParams()
  const router = useRouter()
  const tenantId = params.tenantId as string
  const agentService = useAgentService()
  const { addNotification } = useNotifications()

  const [activeTab, setActiveTab] = useState('overview')
  const [availableAgents, setAvailableAgents] = useState<any[]>([])
  const [serviceStatus, setServiceStatus] = useState<any>(null)
  const [statistics, setStatistics] = useState<any>(null)
  const [recentActivity, setRecentActivity] = useState<any[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  
  // Chat state
  const [selectedAgent, setSelectedAgent] = useState<string>('')
  const [chatMessages, setChatMessages] = useState<Array<{role: string, content: string, timestamp: string}>>([])
  const [chatInput, setChatInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  
  // Create agent dialog
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const [newAgentName, setNewAgentName] = useState('')
  const [newAgentType, setNewAgentType] = useState('')
  const [newAgentDescription, setNewAgentDescription] = useState('')
  const [creating, setCreating] = useState(false)

  // Load agents and status - USA SOLO DATOS REALES DE LA API
  const loadData = async () => {
    setIsLoading(true)
    setError(null)
    
    try {
      // Obtener TODOS los datos de la API - SIN HARDCODE
      const [agentsResponse, statusResponse, statisticsResponse, activityResponse, typesResponse] = await Promise.all([
        agentService.getAgents(),
        agentService.getAgentStatus(),
        agentService.getAgentStatistics(),
        agentService.getAgentActivity(10),
        agentService.getAgentTypes()  // DATOS REALES de tipos
      ])
      
      if (agentsResponse.error) {
        throw new Error(agentsResponse.error)
      }
      
      // Usar SOLO datos REALES del API - disponible en agentsResponse.data
      if (agentsResponse.data?.available_types) {
        const agents = Object.entries(agentsResponse.data.available_types).map(([key, value]: [string, any]) => ({
          id: key,
          name: value.name || key,
          description: value.description || '',
          agent_type: key,
          capabilities: value.capabilities || [],
          source: value.source || 'crewai',
          status: value.status || 'active',
          // Usar datos REALES del role del agente CrewAI, no hardcode
          icon: getAgentIconFromRole(value.role || value.name || key),
          color: getAgentColorFromRole(value.role || value.name || key),
          role: value.role || '',
          goal: value.goal || '',
          tools: value.tools || []
        }))
        setAvailableAgents(agents)
      }
      
      if (statusResponse.data) {
        setServiceStatus(statusResponse.data)
      }

      if (statisticsResponse.data) {
        setStatistics(statisticsResponse.data)
      }

      if (activityResponse.data) {
        setRecentActivity(activityResponse.data.activities || [])
      }
    } catch (err) {
      console.error('Failed to load agent data:', err)
      setError(err instanceof Error ? err.message : 'Failed to load agent data')
      addNotification({
        type: 'error',
        title: 'Load Failed',
        message: 'Failed to load agent data'
      })
    } finally {
      setIsLoading(false)
    }
  }

  // Send chat message
  const sendChatMessage = async () => {
    if (!chatInput.trim() || !selectedAgent) return
    
    setChatLoading(true)
    const userMessage = chatInput.trim()
    setChatInput('')
    
    // Add user message
    const newMessage = {
      role: 'user',
      content: userMessage,
      timestamp: new Date().toISOString()
    }
    setChatMessages(prev => [...prev, newMessage])
    
    try {
      let assistantMessage = ''
      const assistantMsg = {
        role: 'assistant',
        content: '',
        timestamp: new Date().toISOString()
      }
      setChatMessages(prev => [...prev, assistantMsg])
      
      await agentService.chatWithAgent(
        selectedAgent,
        userMessage,
        (chunk) => {
          assistantMessage += chunk
          setChatMessages(prev => 
            prev.map((msg, idx) => 
              idx === prev.length - 1 ? {...msg, content: assistantMessage} : msg
            )
          )
        },
        () => {
          setChatLoading(false)
        }
      )
    } catch (error) {
      console.error('Chat error:', error)
      setChatMessages(prev => prev.slice(0, -1)) // Remove assistant message
      addNotification({
        type: 'error',
        title: 'Chat Error',
        message: 'Failed to send message to agent'
      })
      setChatLoading(false)
    }
  }

  // Create new agent
  const createAgent = async () => {
    if (!newAgentName.trim() || !newAgentType) return
    
    setCreating(true)
    try {
      const response = await agentService.createAgent({
        name: newAgentName,
        description: newAgentDescription,
        agent_type: newAgentType as any
      })
      
      if (response.error) {
        throw new Error(response.error)
      }
      
      addNotification({
        type: 'success',
        title: 'Agent Created',
        message: `Agent "${newAgentName}" was created successfully`
      })
      
      setCreateDialogOpen(false)
      setNewAgentName('')
      setNewAgentType('')
      setNewAgentDescription('')
      loadData()
    } catch (error) {
      console.error('Create agent error:', error)
      addNotification({
        type: 'error',
        title: 'Creation Failed',
        message: error instanceof Error ? error.message : 'Failed to create agent'
      })
    } finally {
      setCreating(false)
    }
  }

  // Test agent
  const testAgent = async (agentId: string) => {
    try {
      addNotification({
        type: 'info',
        title: 'Testing Agent',
        message: `Running test for ${agentId}...`
      })
      
      await agentService.executeTask(
        agentId,
        'health_check',
        undefined,
        (chunk) => console.log('Test progress:', chunk),
        () => {
          addNotification({
            type: 'success',
            title: 'Test Complete',
            message: `Agent ${agentId} is working correctly`
          })
        }
      )
    } catch (error) {
      addNotification({
        type: 'error',
        title: 'Test Failed',
        message: `Agent ${agentId} test failed`
      })
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  if (isLoading) {
    return (
      <div className="flex flex-col h-full">
        <div className="px-6 py-4 border-b">
          <Skeleton className="h-8 w-64 mb-2" />
          <Skeleton className="h-4 w-96" />
        </div>
        <div className="flex-1 p-6">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[1, 2, 3, 4, 5, 6].map(i => (
              <Card key={i}>
                <CardHeader>
                  <Skeleton className="h-6 w-32" />
                  <Skeleton className="h-4 w-48" />
                </CardHeader>
                <CardContent>
                  <Skeleton className="h-20 w-full" />
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col h-full">
        <div className="px-6 py-4 border-b">
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <IconRobot className="h-6 w-6 text-blue-500" />
            AI Agents
          </h1>
        </div>
        <div className="flex-1 flex items-center justify-center">
          <Card className="max-w-md w-full">
            <CardContent className="pt-6">
              <div className="text-center">
                <IconAlertCircle className="h-12 w-12 text-red-500 mx-auto mb-4" />
                <h3 className="text-lg font-semibold mb-2">Failed to load agents</h3>
                <p className="text-muted-foreground mb-4">{error}</p>
                <Button onClick={loadData} variant="outline">
                  <IconRefresh className="mr-2 h-4 w-4" />
                  Try Again
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-6 py-4 border-b">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <IconRobot className="h-6 w-6 text-blue-500" />
              AI Agents
            </h1>
            <p className="text-muted-foreground text-sm mt-1">
              Manage and interact with your intelligent document processing agents
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button onClick={loadData} variant="outline" size="sm">
              <IconRefresh className="mr-2 h-4 w-4" />
              Refresh
            </Button>
            <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
              <DialogTrigger asChild>
                <Button>
                  <IconPlus className="mr-2 h-4 w-4" />
                  Create Agent
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Create New Agent</DialogTitle>
                  <DialogDescription>
                    Create a new AI agent with custom configuration
                  </DialogDescription>
                </DialogHeader>
                <div className="space-y-4">
                  <div>
                    <Label htmlFor="name">Agent Name</Label>
                    <Input
                      id="name"
                      value={newAgentName}
                      onChange={(e) => setNewAgentName(e.target.value)}
                      placeholder="My Custom Agent"
                    />
                  </div>
                  <div>
                    <Label htmlFor="type">Agent Type</Label>
                    <Select value={newAgentType} onValueChange={setNewAgentType}>
                      <SelectTrigger>
                        <SelectValue placeholder="Select agent type" />
                      </SelectTrigger>
                      <SelectContent>
                        {/* Usar opciones REALES de la API, no hardcode */}
                        {availableAgents.map(agent => (
                          <SelectItem key={agent.id} value={agent.id}>
                            {agent.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label htmlFor="description">Description</Label>
                    <Textarea
                      id="description"
                      value={newAgentDescription}
                      onChange={(e) => setNewAgentDescription(e.target.value)}
                      placeholder="Describe what this agent does..."
                    />
                  </div>
                </div>
                <DialogFooter>
                  <Button variant="outline" onClick={() => setCreateDialogOpen(false)}>
                    Cancel
                  </Button>
                  <Button onClick={createAgent} disabled={creating || !newAgentName || !newAgentType}>
                    {creating && <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />}
                    Create Agent
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        <Tabs value={activeTab} onValueChange={setActiveTab} className="h-full">
          <div className="px-6 pt-4">
            <TabsList className="grid w-full grid-cols-3 max-w-[600px]">
              <TabsTrigger value="overview">
                <IconActivity className="mr-2 h-4 w-4" />
                Overview
              </TabsTrigger>
              <TabsTrigger value="agents">
                <IconRobot className="mr-2 h-4 w-4" />
                Agents
              </TabsTrigger>
              <TabsTrigger value="chat">
                <IconMessageCircle className="mr-2 h-4 w-4" />
                Chat
              </TabsTrigger>
            </TabsList>
          </div>
          
          <div className="px-6 py-6">
            <TabsContent value="overview" className="mt-0 space-y-6">
              {/* System Status */}
              <Card>
                <CardHeader>
                  <CardTitle>System Status</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
                    <div className="text-center">
                      <div className="text-2xl font-bold">{statistics?.enabled_agents || availableAgents.length}</div>
                      <div className="text-sm text-muted-foreground">Enabled Agents</div>
                    </div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-blue-600">
                        {statistics?.total_executions || 0}
                      </div>
                      <div className="text-sm text-muted-foreground">Total Executions</div>
                    </div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-green-600">
                        {statistics?.executions_last_24h || 0}
                      </div>
                      <div className="text-sm text-muted-foreground">Last 24h</div>
                    </div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-purple-600">
                        {statistics?.success_rate || 0}%
                      </div>
                      <div className="text-sm text-muted-foreground">Success Rate</div>
                    </div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-orange-600">
                        {Math.round((statistics?.avg_execution_time_ms || 0) / 1000)}s
                      </div>
                      <div className="text-sm text-muted-foreground">Avg Time</div>
                    </div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-cyan-600">
                        {statistics?.total_tokens_used || 0}
                      </div>
                      <div className="text-sm text-muted-foreground">Tokens Used</div>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Recent Activity */}
              <Card>
                <CardHeader>
                  <CardTitle>Recent Agent Activity</CardTitle>
                </CardHeader>
                <CardContent>
                  {recentActivity.length === 0 ? (
                    <div className="text-center py-8">
                      <IconActivity className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
                      <p className="text-muted-foreground">No recent activity</p>
                      <p className="text-sm text-muted-foreground mt-2">
                        Activity will appear here when agents process tasks
                      </p>
                    </div>
                  ) : (
                    <ScrollArea className="h-[300px]">
                      <div className="space-y-4">
                        {recentActivity.map((activity, idx) => (
                          <div key={activity.id || idx} className="flex items-start gap-3 p-3 rounded-lg bg-muted/50">
                            <div className={`h-2 w-2 rounded-full mt-2 ${
                              activity.status === 'completed' ? 'bg-green-500' :
                              activity.status === 'failed' ? 'bg-red-500' :
                              activity.status === 'running' ? 'bg-blue-500' : 'bg-gray-400'
                            }`} />
                            <div className="flex-1 min-w-0">
                              <div className="flex items-start justify-between gap-2">
                                <div className="min-w-0">
                                  <p className="font-medium text-sm">{activity.agent_name}</p>
                                  <p className="text-sm text-muted-foreground capitalize">{activity.action}</p>
                                  {activity.document_id && (
                                    <p className="text-xs text-muted-foreground mt-1">
                                      Document: {activity.document_id.slice(0, 8)}...
                                    </p>
                                  )}
                                  {activity.error_message && (
                                    <p className="text-xs text-red-600 mt-1">
                                      Error: {activity.error_message}
                                    </p>
                                  )}
                                </div>
                                <div className="text-right shrink-0">
                                  <Badge variant={
                                    activity.status === 'completed' ? 'default' :
                                    activity.status === 'failed' ? 'destructive' :
                                    activity.status === 'running' ? 'secondary' : 'outline'
                                  } className="text-xs">
                                    {activity.status}
                                  </Badge>
                                  {activity.created_at && (
                                    <p className="text-xs text-muted-foreground mt-1">
                                      {new Date(activity.created_at).toLocaleTimeString()}
                                    </p>
                                  )}
                                  {activity.execution_time_ms && (
                                    <p className="text-xs text-muted-foreground">
                                      {Math.round(activity.execution_time_ms / 1000)}s
                                    </p>
                                  )}
                                </div>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </ScrollArea>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="agents" className="mt-0">
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {availableAgents.map(agent => {
                  const Icon = agent.icon
                  return (
                    <Card key={agent.id} className="h-full">
                      <CardHeader>
                        <div className="flex items-start justify-between">
                          <div className="flex items-center gap-3">
                            <div className={`p-2 rounded-lg text-white ${agent.color}`}>
                              <Icon className="h-5 w-5" />
                            </div>
                            <div>
                              <CardTitle className="text-lg">{agent.name}</CardTitle>
                              <Badge variant="outline" className="mt-1">
                                {agent.source.toUpperCase()}
                              </Badge>
                            </div>
                          </div>
                          <div className={`h-2 w-2 rounded-full ${
                            agent.status === 'active' ? 'bg-green-500' : 'bg-gray-400'
                          }`} />
                        </div>
                      </CardHeader>
                      <CardContent className="space-y-4">
                        <p className="text-sm text-muted-foreground">
                          {agent.description}
                        </p>
                        
                        {agent.capabilities && agent.capabilities.length > 0 && (
                          <div>
                            <div className="text-sm font-medium mb-2">Capabilities</div>
                            <div className="flex flex-wrap gap-1">
                              {agent.capabilities.slice(0, 3).map((cap: string, idx: number) => (
                                <Badge key={idx} variant="secondary" className="text-xs">
                                  {cap}
                                </Badge>
                              ))}
                              {agent.capabilities.length > 3 && (
                                <Badge variant="secondary" className="text-xs">
                                  +{agent.capabilities.length - 3} more
                                </Badge>
                              )}
                            </div>
                          </div>
                        )}
                        
                        <div className="flex gap-2">
                          <Button 
                            size="sm" 
                            variant="outline" 
                            onClick={() => testAgent(agent.id)}
                            className="flex-1"
                          >
                            <IconPlayerPlay className="mr-2 h-3 w-3" />
                            Test
                          </Button>
                          <Button 
                            size="sm" 
                            onClick={() => {
                              setSelectedAgent(agent.id)
                              setActiveTab('chat')
                            }}
                            className="flex-1"
                          >
                            <IconMessageCircle className="mr-2 h-3 w-3" />
                            Chat
                          </Button>
                        </div>
                      </CardContent>
                    </Card>
                  )
                })}
              </div>
            </TabsContent>

            <TabsContent value="chat" className="mt-0">
              <Card className="h-[600px]">
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle>Agent Chat</CardTitle>
                    <Select value={selectedAgent} onValueChange={setSelectedAgent}>
                      <SelectTrigger className="w-[200px]">
                        <SelectValue placeholder="Select agent" />
                      </SelectTrigger>
                      <SelectContent>
                        {availableAgents.map(agent => (
                          <SelectItem key={agent.id} value={agent.id}>
                            {agent.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </CardHeader>
                <CardContent className="h-full flex flex-col">
                  {!selectedAgent ? (
                    <div className="flex-1 flex items-center justify-center">
                      <div className="text-center">
                        <IconMessageCircle className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
                        <p className="text-muted-foreground">Select an agent to start chatting</p>
                      </div>
                    </div>
                  ) : (
                    <>
                      <ScrollArea className="flex-1 mb-4">
                        <div className="space-y-4">
                          {chatMessages.map((message, idx) => (
                            <div key={idx} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                              <div className={`max-w-[80%] p-3 rounded-lg ${
                                message.role === 'user' 
                                  ? 'bg-primary text-primary-foreground' 
                                  : 'bg-muted'
                              }`}>
                                <p className="text-sm">{message.content}</p>
                                <div className="text-xs opacity-70 mt-1">
                                  {new Date(message.timestamp).toLocaleTimeString()}
                                </div>
                              </div>
                            </div>
                          ))}
                          {chatLoading && (
                            <div className="flex justify-start">
                              <div className="bg-muted p-3 rounded-lg">
                                <IconLoader2 className="h-4 w-4 animate-spin" />
                              </div>
                            </div>
                          )}
                        </div>
                      </ScrollArea>
                      
                      <div className="flex gap-2">
                        <Input
                          value={chatInput}
                          onChange={(e) => setChatInput(e.target.value)}
                          placeholder="Type your message..."
                          onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && sendChatMessage()}
                          disabled={chatLoading}
                        />
                        <Button onClick={sendChatMessage} disabled={chatLoading || !chatInput.trim()}>
                          Send
                        </Button>
                      </div>
                    </>
                  )}
                </CardContent>
              </Card>
            </TabsContent>
          </div>
        </Tabs>
      </div>
    </div>
  )
}