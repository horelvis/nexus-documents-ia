"use client"

import { useState, useEffect, useCallback } from "react"
import { useParams, useSearchParams } from "next/navigation"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import { ScrollArea } from "@/components/ui/scroll-area"
import { 
  IconSearch, 
  IconLoader2, 
  IconFile,
  IconSparkles,
  IconRobot,
  IconBrain,
  IconMessageCircle,
  IconChevronRight,
  IconCurrencyDollar,
  IconFileText,
  IconScale,
  IconSignature,
  IconInfoCircle
} from "@tabler/icons-react"
import { useNotifications } from "@/contexts/notifications-context"
import { useSearchService } from "@/lib/services/search.service"
import { useAgentsService } from "@/lib/services/agents.service"
import { DocumentCard } from "@/components/documents/document-card"
import { useAgentChat } from "@/hooks/use-agent-chat"
import { ThinkingDisplay } from "@/components/agents/thinking-display"
import { AgentMessageRenderer } from "@/components/chat/agent-message-renderer"
import { SubscriptionErrorDialog } from "@/components/common/subscription-error-dialog"
import { getAgentUseCase, getQuickPrompts } from "@/lib/agent-use-cases"
import { AgentDetailsDialog } from "@/components/agents/agent-details-dialog"

export default function SearchPage() {
  const params = useParams()
  const searchParams = useSearchParams()
  const tenantId = params.tenantId as string
  
  // Get initial values from URL params
  const initialQuery = searchParams.get('q') || ''
  const initialAgent = searchParams.get('agent') || 'search'
  
  // Search state
  const [searchQuery, setSearchQuery] = useState(initialQuery)
  const [searchResults, setSearchResults] = useState<any[]>([])
  const [isSearching, setIsSearching] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)
  
  // Agent state
  const [availableAgents, setAvailableAgents] = useState<any[]>([])
  const [selectedAgentId, setSelectedAgentId] = useState<string>(initialAgent)
  const [isLoadingAgents, setIsLoadingAgents] = useState(true)
  const [selectedAgentDetails, setSelectedAgentDetails] = useState<any>(null)
  
  const { addNotification } = useNotifications()
  const searchService = useSearchService()
  const agentService = useAgentsService()

  // Load available agents from backend
  useEffect(() => {
    loadAvailableAgents()
  }, [])
  
  // Auto-search when page loads with query params
  useEffect(() => {
    if (initialQuery && !isLoadingAgents && availableAgents.length > 0) {
      performSearch()
    }
  }, [isLoadingAgents])

  const loadAvailableAgents = async () => {
    try {
      const response = await agentService.getAgents()
      if (response.data) {
        // Extract agents array from response
        const agentsList = response.data.agents || response.data || []
        
        // Add a default search agent
        const agents = [
          {
            id: 'search',
            name: 'Document Search',
            description: 'Classic semantic search',
            type: 'search',
            icon: 'search'
          }
        ]

        if( agentsList ) {
          agents.push(agentsList);
        }
        
        setAvailableAgents(agents)
        
        // If initial agent is specified and exists, select it
        if (initialAgent && agents.some(a => a.id === initialAgent)) {
          setSelectedAgentId(initialAgent)
        }
      }
    } catch (error) {
      console.error('Failed to load agents:', error)
      // Fallback to default agents
      setAvailableAgents([
        {
          id: 'search',
          name: 'Document Search',
          description: 'Classic semantic search',
          type: 'search',
          icon: 'search'
        }
      ])
    } finally {
      setIsLoadingAgents(false)
    }
  }

  // Perform search
  const performSearch = async () => {
    if (!searchQuery.trim()) {
      addNotification({
        type: 'error',
        title: 'Search Error',
        message: 'Please enter a search query'
      })
      return
    }

    setIsSearching(true)
    setSearchError(null)
    
    try {
      const response = await searchService.searchDocuments({
        query: searchQuery,
        limit: 20
      })
      
      if (response.error) {
        setSearchError(response.error)
        addNotification({
          type: 'error',
          title: 'Search Failed',
          message: response.error
        })
      } else {
        // The API returns the results directly as an array
        const results = response.data || []
        setSearchResults(results)
        
        // Auto-select appropriate agent based on query and available agents
        autoSelectAgent(searchQuery, results)
      }
    } catch (error) {
      console.error('Search failed:', error)
      setSearchError('Failed to search documents')
    } finally {
      setIsSearching(false)
    }
  }

  // Auto-select agent based on query
  const autoSelectAgent = (query: string, results: any[]) => {
    const lowerQuery = query.toLowerCase()
    
    // First check dynamic agents with custom keywords
    for (const agent of availableAgents) {
      if (agent.ui_config?.keywords) {
        // Check if query matches any custom keywords
        const keywords = agent.ui_config.keywords as string[]
        if (keywords.some(keyword => lowerQuery.includes(keyword.toLowerCase()))) {
          setSelectedAgentId(agent.id)
          return
        }
      }
    }
    
    // Check for customer support agent
    if (availableAgents.some(a => a.id === 'customer_support_agent')) {
      if (lowerQuery.includes('support') || lowerQuery.includes('help') ||
          lowerQuery.includes('ticket') || lowerQuery.includes('issue')) {
        setSelectedAgentId('customer_support_agent')
        return
      }
    }
    
    // Check for financial agent
    if (availableAgents.some(a => a.id === 'financial_analysis_agent')) {
      if (lowerQuery.includes('invoice') || lowerQuery.includes('payment') ||
          lowerQuery.includes('factura') || lowerQuery.includes('pago')) {
        setSelectedAgentId('financial_analysis_agent')
        return
      }
    }
    
    // Check for legal agent
    if (availableAgents.some(a => a.id === 'legal_compliance_agent')) {
      if (lowerQuery.includes('contract') || lowerQuery.includes('legal') ||
          lowerQuery.includes('contrato') || lowerQuery.includes('compliance')) {
        setSelectedAgentId('legal_compliance_agent')
        return
      }
    }
    
    // Check for RAG agent
    if (availableAgents.some(a => a.id === 'rag_assistant_agent')) {
      if (query.includes('?') || lowerQuery.includes('what') ||
          lowerQuery.includes('how') || lowerQuery.includes('why')) {
        setSelectedAgentId('rag_assistant_agent')
        return
      }
    }
    
    // Default to document analyzer if available
    if (availableAgents.some(a => a.id === 'document_analyzer_agent')) {
      setSelectedAgentId('document_analyzer_agent')
    }
  }

  // Handle Enter key
  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !isSearching) {
      performSearch()
    }
  }

  // Get agent icon - now supports dynamic icons
  const getAgentIcon = (agent: any) => {
    // Check for custom UI config icon first
    const customIcon = agent.ui_config?.icon
    if (customIcon) {
      // Map custom icon names to Tabler icons
      switch (customIcon) {
        case 'IconHeadset':
          return <IconMessageCircle className="h-5 w-5" />
        // Add more custom icon mappings as needed
      }
    }

    // Fallback to default icon mapping
    switch (agent.icon || agent.type) {
      case 'financial':
      case 'financial_analysis_agent':
        return <IconCurrencyDollar className="h-5 w-5" />
      case 'legal':
      case 'legal_compliance_agent':
        return <IconScale className="h-5 w-5" />
      case 'rag':
      case 'rag_assistant_agent':
        return <IconMessageCircle className="h-5 w-5" />
      case 'document':
      case 'document_analyzer_agent':
        return <IconFileText className="h-5 w-5" />
      case 'signature':
      case 'digital_signature_agent':
        return <IconSignature className="h-5 w-5" />
      case 'search':
        return <IconSearch className="h-5 w-5" />
      case 'support':
      case 'customer_support_agent':
        return <IconMessageCircle className="h-5 w-5" />
      default:
        return <IconBrain className="h-5 w-5" />
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-6 py-4 border-b">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <IconSparkles className="h-6 w-6 text-blue-500" />
          AI-Powered Search
        </h1>
        <p className="text-muted-foreground text-sm mt-1">
          Search documents and get insights using AI agents
        </p>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Main Content */}
        <div className="flex-1 flex flex-col">
          {/* Search Bar */}
          <div className="px-6 py-4 border-b">
            <div className="flex gap-2">
              <div className="flex-1 relative">
                <IconSearch className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground h-4 w-4" />
                <Input
                  placeholder="Search documents or ask a question..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyPress={handleKeyPress}
                  className="pl-10"
                />
              </div>
              <Button onClick={performSearch} disabled={isSearching}>
                {isSearching ? (
                  <IconLoader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <IconSearch className="h-4 w-4" />
                )}
                Search
              </Button>
            </div>

            {/* Agent Selection */}
            {!isLoadingAgents && availableAgents.length > 0 && (
              <div className="flex gap-2 mt-3 flex-wrap">
                {availableAgents.map((agent) => (
                  <Button
                    key={agent.id}
                    variant={selectedAgentId === agent.id ? "default" : "outline"}
                    size="sm"
                    onClick={() => setSelectedAgentId(agent.id)}
                    className="flex items-center gap-2"
                  >
                    {getAgentIcon(agent)}
                    {agent.name}
                  </Button>
                ))}
              </div>
            )}
          </div>

          {/* Results Area */}
          <div className="flex-1 overflow-auto px-6 py-4">
            {/* Loading State */}
            {isSearching && (
              <div className="flex items-center justify-center py-12">
                <IconLoader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                <span className="ml-2 text-muted-foreground">Searching...</span>
              </div>
            )}

            {/* Error State */}
            {searchError && (
              <Card className="border-red-200">
                <CardContent className="pt-6">
                  <p className="text-red-600 text-center">{searchError}</p>
                </CardContent>
              </Card>
            )}

            {/* Results */}
            {!isSearching && !searchError && searchResults.length > 0 && (
              <div className="space-y-6">
                {/* Show search results for basic search */}
                {selectedAgentId === 'search' ? (
                  <div>
                    <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                      <IconFile className="h-5 w-5" />
                      Found {searchResults.length} documents
                    </h2>
                    <div className="grid gap-4">
                      {searchResults.map((result) => (
                        <DocumentCard
                          key={result.document.id}
                          document={result.document}
                          score={result.score}
                          highlights={result.matches?.map((match: any) => match.text) || []}
                        />
                      ))}
                    </div>
                  </div>
                ) : (
                  // Agent Interface
                  <AgentInterface
                    agentId={selectedAgentId}
                    searchQuery={searchQuery}
                    searchResults={searchResults}
                    availableAgents={availableAgents}
                  />
                )}
              </div>
            )}

            {/* Empty State */}
            {!isSearching && !searchError && searchResults.length === 0 && searchQuery && (
              <Card>
                <CardContent className="py-12 text-center">
                  <IconFile className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
                  <h3 className="text-lg font-semibold mb-2">No documents found</h3>
                  <p className="text-muted-foreground">
                    Try adjusting your search terms or using a different agent.
                  </p>
                </CardContent>
              </Card>
            )}

            {/* Initial State */}
            {!searchQuery && !isLoadingAgents && (
              <div className="space-y-6">
                <Card>
                  <CardHeader>
                    <CardTitle>Available AI Agents</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                      {availableAgents.map((agent) => (
                        <Card 
                          key={agent.id} 
                          className={`cursor-pointer hover:border-primary transition-colors relative group ${
                            selectedAgentId === agent.id ? 'border-primary' : ''
                          }`}
                          onClick={() => setSelectedAgentId(agent.id)}
                        >
                          {/* Info button */}
                          <Button
                            variant="ghost"
                            size="sm"
                            className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity"
                            onClick={(e) => {
                              e.stopPropagation()
                              setSelectedAgentDetails(agent)
                            }}
                          >
                            <IconInfoCircle className="h-4 w-4" />
                          </Button>
                          <CardHeader className="pb-3">
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-2">
                                <div className={`p-2 rounded-lg ${
                                  agent.ui_config?.color 
                                    ? `bg-${agent.ui_config.color}-50 text-${agent.ui_config.color}-600`
                                    : 'bg-primary/10 text-primary'
                                }`}>
                                  {getAgentIcon(agent)}
                                </div>
                                <h3 className="font-semibold">{agent.name}</h3>
                              </div>
                              {agent.source === 'dynamic' && (
                                <Badge variant="secondary" className="text-xs">
                                  Custom
                                </Badge>
                              )}
                            </div>
                          </CardHeader>
                          <CardContent>
                            <p className="text-sm text-muted-foreground">
                              {(() => {
                                const useCase = getAgentUseCase(agent.id)
                                return useCase?.description || agent.description
                              })()}
                            </p>
                            {/* Show use case benefits if available */}
                            {(() => {
                              const useCase = getAgentUseCase(agent.id)
                              if (useCase?.benefits && useCase.benefits.length > 0) {
                                return (
                                  <div className="mt-3 space-y-1">
                                    {useCase.benefits.slice(0, 2).map((benefit, idx) => (
                                      <div key={idx} className="flex items-start gap-1.5 text-xs text-muted-foreground">
                                        <IconChevronRight className="h-3 w-3 mt-0.5 flex-shrink-0 text-green-600" />
                                        <span>{benefit}</span>
                                      </div>
                                    ))}
                                  </div>
                                )
                              }
                              return null
                            })()}
                            {/* Show example queries */}
                            {(() => {
                              const quickPrompts = getQuickPrompts(agent.id)
                              if (quickPrompts.length > 0) {
                                return (
                                  <div className="mt-3">
                                    <p className="text-xs font-medium text-muted-foreground mb-1">Ejemplos:</p>
                                    <div className="flex flex-wrap gap-1">
                                      {quickPrompts.map((prompt, idx) => (
                                        <Badge 
                                          key={idx} 
                                          variant="secondary" 
                                          className="text-xs cursor-pointer hover:bg-secondary/80"
                                          onClick={(e) => {
                                            e.stopPropagation()
                                            setSearchQuery(prompt)
                                            setSelectedAgentId(agent.id)
                                          }}
                                        >
                                          {prompt}
                                        </Badge>
                                      ))}
                                    </div>
                                  </div>
                                )
                              }
                              return null
                            })()}
                            {agent.capabilities && agent.capabilities.length > 0 && !getAgentUseCase(agent.id) && (
                              <div className="flex flex-wrap gap-1 mt-2">
                                {agent.capabilities.slice(0, 3).map((cap, idx) => (
                                  <Badge key={idx} variant="outline" className="text-xs">
                                    {cap.replace(/_/g, ' ')}
                                  </Badge>
                                ))}
                              </div>
                            )}
                          </CardContent>
                        </Card>
                      ))}
                    </div>

                    <Separator className="my-6" />

                    <div>
                      <h4 className="font-semibold mb-2">Example searches:</h4>
                      <div className="flex flex-wrap gap-2">
                        <Badge 
                          variant="secondary" 
                          className="cursor-pointer"
                          onClick={() => {
                            setSearchQuery("invoices from last month")
                          }}
                        >
                          invoices from last month
                        </Badge>
                        <Badge 
                          variant="secondary" 
                          className="cursor-pointer"
                          onClick={() => {
                            setSearchQuery("What are our payment terms?")
                          }}
                        >
                          What are our payment terms?
                        </Badge>
                        <Badge 
                          variant="secondary" 
                          className="cursor-pointer"
                          onClick={() => {
                            setSearchQuery("contracts 2024")
                          }}
                        >
                          contracts 2024
                        </Badge>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>
            )}
          </div>
        </div>
      </div>
      
      {/* Agent Details Dialog */}
      <AgentDetailsDialog
        agent={selectedAgentDetails}
        isOpen={!!selectedAgentDetails}
        onClose={() => setSelectedAgentDetails(null)}
        onSelectExample={(agentId, example) => {
          setSearchQuery(example)
          setSelectedAgentId(agentId)
          performSearch()
        }}
      />
    </div>
  )
}

