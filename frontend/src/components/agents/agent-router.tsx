"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { cn } from "@/lib/utils"
import {
  IconRobot,
  IconFileText,
  IconSignature,
  IconScale,
  IconChartBar,
  IconRoute,
  IconArrowDown,
  IconLoader2,
  IconCheck,
  IconAlertCircle
} from "@tabler/icons-react"

interface AgentType {
  id: string
  name: string
  type: 'router' | 'signature' | 'compliance' | 'workflow' | 'analytics'
  icon: any
  color: string
  description: string
  status: 'idle' | 'active' | 'processing' | 'error'
}

interface DocumentAnalysis {
  documentType: string
  isSignable: boolean
  requiredAgents: string[]
  confidence: number
  executionType: 'sequential' | 'parallel'
}

interface AgentRouterProps {
  documentId?: string
  documentName?: string
  documentType?: string
  onAnalysisComplete?: (analysis: DocumentAnalysis) => void
  className?: string
}

const AGENT_TYPES: AgentType[] = [
  {
    id: 'router',
    name: 'Router Agent',
    type: 'router',
    icon: IconRoute,
    color: 'bg-gradient-to-br from-purple-500 to-purple-600',
    description: 'Analyzes and classifies documents',
    status: 'active'
  },
  {
    id: 'signature',
    name: 'Signature Agent',
    type: 'signature',
    icon: IconSignature,
    color: 'bg-gradient-to-br from-blue-500 to-blue-600',
    description: 'Manages digital signature workflows',
    status: 'idle'
  },
  {
    id: 'compliance',
    name: 'Compliance Agent',
    type: 'compliance',
    icon: IconScale,
    color: 'bg-gradient-to-br from-green-500 to-green-600',
    description: 'Validates legal requirements',
    status: 'idle'
  },
  {
    id: 'workflow',
    name: 'Workflow Agent',
    type: 'workflow',
    icon: IconFileText,
    color: 'bg-gradient-to-br from-orange-500 to-orange-600',
    description: 'Orchestrates document processes',
    status: 'idle'
  },
  {
    id: 'analytics',
    name: 'Analytics Agent',
    type: 'analytics',
    icon: IconChartBar,
    color: 'bg-gradient-to-br from-pink-500 to-pink-600',
    description: 'Generates insights and reports',
    status: 'idle'
  }
]

