"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"
import {
  IconFileText,
  IconSignature,
  IconScale,
  IconChartBar,
  IconRoute,
  IconClock,
  IconCheck,
  IconAlertCircle,
  IconLoader2,
  IconEye,
  IconArrowRight,
  IconRobot
} from "@tabler/icons-react"
import { getFileIcon, getRelativeTime } from "@/lib/document-utils"
import { useDocumentService } from "@/lib/services/document.service"
import { useAgentService } from "@/lib/services/agent.service"

interface AssignedAgent {
  id: string
  name: string
  type: string
  status: 'standby' | 'active' | 'processing' | 'completed' | 'error'
  progress?: number
  message?: string
  icon: any
  color: string
}

interface DocumentWithAgents {
  id: string
  name: string
  type: string
  fileType: string
  mimeType?: string
  isSignable: boolean
  status: 'pending' | 'processing' | 'completed'
  agents: AssignedAgent[]
  uploadedAt: string
  tags?: string[]
}

interface AgentAssignmentProps {
  onDocumentClick?: (doc: DocumentWithAgents) => void
  className?: string
}

const getAgentIcon = (agentType: string) => {
  switch (agentType) {
    case 'signature':
    case 'digital_signature':
      return IconSignature
    case 'compliance':
    case 'legal_compliance':
      return IconScale
    case 'workflow':
      return IconFileText
    case 'analytics':
    case 'financial_analyzer':
      return IconChartBar
    case 'document_analyzer':
      return IconFileText
    case 'rag_assistant':
      return IconRobot
    default:
      return IconRobot
  }
}

const getAgentColor = (agentType: string) => {
  switch (agentType) {
    case 'signature':
    case 'digital_signature':
      return 'bg-blue-500'
    case 'compliance':
    case 'legal_compliance':
      return 'bg-green-500'
    case 'workflow':
      return 'bg-orange-500'
    case 'analytics':
    case 'financial_analyzer':
      return 'bg-pink-500'
    case 'document_analyzer':
      return 'bg-purple-500'
    case 'rag_assistant':
      return 'bg-indigo-500'
    default:
      return 'bg-gray-500'
  }
}

const getDocumentAgents = (docType: string, tags: string[]): AssignedAgent[] => {
  const agents: AssignedAgent[] = []
  
  // Determine agents based on document type and tags
  const isSignable = tags.includes('signable') || tags.includes('contract') || tags.includes('agreement')
  const isLegal = tags.includes('legal') || tags.includes('contract') || tags.includes('compliance')
  const isFinancial = tags.includes('financial') || tags.includes('invoice') || tags.includes('report')
  
  if (isSignable) {
    agents.push({
      id: 'sig-' + Math.random().toString(36).substr(2, 9),
      name: 'Digital Signature Agent',
      type: 'digital_signature',
      status: Math.random() > 0.5 ? 'processing' : 'standby',
      progress: Math.floor(Math.random() * 100),
      message: 'Managing signature workflow',
      icon: IconSignature,
      color: 'bg-blue-500'
    })
  }
  
  if (isLegal) {
    agents.push({
      id: 'comp-' + Math.random().toString(36).substr(2, 9),
      name: 'Legal Compliance Agent',
      type: 'legal_compliance',
      status: Math.random() > 0.7 ? 'completed' : 'active',
      message: 'Checking legal requirements',
      icon: IconScale,
      color: 'bg-green-500'
    })
  }
  
  if (isFinancial) {
    agents.push({
      id: 'fin-' + Math.random().toString(36).substr(2, 9),
      name: 'Financial Analysis Agent',
      type: 'financial_analyzer',
      status: 'active',
      message: 'Analyzing financial data',
      icon: IconChartBar,
      color: 'bg-pink-500'
    })
  }
  
  // Always add document analyzer for insights
  agents.push({
    id: 'doc-' + Math.random().toString(36).substr(2, 9),
    name: 'Document Analyzer',
    type: 'document_analyzer',
    status: 'completed',
    message: 'Content analyzed',
    icon: IconFileText,
    color: 'bg-purple-500'
  })
  
  return agents
}

