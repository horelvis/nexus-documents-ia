"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"
import {
  IconRobot,
  IconSignature,
  IconScale,
  IconChartBar,
  IconRoute,
  IconFileText,
  IconActivity,
  IconTrendingUp,
  IconClock,
  IconCheck,
  IconAlertCircle,
  IconLoader2,
  IconRefresh
} from "@tabler/icons-react"
import { getRelativeTime } from "@/lib/document-utils"
import { useAgentService, type Agent, type AgentServiceStatus } from "@/lib/services/agent.service"
import { Button } from "@/components/ui/button"

interface AgentMetrics extends Agent {
  icon: any
  color: string
  tasksCompleted: number
  avgResponseTime: number
  successRate: number
  currentLoad: number
}

interface AgentActivity {
  id: string
  agentId: string
  agentName: string
  action: string
  documentName?: string
  timestamp: string
  status: 'success' | 'error' | 'info'
  duration?: number
}

interface SystemHealth {
  totalAgents: number
  activeAgents: number
  averageSuccessRate: number
  totalTasksToday: number
  systemLoad: number
}

const getAgentIcon = (agentType: string) => {
  switch (agentType) {
    case 'digital_signature':
      return IconSignature
    case 'document_analyzer':
      return IconFileText
    case 'rag_assistant':
      return IconRobot
    case 'contract_analyzer':
      return IconScale
    case 'financial_analyzer':
      return IconChartBar
    case 'legal_compliance':
      return IconScale
    default:
      return IconRobot
  }
}

const getAgentColor = (agentType: string) => {
  switch (agentType) {
    case 'digital_signature':
      return 'bg-purple-500'
    case 'document_analyzer':
      return 'bg-blue-500'
    case 'rag_assistant':
      return 'bg-green-500'
    case 'contract_analyzer':
      return 'bg-orange-500'
    case 'financial_analyzer':
      return 'bg-yellow-500'
    case 'legal_compliance':
      return 'bg-red-500'
    default:
      return 'bg-gray-500'
  }
}

