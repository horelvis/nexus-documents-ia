"use client"

import { useState } from "react"
import { 
  IconSearch, 
  IconFile,
  IconLoader2,
  IconMessageCircle,
  IconSend,
  IconBrain,
  IconBook,
  IconTag,
  IconSparkles
} from "@tabler/icons-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { useNotifications } from "@/contexts/notifications-context"
import { useSearchService, SearchResult, AskDocumentsResponse } from "@/lib/services/search.service"
import { getFileIcon, formatFileSize, getStatusColor } from "@/lib/document-utils"
import RAGAssistant from "@/components/search/rag-assistant"
import FinancialAgent from "@/components/search/financial-agent"

export default function SearchPage() {
  // Search state
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<SearchResult[]>([])
  const [isSearching, setIsSearching] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)
  
  // Q&A state
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<AskDocumentsResponse | null>(null)
  const [isAsking, setIsAsking] = useState(false)
  const [askError, setAskError] = useState<string | null>(null)
  
  // Filter state
  const [selectedTags, setSelectedTags] = useState<string[]>([])
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [financialFilters, setFinancialFilters] = useState<any>({})
  
  const { addNotification } = useNotifications()
  const searchService = useSearchService()

  // Simple search function following the established pattern
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
        limit: 20,
        tags: selectedTags.length > 0 ? selectedTags : undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined
      })
      
      if (response.error) {
        setSearchError(response.error)
        addNotification({
          type: 'error',
          title: 'Search Failed',
          message: response.error
        })
      } else {
        setSearchResults(response.data || [])
        addNotification({
          type: 'success',
          title: 'Search Complete',
          message: `Found ${response.data?.length || 0} documents`
        })
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Search failed'
      setSearchError(errorMessage)
      addNotification({
        type: 'error',
        title: 'Search Failed',
        message: errorMessage
      })
    } finally {
      setIsSearching(false)
    }
  }

  // Simple ask function following the established pattern
  const askQuestion = async () => {
    if (!question.trim()) {
      addNotification({
        type: 'error',
        title: 'Question Error',
        message: 'Please enter a question'
      })
      return
    }

    setIsAsking(true)
    setAskError(null)
    
    try {
      const response = await searchService.askDocuments({
        question: question,
        doc_ids: searchResults.map(r => r.document.id) // Use current search results as context
      })
      
      if (response.error) {
        setAskError(response.error)
        addNotification({
          type: 'error',
          title: 'Question Failed',
          message: response.error
        })
      } else {
        setAnswer(response.data || null)
        addNotification({
          type: 'success',
          title: 'Answer Generated',
          message: 'Your question has been answered based on your documents'
        })
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Question failed'
      setAskError(errorMessage)
      addNotification({
        type: 'error',
        title: 'Question Failed',
        message: errorMessage
      })
    } finally {
      setIsAsking(false)
    }
  }

  const clearFilters = () => {
    setSelectedTags([])
    setDateFrom('')
    setDateTo('')
    setFinancialFilters({})
  }

  const handleFinancialFiltersChange = (filters: any) => {
    setFinancialFilters(filters)
    // Optionally trigger a new search with financial filters
    // You could extend the search API to support these filters
  }

  const handleFinancialInsight = async (insight: string) => {
    // When user clicks on a financial insight, set it as a question for the Q&A
    setQuestion(insight)
    setIsAskingQuestion(true)
    
    try {
      // Automatically execute the question
      const response = await searchService.askDocuments({
        question: insight,
        // If there are search results, use them as context
        doc_ids: searchResults.length > 0 ? searchResults.map(r => r.document.id) : undefined
      })

      if (response.error) {
        addNotification({
          type: 'error',
          title: 'Error',
          message: response.error
        })
      } else if (response.data) {
        setAskResponse(response.data)
      }
    } catch (err) {
      console.error("Failed to ask question:", err)
      addNotification({
        type: 'error',
        title: 'Error',
        message: 'Failed to process your question'
      })
    } finally {
      setIsAskingQuestion(false)
    }
  }

  const handleAssistantSuggestion = (suggestion: string) => {
    // If it's a search term (like "facturas"), update search query
    if (suggestion === "facturas" || suggestion === "contratos" || suggestion === "documentos") {
      setSearchQuery(suggestion)
      // Trigger search automatically
      setTimeout(() => performSearch(), 100)
    } else {
      // If it's a question, set it for the Q&A tab
      setQuestion(suggestion)
    }
  }

  return (
    <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6">
      <div className="px-4 lg:px-6">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold mb-2 flex items-center gap-2">
            <IconBrain className="h-8 w-8 text-blue-500" />
            Semantic Search
          </h1>
          <p className="text-muted-foreground">
            Search through your documents using AI-powered semantic understanding and ask questions about your content. The AI Assistant will help you analyze your results.
          </p>
        </div>

        <Tabs defaultValue="search" className="w-full">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="search" className="flex items-center gap-2">
              <IconSearch className="h-4 w-4" />
              Search Documents
            </TabsTrigger>
            <TabsTrigger value="ask" className="flex items-center gap-2">
              <IconMessageCircle className="h-4 w-4" />
              Ask Questions
            </TabsTrigger>
          </TabsList>

          {/* SEARCH TAB */}
          <TabsContent value="search" className="space-y-6">
            {/* Search Controls */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <IconSparkles className="h-5 w-5" />
                  Semantic Search
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Main Search */}
                <div className="flex gap-2">
                  <div className="flex-1 relative">
                    <IconSearch className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground h-4 w-4" />
                    <Input
                      placeholder="Search for concepts, topics, or content..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && performSearch()}
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

                {/* Filters */}
                <div className="flex flex-wrap gap-4 items-end">
                  <div className="flex-1 min-w-48">
                    <label className="text-sm font-medium mb-1 block">Date From</label>
                    <Input
                      type="date"
                      value={dateFrom}
                      onChange={(e) => setDateFrom(e.target.value)}
                    />
                  </div>
                  <div className="flex-1 min-w-48">
                    <label className="text-sm font-medium mb-1 block">Date To</label>
                    <Input
                      type="date"
                      value={dateTo}
                      onChange={(e) => setDateTo(e.target.value)}
                    />
                  </div>
                  <Button variant="outline" onClick={clearFilters}>
                    Clear Filters
                    {(Object.keys(financialFilters).length > 0) && (
                      <Badge variant="secondary" className="ml-2 h-4 w-4 p-0 text-xs">
                        {Object.keys(financialFilters).length}
                      </Badge>
                    )}
                  </Button>
                </div>
              </CardContent>
            </Card>

            {isSearching && (
              <div className="flex justify-center items-center py-12">
                <IconLoader2 className="h-8 w-8 animate-spin" />
                <span className="ml-2">Searching documents...</span>
              </div>
            )}

            {searchError && (
              <Card className="border-red-200">
                <CardContent className="pt-6">
                  <p className="text-red-600 text-center">{searchError}</p>
                  <div className="flex justify-center mt-4">
                    <Button onClick={performSearch} variant="outline">
                      Try Again
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}

            {!isSearching && !searchError && searchResults.length > 0 && (
              <div className="space-y-4">
                {/* AI Agents - Always show when there are results */}
                {searchQuery && (
                  <div className="space-y-4">
                    <RAGAssistant
                      searchResults={searchResults}
                      searchQuery={searchQuery}
                      onSuggestionClick={handleAssistantSuggestion}
                    />
                    
                    <FinancialAgent
                      searchResults={searchResults}
                      searchQuery={searchQuery}
                      onFiltersChange={handleFinancialFiltersChange}
                      onInsightClick={handleFinancialInsight}
                    />
                  </div>
                )}

                <div className="flex items-center justify-between">
                  <h3 className="text-lg font-semibold">
                    Search Results ({searchResults.length})
                  </h3>
                </div>

                <div className="grid gap-4">
                  {searchResults.map((result, index) => {
                    // Handle both new structure (with document object) and current structure (with metadata)
                    const document = result.document || result.metadata || {}
                    const content = result.content || ''
                    const score = result.score || 0
                    const matches = result.matches || []
                    
                    // Create a normalized document object
                    const normalizedDoc = {
                      id: document.doc_id || document._id || document.id || index,
                      title: document.title || document.filename || 'Untitled',
                      description: document.description || '',
                      filename: document.filename || 'Unknown file',
                      file_type: document.file_type || 'unknown',
                      file_size: document.file_size || null,
                      mime_type: document.mime_type || '',
                      created_at: document.created_at || null,
                      indexed: document.indexed || 'unknown',
                      tags: document.tags || []
                    }
                    
                    return (
                      <Card key={normalizedDoc.id} className="hover:shadow-md transition-shadow">
                        <CardContent className="pt-6">
                          <div className="flex items-start gap-4">
                            <div className="flex-shrink-0">
                              {getFileIcon(normalizedDoc.file_type, normalizedDoc.mime_type, normalizedDoc.filename)}
                            </div>
                            
                            <div className="flex-1 min-w-0">
                              <div className="flex items-start justify-between mb-2">
                                <div>
                                  <h4 className="font-semibold text-base truncate">
                                    {normalizedDoc.title}
                                  </h4>
                                  {normalizedDoc.description && (
                                    <p className="text-muted-foreground text-sm mt-1">
                                      {normalizedDoc.description}
                                    </p>
                                  )}
                                </div>
                                <div className="flex items-center gap-2 ml-4">
                                  <Badge variant="secondary" className="text-xs">
                                    {score ? (score * 100).toFixed(1) : '0.0'}% match
                                  </Badge>
                                  <Badge className={getStatusColor(normalizedDoc.indexed)} variant="secondary">
                                    {normalizedDoc.indexed}
                                  </Badge>
                                </div>
                              </div>

                              <div className="flex items-center gap-4 text-sm text-muted-foreground mb-3">
                                <span>Size: {normalizedDoc.file_size ? formatFileSize(normalizedDoc.file_size) : 'Unknown'}</span>
                                <span>•</span>
                                <span>Uploaded: {normalizedDoc.created_at ? new Date(normalizedDoc.created_at).toLocaleDateString() : 'Unknown date'}</span>
                              </div>

                              {normalizedDoc.tags && normalizedDoc.tags.length > 0 && (
                                <div className="flex flex-wrap gap-1 mb-3">
                                  {normalizedDoc.tags.map((tag, tagIndex) => (
                                    <Badge key={tagIndex} variant="outline" className="text-xs">
                                      <IconTag className="h-3 w-3 mr-1" />
                                      {tag}
                                    </Badge>
                                  ))}
                                </div>
                              )}

                              {(matches.length > 0 || content) && (
                                <div className="bg-muted/50 rounded-lg p-3">
                                  <h5 className="font-medium text-sm mb-2">Relevant Excerpts:</h5>
                                  {matches.length > 0 ? (
                                    matches.slice(0, 2).map((match, matchIndex) => (
                                      <div key={matchIndex} className="text-sm mb-2 last:mb-0">
                                        <span className="text-muted-foreground">
                                          &quot;...{match.text}...&quot;
                                        </span>
                                        <Badge variant="outline" className="ml-2 text-xs">
                                          {match.score ? (match.score * 100).toFixed(1) : '0.0'}% relevance
                                        </Badge>
                                      </div>
                                    ))
                                  ) : content && (
                                    <div className="text-sm mb-2">
                                      <span className="text-muted-foreground">
                                        &quot;...{content.slice(0, 200)}...&quot;
                                      </span>
                                      <Badge variant="outline" className="ml-2 text-xs">
                                        {score ? (score * 100).toFixed(1) : '0.0'}% relevance
                                      </Badge>
                                    </div>
                                  )}
                                </div>
                              )}
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    )
                  })}
                </div>
              </div>
            )}

            {!isSearching && !searchError && searchQuery && searchResults.length === 0 && (
              <Card className="text-center py-12">
                <CardContent>
                  <IconFile className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
                  <h3 className="text-lg font-semibold mb-2">No documents found</h3>
                  <p className="text-muted-foreground">
                    Try adjusting your search terms or filters.
                  </p>
                </CardContent>
              </Card>
            )}
          </TabsContent>

          {/* ASK TAB */}
          <TabsContent value="ask" className="space-y-6">
            {/* Question Input */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <IconBook className="h-5 w-5" />
                  Ask Your Documents
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Your Question</label>
                  <Textarea
                    placeholder="Ask a question about your documents..."
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    rows={3}
                  />
                </div>
                
                <div className="flex justify-between items-center">
                  <p className="text-sm text-muted-foreground">
                    {searchResults.length > 0 
                      ? `Will search through ${searchResults.length} documents from your recent search`
                      : 'Will search through all your documents'
                    }
                  </p>
                  <Button onClick={askQuestion} disabled={isAsking}>
                    {isAsking ? (
                      <IconLoader2 className="h-4 w-4 animate-spin mr-2" />
                    ) : (
                      <IconSend className="h-4 w-4 mr-2" />
                    )}
                    Ask Question
                  </Button>
                </div>
              </CardContent>
            </Card>

            {/* Answer Display */}
            {isAsking && (
              <div className="flex justify-center items-center py-12">
                <IconLoader2 className="h-8 w-8 animate-spin" />
                <span className="ml-2">Generating answer...</span>
              </div>
            )}

            {askError && (
              <Card className="border-red-200">
                <CardContent className="pt-6">
                  <p className="text-red-600 text-center">{askError}</p>
                  <div className="flex justify-center mt-4">
                    <Button onClick={askQuestion} variant="outline">
                      Try Again
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}

            {!isAsking && !askError && answer && (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <IconSparkles className="h-5 w-5 text-blue-500" />
                    Answer
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="prose max-w-none">
                    <p className="text-base leading-relaxed">
                      {answer.answer}
                    </p>
                  </div>

                  {answer.sources && answer.sources.length > 0 && (
                    <div className="border-t pt-4">
                      <h4 className="font-semibold mb-3">Sources:</h4>
                      <div className="space-y-2">
                        {answer.sources.map((source, index) => (
                          <div key={index} className="flex items-start gap-3 p-3 bg-muted/50 rounded-lg">
                            <IconFile className="h-4 w-4 mt-1 text-muted-foreground" />
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 mb-1">
                                <span className="font-medium text-sm truncate">
                                  {source.filename}
                                </span>
                                <Badge variant="outline" className="text-xs">
                                  {(source.relevance_score * 100).toFixed(1)}% relevant
                                </Badge>
                              </div>
                              <p className="text-sm text-muted-foreground">
                                &quot;{source.excerpt}...&quot;
                              </p>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}
          </TabsContent>
        </Tabs>
      </div>
    </div>
  )
}