export function AgentAssignment({
  onDocumentClick,
  className
}: AgentAssignmentProps) {
  const documentService = useDocumentService()
  const agentService = useAgentService()
  const [documents, setDocuments] = useState<DocumentWithAgents[]>([])
  const [selectedDoc, setSelectedDoc] = useState<DocumentWithAgents | null>(null)
  const [filter, setFilter] = useState<'all' | 'processing' | 'completed'>('all')
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  
  // Load documents and transform them with agent assignments
  const loadDocuments = async () => {
    setIsLoading(true)
    setError(null)
    
    try {
      const response = await documentService.getDocuments({
        per_page: 20,
        page: 1
      })
      
      if (response.error) {
        throw new Error(response.error)
      }
      
      if (response.data?.documents) {
        // Transform documents to include agent assignments
        const docsWithAgents: DocumentWithAgents[] = response.data.documents.map(doc => {
          const tags = doc.tags || []
          const docType = tags[0] || 'general'
          const agents = getDocumentAgents(docType, tags)
          
          // Determine document status based on agent statuses
          let docStatus: DocumentWithAgents['status'] = 'pending'
          if (agents.some(a => a.status === 'processing')) {
            docStatus = 'processing'
          } else if (agents.every(a => a.status === 'completed')) {
            docStatus = 'completed'
          }
          
          return {
            id: doc.id,
            name: doc.filename,
            type: docType,
            fileType: doc.file_type || 'unknown',
            mimeType: doc.mime_type,
            isSignable: tags.includes('signable') || tags.includes('contract'),
            status: docStatus,
            agents: agents,
            uploadedAt: doc.created_at,
            tags: tags
          }
        })
        
        setDocuments(docsWithAgents)
      }
    } catch (err) {
      console.error('Failed to load documents:', err)
      setError(err instanceof Error ? err.message : 'Failed to load documents')
    } finally {
      setIsLoading(false)
    }
  }
  
  useEffect(() => {
    loadDocuments()
  }, [])
  
  const getStatusIcon = (status: AssignedAgent['status']) => {
    switch (status) {
      case 'processing':
        return <IconLoader2 className="h-3 w-3 animate-spin" />
      case 'active':
        return <div className="h-2 w-2 bg-blue-500 rounded-full animate-pulse" />
      case 'completed':
        return <IconCheck className="h-3 w-3 text-green-600" />
      case 'error':
        return <IconAlertCircle className="h-3 w-3 text-red-600" />
      default:
        return <IconClock className="h-3 w-3 text-gray-400" />
    }
  }
  
  const getDocumentStatusColor = (status: DocumentWithAgents['status']) => {
    switch (status) {
      case 'processing':
        return 'border-blue-500 bg-blue-50 dark:bg-blue-950/20'
      case 'completed':
        return 'border-green-500 bg-green-50 dark:bg-green-950/20'
      default:
        return 'border-gray-300 bg-gray-50 dark:bg-gray-950/20'
    }
  }
  
  const filteredDocs = documents.filter(doc => {
    if (filter === 'all') return true
    return doc.status === filter
  })
  
  const handleDocumentSelect = (doc: DocumentWithAgents) => {
    setSelectedDoc(doc)
    if (onDocumentClick) {
      onDocumentClick(doc)
    }
  }

  if (isLoading) {
    return (
      <div className={cn("grid grid-cols-1 lg:grid-cols-3 gap-6", className)}>
        <div className="lg:col-span-2">
          <Card>
            <CardHeader>
              <Skeleton className="h-6 w-48" />
              <Skeleton className="h-4 w-64 mt-2" />
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {[1, 2, 3].map(i => (
                  <Skeleton key={i} className="h-32" />
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
        <div>
          <Card>
            <CardHeader>
              <Skeleton className="h-5 w-32" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-64" />
            </CardContent>
          </Card>
        </div>
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
              <h3 className="text-lg font-semibold mb-2">Failed to load documents</h3>
              <p className="text-muted-foreground mb-4">{error}</p>
              <Button onClick={loadDocuments} variant="outline">
                Try Again
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }
  
  return (
    <div className={cn("grid grid-cols-1 lg:grid-cols-3 gap-6", className)}>
      {/* Documents List */}
      <div className="lg:col-span-2">
        <Card>
          <CardHeader>
            <CardTitle>Documents & Agent Assignments</CardTitle>
            <CardDescription>
              Real-time view of documents being processed by AI agents
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Tabs value={filter} onValueChange={(v) => setFilter(v as any)}>
              <TabsList className="grid w-full grid-cols-3">
                <TabsTrigger value="all">All Documents</TabsTrigger>
                <TabsTrigger value="processing">Processing</TabsTrigger>
                <TabsTrigger value="completed">Completed</TabsTrigger>
              </TabsList>
              
              <TabsContent value={filter} className="mt-4">
                <ScrollArea className="h-[500px] pr-4">
                  <div className="space-y-4">
                    {filteredDocs.length === 0 ? (
                      <div className="text-center py-12">
                        <IconFileText className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
                        <p className="text-muted-foreground">
                          {filter === 'all' 
                            ? 'No documents uploaded yet' 
                            : `No ${filter} documents`}
                        </p>
                      </div>
                    ) : filteredDocs.map(doc => (
                      <div
                        key={doc.id}
                        className={cn(
                          "p-4 rounded-lg border-2 cursor-pointer transition-all hover:shadow-md",
                          getDocumentStatusColor(doc.status),
                          selectedDoc?.id === doc.id && "ring-2 ring-primary"
                        )}
                        onClick={() => handleDocumentSelect(doc)}
                      >
                        <div className="flex items-start gap-3">
                          {/* File Icon */}
                          <div className="flex-shrink-0">
                            {getFileIcon(doc.fileType, doc.mimeType, doc.name)}
                          </div>
                          
                          {/* Document Info */}
                          <div className="flex-1 min-w-0">
                            <div className="flex items-start justify-between mb-2">
                              <div>
                                <h4 className="font-medium truncate">{doc.name}</h4>
                                <div className="flex items-center gap-2 mt-1">
                                  <Badge variant="outline" className="text-xs">
                                    {doc.type}
                                  </Badge>
                                  {doc.isSignable && (
                                    <Badge variant="secondary" className="text-xs">
                                      <IconSignature className="h-3 w-3 mr-1" />
                                      Signable
                                    </Badge>
                                  )}
                                  <span className="text-xs text-muted-foreground">
                                    {getRelativeTime(doc.uploadedAt)}
                                  </span>
                                </div>
                              </div>
                              <Button variant="ghost" size="sm">
                                <IconEye className="h-4 w-4" />
                              </Button>
                            </div>
                            
                            {/* Assigned Agents */}
                            <div className="flex flex-wrap gap-2 mt-3">
                              {doc.agents.map(agent => {
                                const Icon = agent.icon
                                return (
                                  <div
                                    key={agent.id}
                                    className={cn(
                                      "flex items-center gap-1.5 px-2 py-1 rounded-full text-xs",
                                      "bg-white dark:bg-gray-800 border",
                                      agent.status === 'processing' && "border-blue-300",
                                      agent.status === 'completed' && "border-green-300",
                                      agent.status === 'active' && "border-orange-300",
                                      agent.status === 'standby' && "border-gray-300"
                                    )}
                                  >
                                    <div className={cn("p-1 rounded-full text-white", agent.color)}>
                                      <Icon className="h-2.5 w-2.5" />
                                    </div>
                                    <span className="font-medium">{agent.name}</span>
                                    {getStatusIcon(agent.status)}
                                  </div>
                                )
                              })}
                            </div>
                            
                            {/* Progress for processing docs */}
                            {doc.status === 'processing' && (
                              <div className="mt-3 space-y-1">
                                {doc.agents
                                  .filter(a => a.progress !== undefined)
                                  .map(agent => (
                                    <div key={agent.id} className="space-y-1">
                                      <div className="flex justify-between text-xs">
                                        <span className="text-muted-foreground">{agent.name}</span>
                                        <span>{agent.progress}%</span>
                                      </div>
                                      <div className="h-1.5 bg-gray-200 rounded-full overflow-hidden">
                                        <div 
                                          className="h-full bg-blue-500 transition-all"
                                          style={{ width: `${agent.progress}%` }}
                                        />
                                      </div>
                                    </div>
                                  ))}
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </ScrollArea>
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      </div>
      
      {/* Agent Details Panel */}
      <div>
        <Card className="sticky top-6">
          <CardHeader>
            <CardTitle className="text-lg">Agent Activity</CardTitle>
            <CardDescription>
              {selectedDoc ? `Details for ${selectedDoc.name}` : 'Select a document to view details'}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {selectedDoc ? (
              <div className="space-y-4">
                {selectedDoc.agents.map(agent => {
                  const Icon = agent.icon
                  return (
                    <div key={agent.id} className="space-y-3">
                      <div className="flex items-center gap-3">
                        <div className={cn("p-2 rounded-lg text-white", agent.color)}>
                          <Icon className="h-5 w-5" />
                        </div>
                        <div className="flex-1">
                          <h4 className="font-medium">{agent.name}</h4>
                          <p className="text-xs text-muted-foreground">
                            Status: {agent.status}
                          </p>
                        </div>
                        {getStatusIcon(agent.status)}
                      </div>
                      
                      {agent.message && (
                        <div className="ml-11 p-2 bg-muted rounded-md">
                          <p className="text-sm">{agent.message}</p>
                        </div>
                      )}
                      
                      {agent.progress !== undefined && (
                        <div className="ml-11">
                          <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
                            <div 
                              className="h-full bg-blue-500 transition-all"
                              style={{ width: `${agent.progress}%` }}
                            />
                          </div>
                        </div>
                      )}
                    </div>
                  )
                })}
                
                <div className="pt-4 border-t">
                  <Button className="w-full" size="sm">
                    <IconArrowRight className="mr-2 h-4 w-4" />
                    View Full Details
                  </Button>
                </div>
              </div>
            ) : (
              <div className="text-center py-8">
                <IconRoute className="h-12 w-12 text-muted-foreground mx-auto mb-3" />
                <p className="text-sm text-muted-foreground">
                  Select a document to see agent assignments and activity
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}