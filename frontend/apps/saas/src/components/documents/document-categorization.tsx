'use client'

import { useState, useEffect, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  IconLoader2,
  IconSparkles,
  IconCheck,
  IconX,
  IconAlertCircle,
  IconRefresh,
  IconTags,
  IconCategory,
  IconChartBar
} from '@tabler/icons-react'
import { useToast } from '@/hooks/use-toast'
import { useApiClient } from '@/lib/api-client'

interface CategoryStats {
  total_documents: number
  categorized: number
  pending: number
  by_category: Record<string, number>
  by_tag: Record<string, number>
}

interface CategorizeResult {
  document_id: string
  status: 'success' | 'failed' | 'skipped'
  category?: string
  tags?: string[]
  confidence?: number
  error?: string
  reason?: string
}

export function DocumentCategorization() {
  const [isProcessing, setIsProcessing] = useState(false)
  const [stats, setStats] = useState<CategoryStats | null>(null)
  const [results, setResults] = useState<CategorizeResult[]>([])
  const [progress, setProgress] = useState(0)
  const { toast } = useToast()
  const apiClient = useApiClient()

  const loadStats = useCallback(async () => {
    try {
      const response = await apiClient.get<CategoryStats>('/categorization/stats')
      if (response.data) {
        setStats(response.data)
      } else if (response.error) {
        toast({
          title: "Error loading stats",
          description: response.error,
          variant: "destructive"
        })
      }
    } catch (error) {
      console.error('Failed to load stats:', error)
      toast({
        title: "Error",
        description: "Failed to load categorization stats",
        variant: "destructive"
      })
    }
  }, [apiClient, toast])

  const categorizeAll = async () => {
    setIsProcessing(true)
    setProgress(0)
    setResults([])

    try {
      const response = await apiClient.post('/categorization/categorize', {
        categorize_all_pending: true,
        include_tags: true,
        force_recategorize: false
      })

      if (response.data) {
        const data = response.data as any
        setResults(data.results)
        
        toast({
          title: "Categorization Complete",
          description: `Processed ${data.processed} documents successfully. ${data.failed} failed.`,
          variant: data.failed > 0 ? "destructive" : "default"
        })
        
        // Reload stats
        await loadStats()
      } else if (response.error) {
        throw new Error(response.error)
      }
    } catch (error) {
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to categorize documents",
        variant: "destructive"
      })
    } finally {
      setIsProcessing(false)
    }
  }

  const scheduleBatch = async () => {
    try {
      const response = await apiClient.post('/categorization/schedule-batch?batch_size=100')

      if (!response.error) {
        toast({
          title: "Batch Scheduled",
          description: "Background categorization has been scheduled",
        })
      } else {
        throw new Error(response.error)
      }
    } catch (error) {
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to schedule batch",
        variant: "destructive"
      })
    }
  }

  useEffect(() => {
    loadStats()
  }, [loadStats])

  return (
    <div className="space-y-6">
      {/* Stats Overview */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <IconChartBar className="h-5 w-5" />
                Categorization Overview
              </CardTitle>
              <CardDescription>
                Document categorization and tagging statistics
              </CardDescription>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={loadStats}
              disabled={isProcessing}
            >
              <IconRefresh className="h-4 w-4 mr-2" />
              Refresh
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {stats && (
            <div className="space-y-4">
              <div className="grid grid-cols-3 gap-4">
                <div className="text-center">
                  <div className="text-2xl font-bold">{stats.total_documents}</div>
                  <div className="text-sm text-muted-foreground">Total Documents</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold text-green-600">{stats.categorized}</div>
                  <div className="text-sm text-muted-foreground">Categorized</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold text-orange-600">{stats.pending}</div>
                  <div className="text-sm text-muted-foreground">Pending</div>
                </div>
              </div>

              {stats.categorized > 0 && (
                <Progress 
                  value={(stats.categorized / stats.total_documents) * 100} 
                  className="h-2"
                />
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Actions */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <IconSparkles className="h-5 w-5" />
            Automatic Categorization
          </CardTitle>
          <CardDescription>
            Use AI to automatically categorize and tag your documents
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex gap-4">
            <Button
              onClick={categorizeAll}
              disabled={isProcessing || stats?.pending === 0}
              className="flex-1"
            >
              {isProcessing ? (
                <>
                  <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                  Processing...
                </>
              ) : (
                <>
                  <IconCategory className="mr-2 h-4 w-4" />
                  Categorize All Pending ({stats?.pending || 0})
                </>
              )}
            </Button>

            <Button
              variant="outline"
              onClick={scheduleBatch}
              disabled={isProcessing}
            >
              <IconRefresh className="mr-2 h-4 w-4" />
              Schedule Batch
            </Button>
          </div>

          {isProcessing && (
            <Alert>
              <IconLoader2 className="h-4 w-4 animate-spin" />
              <AlertDescription>
                Processing documents... This may take a few minutes.
              </AlertDescription>
            </Alert>
          )}
        </CardContent>
      </Card>

      {/* Results */}
      {results.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Processing Results</CardTitle>
          </CardHeader>
          <CardContent>
            <Tabs defaultValue="summary">
              <TabsList>
                <TabsTrigger value="summary">Summary</TabsTrigger>
                <TabsTrigger value="details">Details</TabsTrigger>
              </TabsList>

              <TabsContent value="summary" className="space-y-4">
                <div className="grid grid-cols-3 gap-4">
                  <div className="flex items-center gap-2">
                    <IconCheck className="h-5 w-5 text-green-600" />
                    <span className="font-medium">
                      {results.filter(r => r.status === 'success').length} Success
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <IconX className="h-5 w-5 text-red-600" />
                    <span className="font-medium">
                      {results.filter(r => r.status === 'failed').length} Failed
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <IconAlertCircle className="h-5 w-5 text-yellow-600" />
                    <span className="font-medium">
                      {results.filter(r => r.status === 'skipped').length} Skipped
                    </span>
                  </div>
                </div>

                {/* Category Distribution */}
                <div>
                  <h4 className="font-medium mb-2">Categories Assigned</h4>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(
                      results
                        .filter(r => r.category)
                        .reduce((acc, r) => {
                          acc[r.category!] = (acc[r.category!] || 0) + 1
                          return acc
                        }, {} as Record<string, number>)
                    ).map(([category, count]) => (
                      <Badge key={category} variant="secondary">
                        {category} ({count})
                      </Badge>
                    ))}
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="details">
                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {results.map((result) => (
                    <div
                      key={result.document_id}
                      className="flex items-center justify-between p-2 border rounded"
                    >
                      <div className="flex items-center gap-2">
                        {result.status === 'success' && (
                          <IconCheck className="h-4 w-4 text-green-600" />
                        )}
                        {result.status === 'failed' && (
                          <IconX className="h-4 w-4 text-red-600" />
                        )}
                        {result.status === 'skipped' && (
                          <IconAlertCircle className="h-4 w-4 text-yellow-600" />
                        )}
                        <span className="text-sm font-mono">
                          {result.document_id.slice(0, 8)}...
                        </span>
                      </div>

                      <div className="flex items-center gap-2">
                        {result.category && (
                          <Badge variant="outline">{result.category}</Badge>
                        )}
                        {result.confidence && (
                          <span className="text-xs text-muted-foreground">
                            {(result.confidence * 100).toFixed(0)}%
                          </span>
                        )}
                        {result.tags && result.tags.length > 0 && (
                          <div className="flex items-center gap-1">
                            <IconTags className="h-3 w-3" />
                            <span className="text-xs">{result.tags.length}</span>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      )}

      {/* Categories & Tags */}
      {stats && (stats.by_category || stats.by_tag) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Categories */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Document Categories</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {Object.entries(stats.by_category || {}).map(([category, count]) => (
                  <div key={category} className="flex items-center justify-between">
                    <Badge variant="secondary">{category}</Badge>
                    <span className="text-sm text-muted-foreground">{count}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Tags */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Popular Tags</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-2">
                {Object.entries(stats.by_tag || {})
                  .sort(([, a], [, b]) => b - a)
                  .slice(0, 20)
                  .map(([tag, count]) => (
                    <Badge key={tag} variant="outline">
                      {tag} ({count})
                    </Badge>
                  ))}
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}
