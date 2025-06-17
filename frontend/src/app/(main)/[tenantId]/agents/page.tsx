'use client'

import React, { useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  IconSparkles,
  IconSearch,
  IconRobot,
  IconBrain,
  IconArrowRight,
  IconUpload,
  IconRoute,
  IconDashboard,
  IconFileText
} from '@tabler/icons-react'
import { AgentRouter } from '@/components/agents/agent-router'
import { AgentAssignment } from '@/components/agents/agent-assignment'
import { AgentDashboard } from '@/components/agents/agent-dashboard'
import { useUpload } from '@/contexts/upload-context'

export default function AgentsPage() {
  const params = useParams()
  const router = useRouter()
  const tenantId = params.tenantId as string
  const { openUploadDialog } = useUpload()
  const [activeTab, setActiveTab] = useState('overview')
  const [selectedDocument, setSelectedDocument] = useState<any>(null)

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-6 py-4 border-b">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <IconRobot className="h-6 w-6 text-blue-500" />
              Multi-Agent System
            </h1>
            <p className="text-muted-foreground text-sm mt-1">
              Intelligent document processing with specialized AI agents
            </p>
          </div>
          <Button onClick={openUploadDialog} className="flex items-center gap-2">
            <IconUpload className="h-4 w-4" />
            Upload Document
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        <Tabs value={activeTab} onValueChange={setActiveTab} className="h-full">
          <div className="px-6 pt-4">
            <TabsList className="grid w-full grid-cols-3 max-w-[600px]">
              <TabsTrigger value="overview" className="flex items-center gap-2">
                <IconDashboard className="h-4 w-4" />
                Overview
              </TabsTrigger>
              <TabsTrigger value="router" className="flex items-center gap-2">
                <IconRoute className="h-4 w-4" />
                Router Analysis
              </TabsTrigger>
              <TabsTrigger value="assignments" className="flex items-center gap-2">
                <IconFileText className="h-4 w-4" />
                Documents
              </TabsTrigger>
            </TabsList>
          </div>
          
          <div className="px-6 py-6">
            <TabsContent value="overview" className="mt-0">
              <AgentDashboard />
            </TabsContent>
            
            <TabsContent value="router" className="mt-0">
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2">
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <IconBrain className="h-5 w-5" />
                        How Agent Router Works
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="space-y-3">
                        <div className="flex items-start gap-3">
                          <div className="w-8 h-8 rounded-full bg-purple-100 text-purple-600 flex items-center justify-center text-sm font-medium shrink-0">
                            1
                          </div>
                          <div>
                            <h4 className="font-medium">Document Analysis</h4>
                            <p className="text-sm text-muted-foreground">
                              The Router Agent analyzes your document to determine its type, content, and processing requirements.
                            </p>
                          </div>
                        </div>
                        
                        <div className="flex items-start gap-3">
                          <div className="w-8 h-8 rounded-full bg-purple-100 text-purple-600 flex items-center justify-center text-sm font-medium shrink-0">
                            2
                          </div>
                          <div>
                            <h4 className="font-medium">Agent Assignment</h4>
                            <p className="text-sm text-muted-foreground">
                              Based on the analysis, specialized agents are automatically assigned to handle specific aspects of your document.
                            </p>
                          </div>
                        </div>
                        
                        <div className="flex items-start gap-3">
                          <div className="w-8 h-8 rounded-full bg-purple-100 text-purple-600 flex items-center justify-center text-sm font-medium shrink-0">
                            3
                          </div>
                          <div>
                            <h4 className="font-medium">Intelligent Processing</h4>
                            <p className="text-sm text-muted-foreground">
                              Each agent works on its specialized task, whether it's managing signatures, checking compliance, or generating analytics.
                            </p>
                          </div>
                        </div>
                      </div>
                      
                      <Separator />
                      
                      <div className="bg-blue-50 dark:bg-blue-950/20 rounded-lg p-4">
                        <h4 className="font-medium mb-2 flex items-center gap-2">
                          <IconSparkles className="h-4 w-4" />
                          Available Agents
                        </h4>
                        <ul className="space-y-2 text-sm">
                          <li className="flex items-start gap-2">
                            <span className="font-medium text-blue-600">Signature Agent:</span>
                            <span className="text-muted-foreground">Manages digital signature workflows and tracks signing progress</span>
                          </li>
                          <li className="flex items-start gap-2">
                            <span className="font-medium text-green-600">Compliance Agent:</span>
                            <span className="text-muted-foreground">Validates legal requirements and checks document compliance</span>
                          </li>
                          <li className="flex items-start gap-2">
                            <span className="font-medium text-orange-600">Workflow Agent:</span>
                            <span className="text-muted-foreground">Orchestrates document processes and approval chains</span>
                          </li>
                          <li className="flex items-start gap-2">
                            <span className="font-medium text-pink-600">Analytics Agent:</span>
                            <span className="text-muted-foreground">Generates insights and reports from document data</span>
                          </li>
                        </ul>
                      </div>
                    </CardContent>
                  </Card>
                </div>
                
                <div>
                  <AgentRouter 
                    documentId={selectedDocument?.id}
                    documentName={selectedDocument?.name || "Sample_Contract.pdf"}
                    documentType={selectedDocument?.type || "legal"}
                    onAnalysisComplete={(analysis) => {
                      console.log('Analysis complete:', analysis)
                    }}
                  />
                </div>
              </div>
            </TabsContent>
            
            <TabsContent value="assignments" className="mt-0">
              <AgentAssignment 
                onDocumentClick={(doc) => {
                  setSelectedDocument(doc)
                  setActiveTab('router')
                }}
              />
            </TabsContent>
          </div>
        </Tabs>
      </div>
    </div>
  )
}