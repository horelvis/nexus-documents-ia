"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  IconFile,
  IconUsers,
  IconDatabase,
  IconTrendingUp,
  IconTrendingDown,
  IconBarChart3,
  IconPieChart,
  IconCalendar,
  IconTag,
  IconLoader2,
  IconRefresh
} from "@tabler/icons-react"
import { AnalyticsKPIs } from "./analytics-kpis"
import { DocumentTypeChart } from "./document-type-chart"
import { CategoryChart } from "./category-chart"
import { TrendsChart } from "./trends-chart"
import { TopTagsChart } from "./top-tags-chart"
import { useAnalyticsData } from "@/lib/hooks/use-analytics-data"

interface AnalyticsDashboardProps {
  tenantId: string
}

export function AnalyticsDashboard({ tenantId }: AnalyticsDashboardProps) {
  const [timeRange, setTimeRange] = useState<"7d" | "30d" | "90d">("30d")
  const [isRefreshing, setIsRefreshing] = useState(false)

  const {
    dashboardStats,
    facetsData,
    trendsData,
    isLoading,
    error,
    refetch
  } = useAnalyticsData(tenantId, timeRange)

  const handleRefresh = async () => {
    setIsRefreshing(true)
    await refetch()
    setIsRefreshing(false)
  }

  if (error) {
    return (
      <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6">
        <div className="px-4 lg:px-6">
          <Card className="border-red-200">
            <CardContent className="pt-6">
              <div className="text-center">
                <p className="text-red-600 mb-4">Error loading analytics data</p>
                <Button onClick={handleRefresh} variant="outline">
                  <IconRefresh className="h-4 w-4 mr-2" />
                  Try Again
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6 py-4 md:gap-6 md:py-6">
      {/* Header */}
      <div className="px-4 lg:px-6">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold mb-2">Analytics Dashboard</h1>
            <p className="text-muted-foreground">
              Comprehensive insights into your document ecosystem
            </p>
          </div>
          <div className="flex items-center gap-4">
            <Select value={timeRange} onValueChange={(value: "7d" | "30d" | "90d") => setTimeRange(value)}>
              <SelectTrigger className="w-32">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="7d">Last 7 days</SelectItem>
                <SelectItem value="30d">Last 30 days</SelectItem>
                <SelectItem value="90d">Last 90 days</SelectItem>
              </SelectContent>
            </Select>
            <Button
              onClick={handleRefresh}
              disabled={isRefreshing}
              variant="outline"
              size="sm"
            >
              {isRefreshing ? (
                <IconLoader2 className="h-4 w-4 animate-spin" />
              ) : (
                <IconRefresh className="h-4 w-4" />
              )}
            </Button>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="px-4 lg:px-6">
        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
            {[...Array(4)].map((_, i) => (
              <Card key={i} className="animate-pulse">
                <CardHeader className="pb-2">
                  <div className="h-4 bg-muted rounded w-3/4"></div>
                </CardHeader>
                <CardContent>
                  <div className="h-8 bg-muted rounded w-1/2 mb-2"></div>
                  <div className="h-3 bg-muted rounded w-full"></div>
                </CardContent>
              </Card>
            ))}
          </div>
        ) : (
          <>
            {/* KPIs */}
            <AnalyticsKPIs stats={dashboardStats} />

            {/* Charts Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
              {/* Document Types Distribution */}
              <DocumentTypeChart
                data={facetsData?.facets?.find(f => f.field === 'file_type')?.buckets || []}
                totalDocuments={facetsData?.total_documents || 0}
              />

              {/* Categories Distribution */}
              <CategoryChart
                data={facetsData?.facets?.find(f => f.field === 'category')?.buckets || []}
                totalDocuments={facetsData?.total_documents || 0}
              />
            </div>

            {/* Trends and Tags */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
              {/* Trends Chart */}
              <div className="lg:col-span-2">
                <TrendsChart
                  data={trendsData}
                  timeRange={timeRange}
                />
              </div>

              {/* Top Tags */}
              <TopTagsChart
                data={facetsData?.facets?.find(f => f.field === 'tags')?.buckets || []}
              />
            </div>

            {/* Detailed Analytics Tabs */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <IconBarChart3 className="h-5 w-5" />
                  Detailed Analytics
                </CardTitle>
              </CardHeader>
              <CardContent>
                <Tabs defaultValue="overview" className="w-full">
                  <TabsList className="grid w-full grid-cols-4">
                    <TabsTrigger value="overview">Overview</TabsTrigger>
                    <TabsTrigger value="documents">Documents</TabsTrigger>
                    <TabsTrigger value="users">Users</TabsTrigger>
                    <TabsTrigger value="performance">Performance</TabsTrigger>
                  </TabsList>

                  <TabsContent value="overview" className="space-y-4">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <h4 className="font-medium">Document Health</h4>
                        <div className="space-y-1">
                          <div className="flex justify-between text-sm">
                            <span>Processed</span>
                            <span>{dashboardStats?.processed_documents || 0}</span>
                          </div>
                          <div className="flex justify-between text-sm">
                            <span>Processing</span>
                            <span>{dashboardStats?.processing_documents || 0}</span>
                          </div>
                          <div className="flex justify-between text-sm">
                            <span>Errors</span>
                            <span>{dashboardStats?.error_documents || 0}</span>
                          </div>
                        </div>
                      </div>

                      <div className="space-y-2">
                        <h4 className="font-medium">Storage Usage</h4>
                        <div className="text-2xl font-bold">
                          {dashboardStats?.total_storage_bytes
                            ? `${(dashboardStats.total_storage_bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
                            : '0 GB'
                          }
                        </div>
                        <p className="text-sm text-muted-foreground">
                          Total storage used
                        </p>
                      </div>
                    </div>
                  </TabsContent>

                  <TabsContent value="documents" className="space-y-4">
                    <div className="space-y-4">
                      <h4 className="font-medium">Document Distribution</h4>
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        {facetsData?.facets?.find(f => f.field === 'file_type')?.buckets?.map((bucket) => (
                          <div key={bucket.key} className="flex items-center justify-between p-3 border rounded">
                            <div className="flex items-center gap-2">
                              <IconFile className="h-4 w-4" />
                              <span className="text-sm font-medium">{bucket.key || 'Unknown'}</span>
                            </div>
                            <Badge variant="secondary">{bucket.count}</Badge>
                          </div>
                        ))}
                      </div>
                    </div>
                  </TabsContent>

                  <TabsContent value="users" className="space-y-4">
                    <div className="space-y-4">
                      <h4 className="font-medium">User Activity</h4>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <Card>
                          <CardContent className="pt-6">
                            <div className="flex items-center gap-4">
                              <IconUsers className="h-8 w-8 text-blue-500" />
                              <div>
                                <div className="text-2xl font-bold">{dashboardStats?.active_users || 0}</div>
                                <p className="text-sm text-muted-foreground">Active Users</p>
                              </div>
                            </div>
                          </CardContent>
                        </Card>

                        <Card>
                          <CardContent className="pt-6">
                            <div className="flex items-center gap-4">
                              <IconTrendingUp className="h-8 w-8 text-green-500" />
                              <div>
                                <div className="text-2xl font-bold">
                                  {dashboardStats?.trends?.active_users
                                    ? `${dashboardStats.trends.active_users.toFixed(1)}%`
                                    : '0%'
                                  }
                                </div>
                                <p className="text-sm text-muted-foreground">User Growth</p>
                              </div>
                            </div>
                          </CardContent>
                        </Card>
                      </div>
                    </div>
                  </TabsContent>

                  <TabsContent value="performance" className="space-y-4">
                    <div className="space-y-4">
                      <h4 className="font-medium">System Performance</h4>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="space-y-2">
                          <h5 className="text-sm font-medium">Processing Success Rate</h5>
                          <div className="text-lg font-bold">
                            {dashboardStats?.total_documents
                              ? `${((dashboardStats.processed_documents / dashboardStats.total_documents) * 100).toFixed(1)}%`
                              : '0%'
                            }
                          </div>
                        </div>

                        <div className="space-y-2">
                          <h5 className="text-sm font-medium">Error Rate</h5>
                          <div className="text-lg font-bold text-red-600">
                            {dashboardStats?.total_documents
                              ? `${((dashboardStats.error_documents / dashboardStats.total_documents) * 100).toFixed(1)}%`
                              : '0%'
                            }
                          </div>
                        </div>
                      </div>
                    </div>
                  </TabsContent>
                </Tabs>
              </CardContent>
            </Card>
          </>
        )}
      </div>
    </div>
  )
}