// Agent Interface Component
function AgentInterface({ agentId, searchQuery, searchResults, availableAgents }: any) {
  const params = useParams()
  const tenantId = params.tenantId as string
  const [input, setInput] = useState('')
  const [showThinking, setShowThinking] = useState(false)
  const [subscriptionError, setSubscriptionError] = useState<any>(null)
  
  const { 
    messages, 
    thinkingEvents,
    isLoading,
    isStreaming,
    sendMessage,
    clearChat
  } = useAgentChat({
    agentId,
    onError: (error) => {
      console.error('Agent error:', error)
      
      // Check if it's a subscription error
      try {
        console.log('Raw error in onError:', error)
        const errorData = JSON.parse(error)
        console.log('Parsed error data:', errorData)
        if (errorData.type === 'subscription_error') {
          console.log('Setting subscription error:', errorData.detail)
          setSubscriptionError(errorData.detail)
        }
      } catch (e) {
        console.log('Failed to parse error:', e)
        // Not a subscription error
      }
    }
  })

  // Send initial query only once when component mounts with searchQuery
  useEffect(() => {
    if (!searchQuery) return
    
    // Use a ref to track if we've sent the initial message
    let mounted = true
    
    const sendInitialMessage = async () => {
      if (mounted && messages.length === 0) {
        await sendMessage(`Analyze these search results for: "${searchQuery}"`, {
          query: searchQuery,
          documents: searchResults.map((r: any) => ({
            id: r.document.id,
            title: r.document.title,
            type: r.document.file_type,
            score: r.score,
            highlights: r.highlights
          }))
        })
      }
    }
    
    // Small delay to prevent double execution in React StrictMode
    const timer = setTimeout(sendInitialMessage, 200)
    
    return () => {
      mounted = false
      clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId]) // Only re-run when agentId changes

  const handleSendMessage = useCallback(async (message: string) => {
    if (!message.trim()) return
    
    // Include document context
    const context = {
      query: searchQuery,
      documents: searchResults.map((r: any) => ({
        id: r.document.id,
        title: r.document.title,
        type: r.document.file_type,
        score: r.score,
        highlights: r.highlights
      }))
    }
    
    await sendMessage(message, context)
    setInput('')
  }, [searchQuery, searchResults, sendMessage])

  return (
    <div className="space-y-4">
      {/* Subscription Error Dialog */}
      <SubscriptionErrorDialog
        isOpen={!!subscriptionError}
        onClose={() => setSubscriptionError(null)}
        errorDetail={subscriptionError || {}}
        tenantId={tenantId}
      />

      {/* Agent Header */}
      <Card className="bg-gradient-to-r from-blue-50 to-purple-50 border-blue-200">
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <IconRobot className="h-5 w-5 text-blue-600" />
            {(() => {
              const agent = availableAgents.find(a => a.id === agentId)
              return agent?.name || 'AI Agent Analysis'
            })()}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Analyzing {searchResults.length} documents related to "{searchQuery}"
          </p>
          {(() => {
            const agent = availableAgents.find(a => a.id === agentId)
            const useCase = getAgentUseCase(agentId)
            const quickActions = agent?.ui_config?.quick_actions || (useCase ? getQuickPrompts(agentId) : [])
            
            return quickActions.length > 0 && (
              <div className="mt-3">
                <p className="text-xs font-medium text-muted-foreground mb-2">Sugerencias:</p>
                <div className="flex flex-wrap gap-2">
                  {quickActions.map((action, idx) => (
                    <Button
                      key={idx}
                      variant="outline"
                      size="sm"
                      onClick={() => handleSendMessage(action)}
                      className="text-xs"
                    >
                      {action}
                    </Button>
                  ))}
                </div>
              </div>
            )
          })()}
        </CardContent>
      </Card>

      {/* Chat Interface */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">Conversation</CardTitle>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowThinking(!showThinking)}
              className={showThinking ? 'text-blue-600' : 'text-gray-400'}
            >
              <IconBrain className="h-4 w-4 mr-1" />
              {showThinking ? 'Hide' : 'Show'} Thinking
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Messages */}
          <ScrollArea className="h-96 pr-4">
            <div className="space-y-4">
              {messages.map((message, index) => (
                <div
                  key={index}
                  className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[80%] rounded-lg p-3 text-sm ${
                      message.role === 'user'
                        ? 'bg-blue-600 text-white'
                        : 'bg-gray-100 dark:bg-gray-800'
                    }`}
                  >
                    {message.role === 'user' ? (
                      <>
                        <p className="whitespace-pre-wrap">{message.content}</p>
                        <span className="text-xs opacity-70 mt-1 block">
                          {new Date(message.timestamp).toLocaleTimeString()}
                        </span>
                      </>
                    ) : (
                      <AgentMessageRenderer 
                        content={message.content}
                        timestamp={message.timestamp}
                        metadata={message.metadata}
                      />
                    )}
                  </div>
                </div>
              ))}
              
              {/* Thinking Display */}
              {showThinking && thinkingEvents.length > 0 && (
                <div className="bg-blue-50 dark:bg-blue-950/20 rounded-lg p-4">
                  <ThinkingDisplay 
                    events={thinkingEvents} 
                    isStreaming={isStreaming}
                  />
                </div>
              )}
              
              {/* Loading Indicator */}
              {isLoading && (
                <div className="flex items-center gap-2 text-blue-600">
                  <IconLoader2 className="h-4 w-4 animate-spin" />
                  <span className="text-sm">
                    {isStreaming ? 'Agent is thinking...' : 'Processing...'}
                  </span>
                </div>
              )}
            </div>
          </ScrollArea>

          {/* Input */}
          <div className="flex gap-2">
            <Input
              placeholder="Ask a follow-up question..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={(e) => {
                if (e.key === 'Enter' && !isLoading) {
                  handleSendMessage(input)
                }
              }}
              disabled={isLoading}
            />
            <Button 
              onClick={() => handleSendMessage(input)}
              disabled={isLoading || !input.trim()}
            >
              Send
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Document Context */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <IconFile className="h-4 w-4" />
            Document Context
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {searchResults.slice(0, 5).map((result: any, index: number) => (
              <div key={index} className="flex items-start gap-2 text-sm">
                <Badge variant="outline" className="mt-0.5">
                  {Math.round(result.score * 100)}%
                </Badge>
                <div className="flex-1">
                  <p className="font-medium">{result.document.title}</p>
                  <p className="text-xs text-muted-foreground">
                    {result.document.description || result.highlights?.[0] || "No preview available"}
                  </p>
                </div>
              </div>
            ))}
            {searchResults.length > 5 && (
              <p className="text-xs text-muted-foreground text-center pt-2">
                And {searchResults.length - 5} more documents...
              </p>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}