export function AgentRouter({
  documentId,
  documentName,
  documentType,
  onAnalysisComplete,
  className
}: AgentRouterProps) {
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [analysisProgress, setAnalysisProgress] = useState(0)
  const [activeAgents, setActiveAgents] = useState<string[]>([])
  const [analysis, setAnalysis] = useState<DocumentAnalysis | null>(null)
  const [agents, setAgents] = useState<AgentType[]>(AGENT_TYPES)

  const analyzeDocument = async () => {
    setIsAnalyzing(true)
    setAnalysisProgress(0)
    setActiveAgents([])
    setAnalysis(null)
    
    // Update router agent status
    updateAgentStatus('router', 'processing')
    
    // Simulate analysis progress
    const progressInterval = setInterval(() => {
      setAnalysisProgress(prev => {
        if (prev >= 100) {
          clearInterval(progressInterval)
          return 100
        }
        return prev + 10
      })
    }, 200)
    
    // Simulate analysis result
    setTimeout(() => {
      const mockAnalysis: DocumentAnalysis = {
        documentType: documentType || 'legal',
        isSignable: true,
        requiredAgents: ['signature', 'compliance', 'workflow'],
        confidence: 0.95,
        executionType: 'sequential'
      }
      
      setAnalysis(mockAnalysis)
      setActiveAgents(mockAnalysis.requiredAgents)
      
      // Update agent statuses
      updateAgentStatus('router', 'active')
      mockAnalysis.requiredAgents.forEach(agentId => {
        updateAgentStatus(agentId, 'active')
      })
      
      setIsAnalyzing(false)
      
      if (onAnalysisComplete) {
        onAnalysisComplete(mockAnalysis)
      }
    }, 2000)
  }
  
  const updateAgentStatus = (agentId: string, status: AgentType['status']) => {
    setAgents(prev => prev.map(agent => 
      agent.id === agentId ? { ...agent, status } : agent
    ))
  }
  
  const getStatusIcon = (status: AgentType['status']) => {
    switch (status) {
      case 'processing':
        return <IconLoader2 className="h-3 w-3 animate-spin" />
      case 'active':
        return <IconCheck className="h-3 w-3" />
      case 'error':
        return <IconAlertCircle className="h-3 w-3" />
      default:
        return null
    }
  }
  
  const getStatusColor = (status: AgentType['status']) => {
    switch (status) {
      case 'processing':
        return 'bg-blue-500'
      case 'active':
        return 'bg-green-500'
      case 'error':
        return 'bg-red-500'
      default:
        return 'bg-gray-400'
    }
  }

  return (
    <Card className={cn("overflow-hidden", className)}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <IconRoute className="h-5 w-5" />
          Agent Router Analysis
        </CardTitle>
        <CardDescription>
          {documentName ? `Analyzing: ${documentName}` : 'Upload a document to start analysis'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Router Agent */}
        <div className="flex flex-col items-center">
          <div className={cn(
            "relative p-4 rounded-lg text-white",
            agents[0].color
          )}>
            <IconRoute className="h-8 w-8" />
            {agents[0].status !== 'idle' && (
              <div className={cn(
                "absolute -top-1 -right-1 h-4 w-4 rounded-full flex items-center justify-center",
                getStatusColor(agents[0].status)
              )}>
                {getStatusIcon(agents[0].status)}
              </div>
            )}
          </div>
          <p className="mt-2 text-sm font-medium">Router Agent</p>
          <p className="text-xs text-muted-foreground">Document Classifier</p>
        </div>
        
        {/* Analysis Progress */}
        {isAnalyzing && (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span>Analyzing document...</span>
              <span>{analysisProgress}%</span>
            </div>
            <Progress value={analysisProgress} className="h-2" />
          </div>
        )}
        
        {/* Connection Line */}
        {(isAnalyzing || analysis) && (
          <div className="flex justify-center">
            <div className="w-0.5 h-8 bg-gradient-to-b from-purple-500 to-blue-500" />
          </div>
        )}
        
        {/* Analysis Result */}
        {analysis && (
          <div className="space-y-3">
            <div className="text-center space-y-1">
              <p className="text-sm font-medium">
                Document Type: <Badge variant="outline">{analysis.documentType}</Badge>
              </p>
              <p className="text-xs text-muted-foreground">
                Confidence: {(analysis.confidence * 100).toFixed(0)}%
              </p>
            </div>
            
            <div className="flex justify-center">
              <IconArrowDown className="h-4 w-4 text-muted-foreground" />
            </div>
          </div>
        )}
        
        {/* Assigned Agents */}
        <div className="grid grid-cols-2 gap-3">
          {agents.slice(1).map(agent => {
            const Icon = agent.icon
            const isAssigned = activeAgents.includes(agent.id)
            
            return (
              <div
                key={agent.id}
                className={cn(
                  "relative p-3 rounded-lg border transition-all",
                  isAssigned 
                    ? "border-primary bg-primary/5" 
                    : "border-border bg-muted/20 opacity-50"
                )}
              >
                <div className="flex items-start gap-3">
                  <div className={cn(
                    "p-2 rounded-md text-white",
                    isAssigned ? agent.color : "bg-gray-400"
                  )}>
                    <Icon className="h-4 w-4" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{agent.name}</p>
                    <p className="text-xs text-muted-foreground truncate">
                      {agent.description}
                    </p>
                  </div>
                  {isAssigned && agent.status !== 'idle' && (
                    <div className={cn(
                      "h-5 w-5 rounded-full flex items-center justify-center",
                      getStatusColor(agent.status)
                    )}>
                      {getStatusIcon(agent.status)}
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
        
        {/* Action Button */}
        <Button 
          onClick={analyzeDocument} 
          disabled={!documentName || isAnalyzing}
          className="w-full"
        >
          {isAnalyzing ? (
            <>
              <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
              Analyzing...
            </>
          ) : (
            <>
              <IconRobot className="mr-2 h-4 w-4" />
              {analysis ? 'Re-analyze Document' : 'Start Analysis'}
            </>
          )}
        </Button>
      </CardContent>
    </Card>
  )
}