"use client"

import { useParams } from "next/navigation"
import { Suspense, useEffect, useState } from "react"
import { DocumentStats } from "@/components/dashboard/document-stats"
import { RecentActivity } from "@/components/dashboard/recent-activity"
import { QuickActions } from "@/components/dashboard/quick-actions"
import { SharedDocumentsPanel } from "@/components/dashboard/shared-documents-panel"
import { AIInsightsPanel } from "@/components/dashboard/ai-insights-panel"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import Link from "next/link"
import { Skeleton } from "@/components/ui/skeleton"
import { useLanguage } from "@/contexts/language-context";
import { useApiClient } from "@/lib/api-client"
export default function DashboardPage() {
  const params = useParams()
  const tenantId = params.tenantId as string
  const [activeWorkflows, setActiveWorkflows] = useState<number>(0)
  const [loadingWorkflows, setLoadingWorkflows] = useState<boolean>(false)
  const apiClient = useApiClient()
  const { t } = useLanguage()

  useEffect(() => {
    let isMounted = true
    let timeoutId: ReturnType<typeof setTimeout> | undefined
    const SUCCESS_INTERVAL = 60_000
    const FAILURE_INTERVAL = 5 * 60_000

    const fetchWorkflowSummary = async () => {
      let nextDelay = SUCCESS_INTERVAL
      try {
        setLoadingWorkflows(true)
        const response = await apiClient.get<any>('/temporalio/workflows/summary')
        if (!response.data || !isMounted) return

        const data = response.data
        const active = typeof data.active === 'number'
          ? data.active
          : Array.isArray(data.workflows)
            ? data.workflows.filter((w: any) => (w.status || '').toLowerCase() === 'running').length
            : 0

        setActiveWorkflows(active)
        nextDelay = SUCCESS_INTERVAL
      } catch (err) {
        if (isMounted) {
          setActiveWorkflows(0)
        }
        nextDelay = FAILURE_INTERVAL
      } finally {
        if (isMounted) {
          setLoadingWorkflows(false)
          timeoutId = setTimeout(fetchWorkflowSummary, nextDelay)
        }
      }
    }

    fetchWorkflowSummary()

    return () => {
      isMounted = false
      if (timeoutId) {
        clearTimeout(timeoutId)
      }
    }
  }, [apiClient])

  return (
    <div className="flex flex-col gap-6 py-4 md:py-6">
      {/* Welcome Section */}
      <div className="px-4 lg:px-6 dashboard-welcome">
        <h1 className="text-3xl font-bold mb-2">{t('dashboard.title')}</h1>
        <p className="text-muted-foreground">
          {t('dashboard.welcomeMessage')}
        </p>
      </div>

      {/* Quick CTA to Workflows */}
      <div className="px-4 lg:px-6">
        <Card>
          <CardContent className="flex items-center justify-between py-4">
            <div>
              <CardTitle className="text-lg">{t('dashboard.workflows.title')}</CardTitle>
              <CardDescription>{t('dashboard.workflows.description')}</CardDescription>
            </div>
            <div className="flex items-center gap-3">
              <Badge variant="secondary" className="text-xs">
                {loadingWorkflows ? t('dashboard.workflows.loading') : t('dashboard.workflows.active', { count: activeWorkflows })}
              </Badge>
              <Link href={`/${tenantId}/workflows`}>
                <Button>{t('dashboard.workflows.button')}</Button>
              </Link>
            </div>
          </CardContent>
        </Card>
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
        <SharedDocumentsPanel tenantId={tenantId} />
        <AIInsightsPanel tenantId={tenantId} />
      </div>
    </div>
  )
}
