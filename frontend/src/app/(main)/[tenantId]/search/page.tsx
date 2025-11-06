"use client"

import { useState, useEffect, useCallback } from "react"
import { useParams, useRouter, useSearchParams } from "next/navigation"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { 
  IconSearch, 
  IconLoader2, 
  IconFile,
  IconBrain,
  IconFilter,
  IconCalendar,
  IconTag
} from "@tabler/icons-react"
import { useSearchService } from "@/lib/services/search.service"
import { SearchResults } from "@/components/search/search-results"
import { FacetPanel } from "@/components/search/facet-panel"
import { useSearchFacets } from "@/lib/hooks/use-search-facets"
import { toast } from "sonner"

// Helper function to normalize search results from CAG/backend
const normalizeSearchResult = (result: any) => {
  console.log('Raw search result:', result)
  
  if (!result?.id) {
    return null
  }
  
  // Backend returns: { id, content, metadata, similarity_score, title }
  const normalized = {
    id: result.id,
    filename: result.title,
    title: result.title,
    description: result.content ? result.content.substring(0, 200) + '...' : '',
    score: result.similarity_score || 0,
    matches: result.content ? [{ text: result.content.substring(0, 150) + '...' }] : [],
    // Extract file info from title
    file_type: result.title?.includes('.pdf') ? 'pdf' : 
               result.title?.includes('.docx') ? 'docx' :
               result.title?.includes('.doc') ? 'doc' : 'unknown',
    mime_type: result.title?.includes('.pdf') ? 'application/pdf' : 
               result.title?.includes('.docx') ? 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' :
               'application/octet-stream',
    file_size: null, // Not available in search results
    category: result.metadata?.category || null,
    tags: result.metadata?.tags || [],
    created_at: result.metadata?.created_at || null,
    indexed: 'INDEXED', // Assumed if it's in search results
    tenant_id: result.metadata?.tenant_id
  }
  
  console.log('Normalized result:', normalized)
  return normalized
}

// Skip static generation for this page since it uses dynamic params
export const dynamic = 'force-dynamic'

