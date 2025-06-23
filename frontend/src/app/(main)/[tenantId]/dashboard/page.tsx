"use client"

import { useParams } from "next/navigation"
import Link from "next/link"
import { Suspense, useEffect, useState } from "react"
import { DocumentStats } from "@/components/dashboard/document-stats"
import { RecentActivity } from "@/components/dashboard/recent-activity"
import { QuickActions } from "@/components/dashboard/quick-actions"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { IconChartBar, IconAlertCircle, IconShare2, IconUsers, IconLink, IconMail } from "@tabler/icons-react"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { useSharedDocumentsService, type ShareStatistics } from "@/lib/services/shared-documents.service"
import { useDashboardService, type AIInsight } from "@/lib/services/dashboard.service"
import { formatDistanceToNow } from "date-fns"

export default function DashboardPage() {
  const params = useParams()
  const tenantId = params.tenantId as string
  const sharedDocumentsService = useSharedDocumentsService()
  const dashboardService = useDashboardService()
  
  const [shareStats, setShareStats] = useState<ShareStatistics | null>(null)
  const [isLoadingShares, setIsLoadingShares] = useState(true)
  const [shareError, setShareError] = useState<string | null>(null)
  
  const [aiInsights, setAIInsights] = useState<AIInsight[]>([])
  const [isLoadingInsights, setIsLoadingInsights] = useState(true)
  const [insightsError, setInsightsError] = useState<string | null>(null)

  // Load shared documents statistics
  useEffect(() => {
    const loadShareStatistics = async () => {
      setIsLoadingShares(true)
      setShareError(null)
      
      try {
        const response = await sharedDocumentsService.getShareStatistics()
        if (response.error) {
          setShareError(response.error)
        } else {
          setShareStats(response.data)
        }
      } catch (err) {
        setShareError('Failed to load shared documents')
      } finally {
        setIsLoadingShares(false)
      }
    }

    loadShareStatistics()
  }, [sharedDocumentsService])
  
  // Load AI insights
  useEffect(() => {
    const loadAIInsights = async () => {
      setIsLoadingInsights(true)
      setInsightsError(null)
      
      try {
        const response = await dashboardService.getAIInsights()
        if (response.error) {
          setInsightsError(response.error)
        } else {
          setAIInsights(response.data?.insights || [])
        }
      } catch (err) {
        setInsightsError('Failed to load AI insights')
      } finally {
        setIsLoadingInsights(false)
      }
    }

    loadAIInsights()
  }, [dashboardService])

  return (
    <div className="flex flex-col gap-6 py-4 md:py-6">
      {/* Welcome Section */}
      <div className="px-4 lg:px-6">
        <h1 className="text-3xl font-bold mb-2">Dashboard</h1>
        <p className="text-muted-foreground">
          Welcome back! Here's an overview of your document workspace.
        </p>
      </div>

      {/* Document Stats */}
      <Suspense fallback={
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 px-4 lg:px-6">
          {[...Array(4)].map((_, i) => (
            <Card key={i}>
              <CardHeader className="pb-2">
                <Skeleton className="h-8 w-8 mb-2" />
                <Skeleton className="h-4 w-24" />
              </CardHeader>
              <CardContent>
                <Skeleton className="h-8 w-16" />
              </CardContent>
            </Card>
          ))}
        </div>
      }>
        <DocumentStats />
      </Suspense>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 gap-6 px-4 lg:px-6 @3xl/main:grid-cols-2">
        {/* Recent Activity */}
        <Suspense fallback={
          <Card className="h-full">
            <CardHeader>
              <Skeleton className="h-6 w-32" />
              <Skeleton className="h-4 w-48 mt-2" />
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {[...Array(5)].map((_, i) => (
                  <div key={i} className="flex items-start gap-3">
                    <Skeleton className="h-8 w-8 rounded-full" />
                    <div className="flex-1">
                      <Skeleton className="h-4 w-full" />
                      <Skeleton className="h-3 w-32 mt-2" />
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        }>
          <RecentActivity tenantId={tenantId} />
        </Suspense>

        {/* Quick Actions */}
        <QuickActions tenantId={tenantId} />
      </div>

      {/* Shared Documents and Insights */}
      <div className="grid grid-cols-1 gap-6 px-4 lg:px-6 @3xl/main:grid-cols-2">
        {/* Shared Documents */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <IconShare2 className="h-5 w-5" />
              Shared Documents
            </CardTitle>
            <CardDescription>Documents shared with external parties</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Summary Stats */}
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1">
                {isLoadingShares ? (
                  <Skeleton className="h-8 w-16" />
                ) : (
                  <p className="text-2xl font-bold">{shareStats?.total_shares || 0}</p>
                )}
                <p className="text-xs text-muted-foreground">Total shared</p>
              </div>
              <div className="space-y-1">
                {isLoadingShares ? (
                  <Skeleton className="h-8 w-16" />
                ) : (
                  <p className="text-2xl font-bold">{shareStats?.active_shares || 0}</p>
                )}
                <p className="text-xs text-muted-foreground">Active links</p>
              </div>
            </div>
            
            {/* Recent Shares */}
            <div className="space-y-3 pt-4 border-t">
              <h4 className="text-sm font-medium">Recent Shares</h4>
              
              {isLoadingShares ? (
                <div className="space-y-2">
                  {[1, 2, 3].map((i) => (
                    <div key={i} className="space-y-2">
                      <Skeleton className="h-4 w-3/4" />
                      <Skeleton className="h-3 w-1/2" />
                    </div>
                  ))}
                </div>
              ) : shareError ? (
                <p className="text-sm text-muted-foreground">Failed to load recent shares</p>
              ) : shareStats?.recent_shares && shareStats.recent_shares.length > 0 ? (
                <div className="space-y-2">
                  {shareStats.recent_shares.slice(0, 3).map((share) => {
                    const isExpired = share.expires_at && new Date(share.expires_at) < new Date()
                    const expiresIn = share.expires_at ? formatDistanceToNow(new Date(share.expires_at), { addSuffix: true }) : null
                    
                    return (
                      <div key={share.id} className="flex items-start justify-between gap-2">
                        <div className="flex-1 space-y-1">
                          <p className="text-sm font-medium leading-none truncate">
                            {share.document_filename || share.document_title || 'Untitled'}
                          </p>
                          <div className="flex items-center gap-2 text-xs text-muted-foreground">
                            {share.recipient_email ? (
                              <>
                                <IconMail className="h-3 w-3" />
                                <span className="truncate">{share.recipient_email}</span>
                              </>
                            ) : share.share_type === 'public' ? (
                              <>
                                <IconLink className="h-3 w-3" />
                                <span>Public link • {share.current_access_count} views</span>
                              </>
                            ) : (
                              <>
                                <IconUsers className="h-3 w-3" />
                                <span>{share.current_access_count} accesses</span>
                              </>
                            )}
                          </div>
                        </div>
                        <Badge 
                          variant={isExpired ? "destructive" : share.is_active ? "outline" : "secondary"} 
                          className="text-xs"
                        >
                          {isExpired ? "Expired" : !share.is_active ? "Revoked" : expiresIn ? `Expires ${expiresIn}` : "Active"}
                        </Badge>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">No recent shares</p>
              )}
            </div>

            <div className="pt-4 border-t">
              <Button variant="outline" className="w-full" asChild>
                <Link href={`/${tenantId}/shared`}>
                  <IconShare2 className="mr-2 h-4 w-4" />
                  Manage All Shares
                </Link>
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* AI Insights */}
        <Card>
          <CardHeader>
            <CardTitle>AI Insights</CardTitle>
            <CardDescription>Smart recommendations for your documents</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {isLoadingInsights ? (
              <div className="space-y-3">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="flex items-start gap-3 p-3">
                    <Skeleton className="h-5 w-5 rounded" />
                    <div className="flex-1 space-y-2">
                      <Skeleton className="h-4 w-3/4" />
                      <Skeleton className="h-3 w-full" />
                    </div>
                  </div>
                ))}
              </div>
            ) : insightsError ? (
              <p className="text-sm text-muted-foreground text-center py-4">
                Failed to load insights
              </p>
            ) : aiInsights.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-4">
                No insights available at this time
              </p>
            ) : (
              <div className="space-y-3">
                {aiInsights.slice(0, 3).map((insight, index) => {
                  const bgColor = insight.priority === 'high' 
                    ? 'bg-red-50 dark:bg-red-950/30' 
                    : insight.priority === 'medium'
                    ? 'bg-yellow-50 dark:bg-yellow-950/30'
                    : 'bg-blue-50 dark:bg-blue-950/30'
                  
                  const iconColor = insight.priority === 'high'
                    ? 'text-red-600'
                    : insight.priority === 'medium'
                    ? 'text-yellow-600'
                    : 'text-blue-600'
                  
                  const Icon = insight.type === 'warning' ? IconAlertCircle : IconChartBar
                  
                  return (
                    <div key={index} className={`flex items-start gap-3 p-3 rounded-lg ${bgColor}`}>
                      <Icon className={`h-5 w-5 ${iconColor} mt-0.5`} />
                      <div className="flex-1">
                        <p className="text-sm font-medium">{insight.title}</p>
                        <p className="text-xs text-muted-foreground mt-1">
                          {insight.description}
                        </p>
                        {insight.action_url && (
                          <Button
                            variant="link"
                            size="sm"
                            className="h-auto p-0 text-xs mt-2"
                            asChild
                          >
                            <Link href={insight.action_url}>
                              {insight.action_text || 'Take Action'}
                            </Link>
                          </Button>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
