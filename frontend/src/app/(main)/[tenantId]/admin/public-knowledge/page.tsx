"use client"

import { useState, useEffect } from "react"
import { useParams } from "next/navigation"
import {
  IconDatabase,
  IconSearch,
  IconLoader2,
  IconAlertCircle,
  IconScale,
  IconGavel,
  IconFileText,
  IconWorld,
  IconBuilding,
  IconRefresh,
  IconCheck,
  IconX
} from "@tabler/icons-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { Switch } from "@/components/ui/switch"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Input } from "@/components/ui/input"
import { useNotifications } from "@/contexts/app-state-context"
import { useTranslation } from "@/lib/i18n/hooks"
import { useApiClient } from "@/lib/api-client"

interface PublicKnowledgeStats {
  total_documents: number
  verified_count: number
  documents_by_category: Record<string, number>
  documents_by_jurisdiction: Record<string, number>
  last_updated: string
}

interface PublicDocument {
  id: string
  title: string
  category: string
  jurisdiction: string
  legal_reference?: string
  verified: boolean
  created_at: string
  similarity_score?: number
}

interface SearchResult {
  query: string
  total_results: number
  search_time_ms: number
  results: PublicDocument[]
}

export default function PublicKnowledgePage() {
  const params = useParams()
  const tenantId = params.tenantId as string
  const { addNotification } = useNotifications()
  const { t } = useTranslation()
  const apiClient = useApiClient()

  const [stats, setStats] = useState<PublicKnowledgeStats | null>(null)
  const [searchResults, setSearchResults] = useState<SearchResult | null>(null)
  const [searchQuery, setSearchQuery] = useState("")
  const [isLoading, setIsLoading] = useState(true)
  const [isSearching, setIsSearching] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [enabledCategories, setEnabledCategories] = useState<Record<string, boolean>>({
    legislation: true,
    regulation: true,
    jurisprudence: true,
    template: true,
    guideline: true,
    reference: true,
    form: false,
    treaty: true
  })

  useEffect(() => {
    loadStats()
  }, [])

  const loadStats = async () => {
    setIsLoading(true)
    setError(null)

    try {
      const response = await apiClient.get<PublicKnowledgeStats>('/weaviate/public-knowledge/stats')

      if (response.error) {
        throw new Error(response.error)
      }

      setStats(response.data || null)
    } catch (error: any) {
      setError(error.message || 'Failed to load public knowledge stats')
      addNotification({
        type: 'error',
        title: t('publicKnowledgePage.notifications.loadFailed'),
        message: error.message || 'An error occurred'
      })
    } finally {
      setIsLoading(false)
    }
  }

  const handleSearch = async () => {
    if (!searchQuery.trim()) return

    setIsSearching(true)
    setError(null)

    try {
      const enabledCats = Object.entries(enabledCategories)
        .filter(([_, enabled]) => enabled)
        .map(([cat]) => cat)

      const response = await apiClient.post<SearchResult>('/weaviate/public-knowledge/search', {
        query: searchQuery,
        limit: 20,
        categories: enabledCats.length > 0 ? enabledCats : undefined,
        search_type: 'hybrid'
      })

      if (response.error) {
        throw new Error(response.error)
      }

      setSearchResults(response.data || null)
    } catch (error: any) {
      setError(error.message || 'Search failed')
      addNotification({
        type: 'error',
        title: t('publicKnowledgePage.notifications.searchFailed'),
        message: error.message || 'An error occurred'
      })
    } finally {
      setIsSearching(false)
    }
  }

  const toggleCategory = (category: string) => {
    setEnabledCategories(prev => ({
      ...prev,
      [category]: !prev[category]
    }))
  }

  const getCategoryIcon = (category: string) => {
    const icons: Record<string, React.ReactNode> = {
      legislation: <IconScale className="h-4 w-4" />,
      regulation: <IconBuilding className="h-4 w-4" />,
      jurisprudence: <IconGavel className="h-4 w-4" />,
      template: <IconFileText className="h-4 w-4" />,
      guideline: <IconFileText className="h-4 w-4" />,
      reference: <IconFileText className="h-4 w-4" />,
      form: <IconFileText className="h-4 w-4" />,
      treaty: <IconWorld className="h-4 w-4" />
    }
    return icons[category] || <IconFileText className="h-4 w-4" />
  }

  const getCategoryColor = (category: string) => {
    const colors: Record<string, string> = {
      legislation: 'blue',
      regulation: 'green',
      jurisprudence: 'purple',
      template: 'orange',
      guideline: 'cyan',
      reference: 'gray',
      form: 'yellow',
      treaty: 'red'
    }
    return colors[category] || 'gray'
  }

  const getJurisdictionLabel = (jurisdiction: string) => {
    const labels: Record<string, string> = {
      es: t('publicKnowledgePage.jurisdictions.es'),
      eu: t('publicKnowledgePage.jurisdictions.eu'),
      int: t('publicKnowledgePage.jurisdictions.int'),
      regional: t('publicKnowledgePage.jurisdictions.regional')
    }
    return labels[jurisdiction] || jurisdiction.toUpperCase()
  }

  const getCategoryLabel = (category: string) => {
    return t(`publicKnowledgePage.categories.${category}`) || category
  }

  return (
    <div className="container mx-auto p-6">
      <div className="mb-6">
        <h1 className="text-3xl font-bold">{t('publicKnowledgePage.title')}</h1>
        <p className="text-muted-foreground">
          {t('publicKnowledgePage.subtitle')}
        </p>
      </div>

      {/* Info Notice */}
      <Alert className="mb-6">
        <IconDatabase className="h-4 w-4" />
        <AlertDescription>
          {t('publicKnowledgePage.infoNotice')}
        </AlertDescription>
      </Alert>

      {/* Statistics Card */}
      <Card className="mb-6">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>{t('publicKnowledgePage.stats.title')}</CardTitle>
              <CardDescription>
                {t('publicKnowledgePage.stats.description')}
              </CardDescription>
            </div>
            <Button variant="outline" onClick={loadStats} disabled={isLoading}>
              <IconRefresh className={`mr-2 h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
              {t('common.refresh')}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <IconLoader2 className="h-6 w-6 animate-spin" />
              <span className="ml-2">{t('common.loading')}</span>
            </div>
          ) : error && !stats ? (
            <Alert variant="destructive">
              <IconAlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : stats ? (
            <div className="grid gap-4 md:grid-cols-4">
              <div className="rounded-lg border p-4">
                <div className="text-2xl font-bold">{stats.total_documents}</div>
                <div className="text-sm text-muted-foreground">{t('publicKnowledgePage.stats.totalDocs')}</div>
              </div>
              <div className="rounded-lg border p-4">
                <div className="text-2xl font-bold">{stats.verified_count}</div>
                <div className="text-sm text-muted-foreground">{t('publicKnowledgePage.stats.verifiedDocs')}</div>
              </div>
              <div className="rounded-lg border p-4">
                <div className="text-2xl font-bold">{Object.keys(stats.documents_by_category).length}</div>
                <div className="text-sm text-muted-foreground">{t('publicKnowledgePage.stats.categories')}</div>
              </div>
              <div className="rounded-lg border p-4">
                <div className="text-2xl font-bold">{Object.keys(stats.documents_by_jurisdiction).length}</div>
                <div className="text-sm text-muted-foreground">{t('publicKnowledgePage.stats.jurisdictions')}</div>
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>

      {/* Category Selection */}
      <Card className="mb-6">
        <CardHeader>
          <CardTitle>{t('publicKnowledgePage.categorySelection.title')}</CardTitle>
          <CardDescription>
            {t('publicKnowledgePage.categorySelection.description')}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-4">
            {Object.entries(enabledCategories).map(([category, enabled]) => (
              <div key={category} className="flex items-center justify-between rounded-lg border p-3">
                <div className="flex items-center gap-2">
                  {getCategoryIcon(category)}
                  <span className="text-sm font-medium">{getCategoryLabel(category)}</span>
                </div>
                <Switch
                  checked={enabled}
                  onCheckedChange={() => toggleCategory(category)}
                />
              </div>
            ))}
          </div>
          {stats && stats.documents_by_category && (
            <div className="mt-4 flex flex-wrap gap-2">
              {Object.entries(stats.documents_by_category).map(([category, count]) => (
                <Badge
                  key={category}
                  variant={enabledCategories[category] ? "default" : "outline"}
                  className="cursor-pointer"
                  onClick={() => toggleCategory(category)}
                >
                  {getCategoryLabel(category)}: {count}
                </Badge>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Search */}
      <Card className="mb-6">
        <CardHeader>
          <CardTitle>{t('publicKnowledgePage.search.title')}</CardTitle>
          <CardDescription>
            {t('publicKnowledgePage.search.description')}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex gap-2">
            <Input
              placeholder={t('publicKnowledgePage.search.placeholder')}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              className="flex-1"
            />
            <Button onClick={handleSearch} disabled={isSearching || !searchQuery.trim()}>
              {isSearching ? (
                <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <IconSearch className="mr-2 h-4 w-4" />
              )}
              {t('common.search')}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Search Results */}
      {searchResults && (
        <Card>
          <CardHeader>
            <CardTitle>
              {t('publicKnowledgePage.results.title').replace('{count}', String(searchResults.total_results))}
            </CardTitle>
            <CardDescription>
              {t('publicKnowledgePage.results.searchTime').replace('{ms}', String(searchResults.search_time_ms))}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {searchResults.results.length === 0 ? (
              <div className="text-center py-8">
                <IconSearch className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
                <p className="text-muted-foreground">
                  {t('publicKnowledgePage.results.noResults')}
                </p>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t('publicKnowledgePage.table.title')}</TableHead>
                    <TableHead>{t('publicKnowledgePage.table.category')}</TableHead>
                    <TableHead>{t('publicKnowledgePage.table.jurisdiction')}</TableHead>
                    <TableHead>{t('publicKnowledgePage.table.reference')}</TableHead>
                    <TableHead>{t('publicKnowledgePage.table.verified')}</TableHead>
                    <TableHead>{t('publicKnowledgePage.table.score')}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {searchResults.results.map((doc) => (
                    <TableRow key={doc.id}>
                      <TableCell className="font-medium max-w-xs truncate">
                        {doc.title}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className={`text-${getCategoryColor(doc.category)}-600`}>
                          <span className="mr-1">{getCategoryIcon(doc.category)}</span>
                          {getCategoryLabel(doc.category)}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant="secondary">
                          {getJurisdictionLabel(doc.jurisdiction)}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground max-w-xs truncate">
                        {doc.legal_reference || '-'}
                      </TableCell>
                      <TableCell>
                        {doc.verified ? (
                          <IconCheck className="h-4 w-4 text-green-500" />
                        ) : (
                          <IconX className="h-4 w-4 text-gray-400" />
                        )}
                      </TableCell>
                      <TableCell>
                        {doc.similarity_score ? (
                          <span className="text-sm">{(doc.similarity_score * 100).toFixed(0)}%</span>
                        ) : '-'}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      )}

      {/* Category Information */}
      <div className="mt-6 grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <IconScale className="h-4 w-4" />
              {t('publicKnowledgePage.categoryInfo.legislation.title')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              {t('publicKnowledgePage.categoryInfo.legislation.description')}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <IconBuilding className="h-4 w-4" />
              {t('publicKnowledgePage.categoryInfo.regulation.title')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              {t('publicKnowledgePage.categoryInfo.regulation.description')}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <IconGavel className="h-4 w-4" />
              {t('publicKnowledgePage.categoryInfo.jurisprudence.title')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              {t('publicKnowledgePage.categoryInfo.jurisprudence.description')}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <IconWorld className="h-4 w-4" />
              {t('publicKnowledgePage.categoryInfo.treaty.title')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              {t('publicKnowledgePage.categoryInfo.treaty.description')}
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