export default function SimpleSearchPage() {
  const params = useParams()
  const router = useRouter()
  const searchParams = useSearchParams()
  const tenantId = params.tenantId as string

  // Search state
  const [searchResults, setSearchResults] = useState<any[]>([])
  const [isSearching, setIsSearching] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)
  const [searchType, setSearchType] = useState<'semantic' | 'hybrid' | 'keyword'>('semantic')

  // Use the faceting hook
  const {
    facets,
    isLoadingFacets,
    currentFilters,
    searchQuery,
    handleFacetChange,
    clearAllFilters,
    updateSearchQuery,
    getActiveFilterCount,
    getFilterSummary
  } = useSearchFacets(tenantId)
  
  const searchService = useSearchService()

  // Auto-search if returning from preview with search context
  useEffect(() => {
    const queryFromUrl = searchParams.get('q')
    if (queryFromUrl && queryFromUrl.trim()) {
      performSearch()
    }
  }, []) // Only run once on mount

  const performSearch = useCallback(async () => {
    if (!searchQuery.trim()) {
      toast.error("Please enter a search query")
      return
    }

    setIsSearching(true)
    setSearchError(null)

    try {
      console.log('Starting search with params:', {
        query: searchQuery,
        limit: 20,
        search_type: searchType,
        filters: currentFilters
      })

      const response = await searchService.searchDocuments({
        query: searchQuery,
        limit: 20,
        search_type: searchType,
        ...currentFilters
      })

      console.log('Search response:', response)

      if (response.error) {
        console.error('Search error from response:', response.error)
        setSearchError(response.error)
      } else {
        console.log('Search results raw:', response.data)

        if (response.data && response.data.length > 0) {
          console.log('First result sample:', response.data[0])
          console.log('Search results structure check:', response.data?.map(r => ({
            hasDocument: !!r?.document,
            hasId: !!r?.document?.id || !!r?.id,
            documentKeys: r?.document ? Object.keys(r.document) : [],
            resultKeys: r ? Object.keys(r) : []
          })))
        }

        setSearchResults(response.data || [])
        if (!response.data || response.data.length === 0) {
          toast.info("No documents found matching your search")
        }
      }
    } catch (error: any) {
      console.error('Search exception:', error)
      setSearchError(error.message || "An error occurred during search")
    } finally {
      setIsSearching(false)
    }
  }, [searchQuery, searchType, currentFilters, searchService])

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !isSearching) {
      performSearch()
    }
  }

  const askEmmaAboutResults = () => {
    if (searchResults.length === 0) {
      toast.error("No results to analyze")
      return
    }
    
    // Navigate to Emma with search context
    const emmaQuery = `Analyze these search results for: "${searchQuery}"`
    router.push(`/${tenantId}/chat?q=${encodeURIComponent(emmaQuery)}`)
  }

  const clearSearch = () => {
    updateSearchQuery("")
    setSearchResults([])
    setSearchError(null)
    clearAllFilters()
  }

  const handleDocumentDownload = (document: any) => {
    if (document.download_url) {
      window.open(document.download_url, '_blank')
    } else {
      toast.error("Download URL not available")
    }
  }

  const handleDocumentShare = (document: any) => {
    // TODO: Implement share functionality
    toast.info("Share functionality coming soon")
  }

  const handleDocumentSignature = (document: any) => {
    router.push(`/${tenantId}/signatures/requests/new?document_id=${document.id}`)
  }

  return (
    <div className="flex-1 space-y-6 p-6">
      {/* Header */}
      <div className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight">Document Search</h1>
        <p className="text-muted-foreground">
          Quickly find documents using semantic search with dynamic filters. For complex queries and analysis, try Emma Assistant.
        </p>
      </div>

      {/* Search Interface */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Facet Panel - Sidebar */}
        <div className="lg:col-span-1">
          <FacetPanel
            facets={facets}
            onFacetChange={handleFacetChange}
            onClearAll={clearAllFilters}
            isLoading={isLoadingFacets}
          />
        </div>

        {/* Main Search Area */}
        <div className="lg:col-span-3 space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <IconSearch className="h-5 w-5" />
                Quick Search
                {getActiveFilterCount() > 0 && (
                  <Badge variant="secondary" className="text-xs">
                    {getActiveFilterCount()} filter{getActiveFilterCount() !== 1 ? 's' : ''} active
                  </Badge>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
          {/* Main search */}
          <div className="space-y-3">
            {/* Search input and type selector */}
            <div className="flex gap-2">
              <div className="flex-1 relative">
                <IconSearch className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground h-4 w-4" />
                <Input
                  placeholder="Search documents..."
                  value={searchQuery}
                  onChange={(e) => updateSearchQuery(e.target.value)}
                  onKeyPress={handleKeyPress}
                  className="pl-10"
                />
              </div>
              <Select value={searchType} onValueChange={(value: 'semantic' | 'hybrid' | 'keyword') => setSearchType(value)}>
                <SelectTrigger className="w-32">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="semantic">
                    <div className="flex flex-col">
                      <span>Semantic</span>
                      <span className="text-xs text-muted-foreground">Fast AI search</span>
                    </div>
                  </SelectItem>
                  <SelectItem value="hybrid">
                    <div className="flex flex-col">
                      <span>Hybrid</span>
                      <span className="text-xs text-muted-foreground">AI + keywords</span>
                    </div>
                  </SelectItem>
                  <SelectItem value="keyword">
                    <div className="flex flex-col">
                      <span>Keyword</span>
                      <span className="text-xs text-muted-foreground">Traditional search</span>
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
              <Button onClick={performSearch} disabled={isSearching || !searchQuery.trim()}>
                {isSearching ? (
                  <IconLoader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <IconSearch className="h-4 w-4" />
                )}
                Search
              </Button>
              {searchResults.length > 0 && (
                <Button variant="outline" onClick={clearSearch}>
                  Clear
                </Button>
              )}
            </div>

            {/* Search type info */}
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Badge variant="outline" className="text-xs">
                {searchType === 'semantic' && '🚀 Weaviate Engine'}
                {searchType === 'hybrid' && '🔍 Elasticsearch Engine'}  
                {searchType === 'keyword' && '📝 Elasticsearch Engine'}
              </Badge>
              <span>
                {searchType === 'semantic' && 'Fast semantic search using AI embeddings'}
                {searchType === 'hybrid' && 'Combined keyword and semantic search with filters'}
                {searchType === 'keyword' && 'Traditional keyword-based search with boolean operators'}
              </span>
            </div>
          </div>

          {/* Advanced filters toggle */}
          <div className="flex items-center gap-2">
            <Button 
              variant="ghost" 
              size="sm" 
              onClick={() => setShowFilters(!showFilters)}
              className="text-muted-foreground"
            >
              <IconFilter className="h-4 w-4 mr-2" />
              Advanced Filters
            </Button>
            {showFilters && (
              <Badge variant="secondary" className="text-xs">
                Optional filters for more specific results
              </Badge>
            )}
          </div>

          {/* Advanced filters */}
          {showFilters && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 p-4 bg-muted/30 rounded-lg">
              <div className="space-y-2">
                <label className="text-sm font-medium flex items-center gap-2">
                  <IconTag className="h-4 w-4" />
                  Tags
                </label>
                <Input
                  placeholder="tag1, tag2, tag3"
                  value={tags}
                  onChange={(e) => setTags(e.target.value)}
                  className="text-sm"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium flex items-center gap-2">
                  <IconCalendar className="h-4 w-4" />
                  Date From
                </label>
                <Input
                  type="date"
                  value={dateFrom}
                  onChange={(e) => setDateFrom(e.target.value)}
                  className="text-sm"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium flex items-center gap-2">
                  <IconCalendar className="h-4 w-4" />
                  Date To
                </label>
                <Input
                  type="date"
                  value={dateTo}
                  onChange={(e) => setDateTo(e.target.value)}
                  className="text-sm"
                />
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Search Results */}
      {searchError && (
        <Card className="border-red-200">
          <CardContent className="pt-6">
            <p className="text-red-600 text-center">{searchError}</p>
          </CardContent>
        </Card>
      )}

      {!isSearching && !searchError && searchResults.length > 0 && (
        <div className="space-y-6">
          {/* Results header with Emma integration */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="flex items-center gap-2">
                  <IconFile className="h-5 w-5" />
                  Found {searchResults.length} documents
                </CardTitle>
                <Button onClick={askEmmaAboutResults} className="flex items-center gap-2">
                  <IconBrain className="h-4 w-4" />
                  Ask Emma about these results
                </Button>
              </div>
            </CardHeader>
          </Card>

          {/* Search Results */}
          <SearchResults
            results={searchResults.map((result, index) => {
              console.log(`Processing result ${index}:`, result)
              return normalizeSearchResult(result)
            }).filter(doc => doc !== null)}
            onDocumentClick={(doc) => {
              // Preserve search context in URL
              const searchParams = new URLSearchParams({
                returnTo: 'search',
                query: searchQuery,
                ...(currentFilters.tags && { tags: currentFilters.tags.join(',') }),
                ...(currentFilters.date_from && { dateFrom: currentFilters.date_from }),
                ...(currentFilters.date_to && { dateTo: currentFilters.date_to })
              })
              router.push(`/${tenantId}/documents/${doc.id}/preview?${searchParams.toString()}`)
            }}
            onDownload={handleDocumentDownload}
            onShare={handleDocumentShare}
            onSignature={handleDocumentSignature}
            emptyMessage="No documents found matching your search criteria"
          />
        </div>
      )}

      {/* Active Filters Summary */}
      {getActiveFilterCount() > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">Active Filters</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {getFilterSummary().map((filter, index) => (
                <Badge key={index} variant="outline" className="text-xs">
                  {filter}
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Getting started */}
      {!searchQuery && searchResults.length === 0 && (
        <Card>
          <CardContent className="pt-6">
            <div className="text-center space-y-4">
              <IconSearch className="h-12 w-12 text-muted-foreground mx-auto" />
              <div>
                <h3 className="text-lg font-medium">Quick Document Search</h3>
                <p className="text-muted-foreground mt-2">
                  Search for specific documents using keywords. Use the filters on the left to narrow down results. For complex analysis and conversations, use Emma Assistant.
                </p>
              </div>
              <div className="flex items-center justify-center gap-4">
                <Button onClick={() => router.push(`/${tenantId}/chat`)} variant="outline" className="flex items-center gap-2">
                  <IconBrain className="h-4 w-4" />
                  Try Emma Assistant
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  </div>

    </div>
  )
}