export function AgentDashboard({ className }: { className?: string }) {
  const agentService = useAgentService()
  const [agents, setAgents] = useState<AgentMetrics[]>([])
  const [activities, setActivities] = useState<AgentActivity[]>([])
  const [serviceStatus, setServiceStatus] = useState<AgentServiceStatus | null>(null)
  const [systemHealth, setSystemHealth] = useState<SystemHealth>({
    totalAgents: 0,
    activeAgents: 0,
    averageSuccessRate: 0,
    totalTasksToday: 0,
    systemLoad: 0
  })
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  
  // Load real agent data
  const loadAgentData = async () => {
    setIsLoading(true)
    setError(null)
    
    // Declare agentMetrics at the top of the function
    let agentMetrics: AgentMetrics[] = []
    
    try {
      // Fetch agents and service status in parallel
      const [agentsResponse, statusResponse] = await Promise.all([
        agentService.getAgents(),
        agentService.getAgentStatus()
      ])
      
      if (agentsResponse.error) {
        throw new Error(agentsResponse.error)
      }
      
      if (agentsResponse.data) {
        // Handle the response structure from /list endpoint
        const agentTypes = agentsResponse.data.available_types || agentsResponse.data
        
        // Transform agent types to AgentMetrics
        agentMetrics = Object.entries(agentTypes).map(([key, value]: [string, any]) => ({
          id: key,
          name: value.name || key,
          description: value.description || '',
          agent_type: key,
          type: key,
          status: 'active', // Default status since types don't have runtime status
          icon: getAgentIcon(key),
          color: getAgentColor(key),
          // TODO: Connect to real agent statistics from API
          tasksCompleted: 0, // Placeholder - needs API endpoint for agent stats
          avgResponseTime: 0, // Placeholder - needs API endpoint for agent metrics
          successRate: 0, // Placeholder - needs API endpoint for agent performance
          currentLoad: 0,
          last_activity: new Date().toISOString(),
          updated_at: new Date().toISOString()
        }))
        setAgents(agentMetrics)
        
        // Update system health
        const activeAgents = agentMetrics.filter(a => a.status !== 'inactive')
        setSystemHealth({
          totalAgents: agentMetrics.length,
          activeAgents: activeAgents.length,
          averageSuccessRate: agentMetrics.reduce((acc, a) => acc + a.successRate, 0) / agentMetrics.length || 0,
          totalTasksToday: agentMetrics.reduce((acc, a) => acc + a.tasksCompleted, 0),
          systemLoad: statusResponse.data?.system_resources?.cpu_percent || 0
        })
      }
      
      if (statusResponse.data) {
        setServiceStatus(statusResponse.data)
        
        // TODO: Connect to real agent activity endpoint
        // Currently using agent metrics data as placeholder
        const activities: AgentActivity[] = agentMetrics.slice(0, 5).map((agent, index) => ({
          id: `activity-${index}`,
          agentId: agent.id,
          agentName: agent.name,
          action: 'Agent initialized',
          timestamp: agent.last_activity || agent.updated_at,
          status: 'success' as const,
          duration: 0 // Placeholder - needs real execution time from API
        }))
        setActivities(activities)
      }
    } catch (err) {
      console.error('Failed to load agent data:', err)
      setError(err instanceof Error ? err.message : 'Failed to load agent data')
    } finally {
      setIsLoading(false)
    }
  }
  
  const getAgentAction = (agentType: string): string => {
    const actions: Record<string, string[]> = {
      digital_signature: [
        'Signature workflow initiated',
        'Signature request sent',
        'All signatures collected'
      ],
      document_analyzer: [
        'Document analysis completed',
        'Content extraction finished',
        'Summary generated'
      ],
      rag_assistant: [
        'Knowledge retrieval completed',
        'Context search performed',
        'Q&A session started'
      ],
      contract_analyzer: [
        'Contract clauses analyzed',
        'Risk assessment completed',
        'Compliance check finished'
      ],
      financial_analyzer: [
        'Financial metrics calculated',
        'Trend analysis completed',
        'Report generated'
      ],
      legal_compliance: [
        'Compliance validation done',
        'Regulatory check completed',
        'Risk factors identified'
      ]
    }
    
    // TODO: This should come from actual agent execution logs
    const typeActions = actions[agentType] || ['Task completed']
    return typeActions[0] // Use first action as placeholder instead of random
  }
  
  // Load data on mount
  useEffect(() => {
    loadAgentData()
  }, [])
  
  const getStatusIcon = (status: AgentMetrics['status']) => {
    switch (status) {
      case 'busy':
        return <IconLoader2 className="h-4 w-4 animate-spin" />
      case 'active':
        return <div className="h-2 w-2 bg-green-500 rounded-full animate-pulse" />
      case 'error':
        return <IconAlertCircle className="h-4 w-4 text-red-500" />
      default:
        return <IconClock className="h-4 w-4 text-gray-400" />
    }
  }
  
  const getStatusColor = (status: AgentMetrics['status']) => {
    switch (status) {
      case 'busy':
        return 'text-blue-600 bg-blue-50 dark:bg-blue-950/30'
      case 'active':
        return 'text-green-600 bg-green-50 dark:bg-green-950/30'
      case 'error':
        return 'text-red-600 bg-red-50 dark:bg-red-950/30'
      default:
        return 'text-gray-600 bg-gray-50 dark:bg-gray-950/30'
    }
  }
  
  const getActivityIcon = (status: AgentActivity['status']) => {
    switch (status) {
      case 'success':
        return <IconCheck className="h-4 w-4 text-green-600" />
      case 'error':
        return <IconAlertCircle className="h-4 w-4 text-red-600" />
      default:
        return <IconActivity className="h-4 w-4 text-blue-600" />
    }
  }
  
  // Auto-refresh data every 30 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      loadAgentData()
    }, 30000)
    
    return () => clearInterval(interval)
  }, [])
  
  if (isLoading) {
    return (
      <div className={cn("space-y-6", className)}>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
          {[1, 2, 3, 4, 5].map(i => (
            <Card key={i}>
              <CardHeader className="pb-2">
                <Skeleton className="h-4 w-20" />
              </CardHeader>
              <CardContent>
                <Skeleton className="h-8 w-16 mb-2" />
                <Skeleton className="h-2 w-full" />
              </CardContent>
            </Card>
          ))}
        </div>
        <Card>
          <CardHeader>
            <Skeleton className="h-6 w-48" />
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {[1, 2, 3].map(i => (
                <Skeleton key={i} className="h-40" />
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }
  
  if (error) {
    return (
      <div className={cn("flex items-center justify-center min-h-[400px]", className)}>
        <Card className="max-w-md w-full">
          <CardContent className="pt-6">
            <div className="text-center">
              <IconAlertCircle className="h-12 w-12 text-red-500 mx-auto mb-4" />
              <h3 className="text-lg font-semibold mb-2">Failed to load agent data</h3>
              <p className="text-muted-foreground mb-4">{error}</p>
              <Button onClick={loadAgentData} variant="outline">
                <IconRefresh className="mr-2 h-4 w-4" />
                Try Again
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className={cn("space-y-6", className)}>
      {/* System Health Overview */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-semibold">Agent System Overview</h2>
        <Button 
          variant="outline" 
          size="sm"
          onClick={loadAgentData}
          disabled={isLoading}
        >
          <IconRefresh className={cn("mr-2 h-4 w-4", isLoading && "animate-spin")} />
          Refresh
        </Button>
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Total Agents</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{systemHealth.totalAgents}</div>
            <div className="flex items-center gap-1 mt-1">
              <div className="h-2 w-2 bg-green-500 rounded-full" />
              <span className="text-xs text-muted-foreground">
                {systemHealth.activeAgents} active
              </span>
            </div>
          </CardContent>
        </Card>
        
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Success Rate</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {systemHealth.averageSuccessRate.toFixed(1)}%
            </div>
            <Progress value={systemHealth.averageSuccessRate} className="h-1 mt-2" />
          </CardContent>
        </Card>
        
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Tasks Today</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{systemHealth.totalTasksToday}</div>
            <div className="flex items-center gap-1 mt-1 text-green-600">
              <IconTrendingUp className="h-3 w-3" />
              <span className="text-xs">+12% from yesterday</span>
            </div>
          </CardContent>
        </Card>
        
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>System Load</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {systemHealth.systemLoad.toFixed(0)}%
            </div>
            <Progress 
              value={systemHealth.systemLoad} 
              className={cn(
                "h-1 mt-2",
                systemHealth.systemLoad > 70 && "bg-red-200"
              )} 
            />
          </CardContent>
        </Card>
        
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Avg Response</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {agents.length > 0 
                ? (agents.reduce((acc, a) => acc + a.avgResponseTime, 0) / agents.length).toFixed(1)
                : '0'}s
            </div>
            <span className="text-xs text-muted-foreground">
              Across all agents
            </span>
          </CardContent>
        </Card>
      </div>
      
      {/* Agent Status Grid */}
      <Card>
        <CardHeader>
          <CardTitle>Agent Status & Performance</CardTitle>
          <CardDescription>
            Real-time monitoring of all AI agents in the system
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {agents.map(agent => {
              const Icon = agent.icon
              return (
                <div
                  key={agent.id}
                  className="p-4 rounded-lg border bg-card"
                >
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <div className={cn("p-2 rounded-lg text-white", agent.color)}>
                        <Icon className="h-5 w-5" />
                      </div>
                      <div>
                        <h4 className="font-medium">{agent.name}</h4>
                        <div className={cn(
                          "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs mt-1",
                          getStatusColor(agent.status)
                        )}>
                          {getStatusIcon(agent.status)}
                          <span className="capitalize">{agent.status}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                  
                  <div className="space-y-3">
                    <div>
                      <div className="flex justify-between text-sm mb-1">
                        <span className="text-muted-foreground">Current Load</span>
                        <span className="font-medium">{agent.currentLoad}%</span>
                      </div>
                      <Progress 
                        value={agent.currentLoad} 
                        className={cn(
                          "h-1.5",
                          agent.currentLoad > 80 && "bg-red-200"
                        )}
                      />
                    </div>
                    
                    <div className="grid grid-cols-2 gap-3 text-sm">
                      <div>
                        <p className="text-muted-foreground">Tasks</p>
                        <p className="font-medium">{agent.tasksCompleted}</p>
                      </div>
                      <div>
                        <p className="text-muted-foreground">Success</p>
                        <p className="font-medium">{agent.successRate}%</p>
                      </div>
                      <div>
                        <p className="text-muted-foreground">Avg Time</p>
                        <p className="font-medium">{agent.avgResponseTime}s</p>
                      </div>
                      <div>
                        <p className="text-muted-foreground">Last Active</p>
                        <p className="font-medium text-xs">
                          {agent.last_activity ? getRelativeTime(agent.last_activity) : 'Never'}
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
          
          {agents.length === 0 && (
            <div className="text-center py-12">
              <IconRobot className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
              <p className="text-muted-foreground">No agents configured yet</p>
            </div>
          )}
        </CardContent>
      </Card>
      
      {/* Recent Activity */}
      <Card>
        <CardHeader>
          <CardTitle>Recent Agent Activity</CardTitle>
          <CardDescription>
            Latest actions performed by AI agents
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ScrollArea className="h-[300px]">
            <div className="space-y-3">
              {activities.length === 0 ? (
                <div className="text-center py-12">
                  <IconActivity className="h-8 w-8 text-muted-foreground mx-auto mb-3" />
                  <p className="text-sm text-muted-foreground">No recent activity</p>
                </div>
              ) : activities.map(activity => (
                <div
                  key={activity.id}
                  className="flex items-start gap-3 p-3 rounded-lg bg-muted/50"
                >
                  <div className="mt-0.5">
                    {getActivityIcon(activity.status)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="font-medium text-sm">{activity.agentName}</p>
                        <p className="text-sm text-muted-foreground">{activity.action}</p>
                        {activity.documentName && (
                          <p className="text-xs text-muted-foreground mt-1">
                            Document: {activity.documentName}
                          </p>
                        )}
                      </div>
                      <div className="text-right shrink-0">
                        <Badge variant="outline" className="text-xs">
                          {getRelativeTime(activity.timestamp)}
                        </Badge>
                        {activity.duration && (
                          <p className="text-xs text-muted-foreground mt-1">
                            {activity.duration}s
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  )
}