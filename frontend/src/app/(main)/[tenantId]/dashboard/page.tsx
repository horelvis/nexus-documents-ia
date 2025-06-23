"use client"

import { useParams } from "next/navigation"
import { Suspense } from "react"
import { DocumentStats } from "@/components/dashboard/document-stats"
import { RecentActivity } from "@/components/dashboard/recent-activity"
import { QuickActions } from "@/components/dashboard/quick-actions"
import { SharedDocumentsPanel } from "@/components/dashboard/shared-documents-panel"
import { AIInsightsPanel } from "@/components/dashboard/ai-insights-panel"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"

export default function DashboardPage() {
  const params = useParams()
  const tenantId = params.tenantId as string

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
        <SharedDocumentsPanel tenantId={tenantId} />
        <AIInsightsPanel tenantId={tenantId} />
      </div>
    </div>
  )
}
