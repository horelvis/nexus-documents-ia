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
import { useTranslation } from "@/lib/i18n/hooks"

const normalizeSearchResult = (rawResult: any, t: (key: string) => string) => {
  if (!rawResult) {
    return null
  }

  const document = rawResult.document ?? rawResult
  const metadata = rawResult.metadata ?? document.metadata ?? {}

  const id =
    document.id ??
    metadata.doc_id ??
    metadata._id

  if (!id) {
    console.warn(t('searchPage.processingResultError'), rawResult)
    return null
  }

  const title =
    document.title ??
    metadata.title ??
    document.filename ??
    metadata.filename ??
    t('searchPage.untitledDocument')

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
  return normalized
}

export const dynamic = 'force-dynamic'

export default function SimpleSearchPage() {
  const params = useParams()
  const router = useRouter()
  const searchParams = useSearchParams()
  const tenantId = params.tenantId as string
  const { t } = useTranslation()

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

  const [localQuery, setLocalQuery] = useState(searchQuery)

  useEffect(() => {
    setLocalQuery(searchQuery)
  }, [searchQuery])

  useEffect(() => {
    if (currentFilters.date_from) setDateFrom(currentFilters.date_from)
    if (currentFilters.date_to) setDateTo(currentFilters.date_to)
    if (currentFilters.tags) setTags(currentFilters.tags.join(', '))
    if (currentFilters.file_size_min) setFileSizeMin(String(currentFilters.file_size_min))
    if (currentFilters.file_size_max) setFileSizeMax(String(currentFilters.file_size_max))
  }, [currentFilters])

  useEffect(() => {
    const queryFromUrl = searchParams.get('q')
    if (queryFromUrl && queryFromUrl.trim()) {
      performSearch(queryFromUrl)
    }
  }, [])

  const performSearch = useCallback(async (queryOverride?: string) => {
    const queryToUse = queryOverride !== undefined ? queryOverride : searchQuery;

    if (!queryToUse.trim()) {
      toast.error(t('searchPage.error'))
      return
    }

    if (queryToUse.trim().length < 3) {
      toast.error(t('searchPage.minCharacters'))
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
      const response = await searchService.searchDocuments({
        query: queryToUse,
        limit: 20,
        search_type: searchType,
        ...activeFilters
      })

      if (response.error) {
        setSearchError(response.error)
      } else {
        setSearchResults(response.data || [])
        if (!response.data || response.data.length === 0) {
          toast.info(t('searchPage.noResults'))
        }
      }
    } catch (error: any) {
      setSearchError(error.message || t('searchPage.searchError'))
    } finally {
      setIsSearching(false)
    }
  }, [searchQuery, searchType, currentFilters, searchService, t, tags, dateFrom, dateTo, fileSizeMin, fileSizeMax])

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
      toast.error(t('searchPage.noResultsToAnalyze'))
      return
    }
    
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
      toast.error(t('searchPage.downloadUrlNotAvailable'))
    }
  }

  const handleDocumentShare = (document: any) => {
    toast.info(t('searchPage.shareComingSoon'))
  }

  const handleDocumentSignature = (document: any) => {
    router.push(`/${tenantId}/signatures/requests/new?document_id=${document.id}`)
  }

  return (
    <div className="flex-1 space-y-6 p-6">
      {/* Header */}
      <div className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight">{t('searchPage.title')}</h1>
        <p className="text-muted-foreground">
          {t('searchPage.subtitle')}
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
                {t('searchPage.quickSearch')}
                {getActiveFilterCount() > 0 && (
                  <Badge variant="secondary" className="text-xs">
                    {getActiveFilterCount()} {getActiveFilterCount() !== 1 ? t('searchPage.filtersActive', { count: getActiveFilterCount() }) : t('searchPage.filterActive', { count: getActiveFilterCount() })}
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
                  placeholder={t('searchPage.searchPlaceholder')}
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
                      <span>{t('searchPage.semantic')}</span>
                      <span className="text-xs text-muted-foreground">{t('searchPage.semanticDescription')}</span>
                    </div>
                  </SelectItem>
                  <SelectItem value="hybrid">
                    <div className="flex flex-col">
                      <span>{t('searchPage.hybrid')}</span>
                      <span className="text-xs text-muted-foreground">{t('searchPage.hybridDescription')}</span>
                    </div>
                  </SelectItem>
                  <SelectItem value="keyword">
                    <div className="flex flex-col">
                      <span>{t('searchPage.keyword')}</span>
                      <span className="text-xs text-muted-foreground">{t('searchPage.keywordDescription')}</span>
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
                {t('searchPage.searchButton')}
              </Button>
              {searchResults.length > 0 && (
                <Button variant="outline" onClick={clearSearch}>
                  {t('searchPage.clearButton')}
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
                {searchType === 'semantic' && t('searchPage.engineInfoSemantic')}
                {searchType === 'hybrid' && t('searchPage.engineInfoHybrid')}
                {searchType === 'keyword' && t('searchPage.engineInfoKeyword')}
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
              {t('searchPage.advancedFilters')}
            </Button>
            {showFilters && (
              <Badge variant="secondary" className="text-xs">
                {t('searchPage.optionalFilters')}
              </Badge>
            )}
          </div>

          {/* Advanced filters */}
          {showFilters && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 p-4 bg-muted/30 rounded-lg">
              <div className="space-y-2">
                <label className="text-sm font-medium flex items-center gap-2">
                  <IconTag className="h-4 w-4" />
                  {t('searchPage.tags')}
                </label>
                <Input
                  placeholder={t('searchPage.tagsPlaceholder')}
                  value={tags}
                  onChange={(e) => setTags(e.target.value)}
                  className="text-sm"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium flex items-center gap-2">
                  <IconCalendar className="h-4 w-4" />
                  {t('searchPage.dateFrom')}
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
                  {t('searchPage.dateTo')}
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
                  {t('searchPage.fileSize')}
                </label>
                <div className="flex gap-2">
                  <Input
                    type="number"
                    placeholder={t('searchPage.min')}
                    value={fileSizeMin}
                    onChange={(e) => setFileSizeMin(e.target.value)}
                    className="text-sm"
                  />
                  <Input
                    type="number"
                    placeholder={t('searchPage.max')}
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
        </div>
      </div>

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
                  {t('searchPage.resultsHeader', { count: searchResults.length })}
                </CardTitle>
                <Button onClick={askEmmaAboutResults} className="flex items-center gap-2">
                  <IconBrain className="h-4 w-4" />
                  {t('searchPage.askEmmaAboutResults')}
                </Button>
              </div>
            </CardHeader>
          </Card>

          {/* Search Results */}
          <SearchResults
            results={searchResults.map((result, index) => {
              return normalizeSearchResult(result, t)
            }).filter(doc => doc !== null)}
            onDocumentClick={(doc) => {
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
            emptyMessage={t('searchPage.noResults')}
          />
        </div>
      )}

      {/* Active Filters Summary */}
      {getActiveFilterCount() > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">{t('searchPage.activeFilters')}</CardTitle>
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
                <h3 className="text-lg font-medium">{t('searchPage.emptySearchTitle')}</h3>
                <p className="text-muted-foreground mt-2">
                  {t('searchPage.emptySearchDescription')}
                </p>
              </div>
              <div className="flex items-center justify-center gap-4">
                <Button onClick={() => router.push(`/${tenantId}/chat`)} variant="outline" className="flex items-center gap-2">
                  <IconBrain className="h-4 w-4" />
                  {t('searchPage.tryEmmaAssistant')}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
