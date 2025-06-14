"use client"

import { useState, useEffect } from "react"
import { useParams } from "next/navigation"
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
  IconSignature
} from "@tabler/icons-react"
import { useNotifications } from "@/contexts/notifications-context"
import { useSearchService } from "@/lib/services/search.service"
import { useAgentsService } from "@/lib/services/agents.service"
import { DocumentCard } from "@/components/documents/document-card"
import { useAgentChat } from "@/hooks/use-agent-chat"
import { ThinkingDisplay } from "@/components/agents/thinking-display"

export default function SearchPage() {
  const params = useParams()
  const tenantId = params.tenantId as string
  
  // Search state
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<any[]>([])
  const [isSearching, setIsSearching] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)
  
  // Agent state
  const [availableAgents, setAvailableAgents] = useState<any[]>([])
  const [selectedAgentId, setSelectedAgentId] = useState<string>('search')
  const [isLoadingAgents, setIsLoadingAgents] = useState(true)
  
  const { addNotification } = useNotifications()
  const searchService = useSearchService()
  const agentService = useAgentsService()

  // Load available agents from backend
  useEffect(() => {
    loadAvailableAgents()
  }, [])

  const loadAvailableAgents = async () => {
    try {
      const response = await agentService.getAgents()
      if (response.data) {
        // Add a default search agent
        const agents = [
          {
            id: 'search',
            name: 'Document Search',
            description: 'Classic semantic search',
            type: 'search',
            icon: 'search'
          },
          ...response.data
        ]
        setAvailableAgents(agents)
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
        setSearchResults(response.data?.results || [])
        
        // Auto-select appropriate agent based on query and available agents
        autoSelectAgent(searchQuery, response.data?.results || [])
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

  // Get agent icon
  const getAgentIcon = (agent: any) => {
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
                          highlights={result.highlights}
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
                          className="cursor-pointer hover:border-primary transition-colors"
                          onClick={() => setSelectedAgentId(agent.id)}
                        >
                          <CardHeader className="pb-3">
                            <div className="flex items-center gap-2">
                              <div className="p-2 rounded-lg bg-primary/10 text-primary">
                                {getAgentIcon(agent)}
                              </div>
                              <h3 className="font-semibold">{agent.name}</h3>
                            </div>
                          </CardHeader>
                          <CardContent>
                            <p className="text-sm text-muted-foreground">
                              {agent.description}
                            </p>
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
    </div>
  )
}

// Agent Interface Component
function AgentInterface({ agentId, searchQuery, searchResults }: any) {
  const [input, setInput] = useState('')
  const [showThinking, setShowThinking] = useState(false)
  
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
    }
  })

  // Send initial query when component mounts
  useEffect(() => {
    if (searchQuery && messages.length === 0) {
      handleSendMessage(`Analyze these search results for: "${searchQuery}"`)
    }
  }, [searchQuery])

  const handleSendMessage = async (message: string) => {
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
  }

  return (
    <div className="space-y-4">
      {/* Agent Header */}
      <Card className="bg-gradient-to-r from-blue-50 to-purple-50 border-blue-200">
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <IconRobot className="h-5 w-5 text-blue-600" />
            AI Agent Analysis
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Analyzing {searchResults.length} documents related to "{searchQuery}"
          </p>
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
                    <p className="whitespace-pre-wrap">{message.content}</p>
                    <span className="text-xs opacity-70 mt-1 block">
                      {new Date(message.timestamp).toLocaleTimeString()}
                    </span>
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