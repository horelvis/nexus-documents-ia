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
const normalizeSearchResult = (rawResult: any) => {
  console.log('Raw search result:', rawResult)

  if (!rawResult) {
    return null
  }

  // Support both legacy flat results and the new backend shape that wraps data inside "document"
  const document = rawResult.document ?? rawResult
  const metadata = rawResult.metadata ?? document.metadata ?? {}

  const id =
    document.id ??
    metadata.doc_id ??
    metadata._id

  if (!id) {
    console.warn('Search result missing identifier. Skipping item.', rawResult)
    return null
  }

  const title =
    document.title ??
    metadata.title ??
    document.filename ??
    metadata.filename ??
    'Untitled document'

  const filename =
    document.filename ??
    metadata.filename ??
    title

  const baseDescription =
    document.description ??
    rawResult.description ??
    document.content ??
    rawResult.content ??
    metadata.summary ??
    ''

  const description =
    typeof baseDescription === 'string' && baseDescription.length > 0
      ? `${baseDescription.slice(0, 200)}${baseDescription.length > 200 ? '...' : ''}`
      : ''

  const score =
    rawResult.score ??
    rawResult.similarity_score ??
    metadata.score ??
    null

  const matchesSource =
    Array.isArray(rawResult.matches) && rawResult.matches.length > 0
      ? rawResult.matches
      : Array.isArray(rawResult.highlights) && rawResult.highlights.length > 0
        ? rawResult.highlights
        : []

  const matches = matchesSource.map((match: any) =>
    typeof match === 'string'
      ? { text: match }
      : {
          text: match?.text ?? '',
          score: match?.score ?? null
        }
  )

  const tags = document.tags ?? metadata.tags ?? []

  const normalized = {
    id,
    filename,
    title,
    description,
    score: score ?? undefined,
    matches,
    file_type: document.file_type ?? metadata.file_type ?? '',
    mime_type: document.mime_type ?? metadata.mime_type ?? '',
    file_size: document.file_size ?? metadata.file_size ?? null,
    category: document.category ?? metadata.category ?? null,
    tags,
    created_at: document.created_at ?? metadata.created_at ?? null,
    updated_at: document.updated_at ?? metadata.updated_at ?? null,
    indexed: document.indexed ?? metadata.indexed ?? document.status ?? metadata.status ?? null,
    tenant_id: document.tenant_id ?? metadata.tenant_id ?? null,
    download_url: document.download_url ?? rawResult.download_url ?? null
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
  const [searchType, setSearchType] = useState<'semantic' | 'hybrid' | 'keyword'>('keyword')

  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [tags, setTags] = useState('')
  const [showFilters, setShowFilters] = useState(false)
  const [fileSizeMin, setFileSizeMin] = useState('')
  const [fileSizeMax, setFileSizeMax] = useState('')

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

  // Local state for input to decouple typing from searching
  const [localQuery, setLocalQuery] = useState(searchQuery)

  // Sync local state with URL state (e.g. on back button or initial load)
  useEffect(() => {
    setLocalQuery(searchQuery)
  }, [searchQuery])

  // Sync local filter state with URL filters
  useEffect(() => {
    if (currentFilters.date_from) setDateFrom(currentFilters.date_from)
    if (currentFilters.date_to) setDateTo(currentFilters.date_to)
    if (currentFilters.tags) setTags(currentFilters.tags.join(', '))
    if (currentFilters.file_size_min) setFileSizeMin(currentFilters.file_size_min)
    if (currentFilters.file_size_max) setFileSizeMax(currentFilters.file_size_max)
  }, [currentFilters])

  // Auto-search if returning from preview with search context
  useEffect(() => {
    const queryFromUrl = searchParams.get('q')
    if (queryFromUrl && queryFromUrl.trim()) {
      performSearch(queryFromUrl)
    }
  }, []) // Only run once on mount

  const performSearch = useCallback(async (queryOverride?: string) => {
    const queryToUse = queryOverride !== undefined ? queryOverride : searchQuery;

    if (!queryToUse.trim()) {
      toast.error("Please enter a search query")
      return
    }

    if (queryToUse.trim().length < 3) {
      toast.error("Please enter at least 3 characters")
      return
    }

    setIsSearching(true)
    setSearchError(null)

    const activeFilters = {
      ...currentFilters,
      tags: tags ? tags.split(',').map(t => t.trim()).filter(Boolean) : undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      file_size_min: fileSizeMin ? parseInt(fileSizeMin) : undefined,
      file_size_max: fileSizeMax ? parseInt(fileSizeMax) : undefined
    }

    try {
      console.log('Starting search with params:', {
        query: queryToUse,
        limit: 20,
        search_type: searchType,
        filters: activeFilters
      })

      const response = await searchService.searchDocuments({
        query: queryToUse,
        limit: 20,
        search_type: searchType,
        ...activeFilters
      })


      console.log('Search response:', response)

      if (response.error) {
        console.error('Search error from response:', response.error)
        setSearchError(response.error)
      } else {
        console.log('Search results raw:', response.data)

        if (response.data && response.data.length > 0) {
          console.log('First result sample:', response.data[0])
          console.log('Search results structure check:', response.data?.map((r: any) => ({
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

  const handleSearchConfirm = () => {
    updateSearchQuery(localQuery)
    performSearch(localQuery)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !isSearching) {
      handleSearchConfirm()
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
    setLocalQuery("")
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
                  value={localQuery}
                  onChange={(e) => setLocalQuery(e.target.value)}
                  onKeyDown={handleKeyDown}
                  className="pl-10 border bg-background shadow-sm"
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
              <Button onClick={handleSearchConfirm} disabled={isSearching || localQuery.trim().length < 3}>
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
              <div className="space-y-2">
                <label className="text-sm font-medium flex items-center gap-2">
                  <IconFile className="h-4 w-4" />
                  Size (Bytes)
                </label>
                <div className="flex gap-2">
                  <Input
                    type="number"
                    placeholder="Min"
                    value={fileSizeMin}
                    onChange={(e) => setFileSizeMin(e.target.value)}
                    className="text-sm"
                  />
                  <Input
                    type="number"
                    placeholder="Max"
                    value={fileSizeMax}
                    onChange={(e) => setFileSizeMax(e.target.value)}
                    className="text-sm"
                  />
                </div>
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
