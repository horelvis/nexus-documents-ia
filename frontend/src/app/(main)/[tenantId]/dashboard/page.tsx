"use client"

import { useParams } from "next/navigation"
import Link from "next/link"
import { Suspense } from "react"
import { DocumentStats } from "@/components/dashboard/document-stats"
import { RecentActivity } from "@/components/dashboard/recent-activity"
import { QuickActions } from "@/components/dashboard/quick-actions"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { IconChartBar, IconAlertCircle, IconShare2, IconUsers, IconLink, IconMail } from "@tabler/icons-react"
import { Badge } from "@/components/ui/badge"
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
                <p className="text-2xl font-bold">24</p>
                <p className="text-xs text-muted-foreground">Total shared</p>
              </div>
              <div className="space-y-1">
                <p className="text-2xl font-bold">18</p>
                <p className="text-xs text-muted-foreground">Active links</p>
              </div>
            </div>
            
            {/* Recent Shares */}
            <div className="space-y-3 pt-4 border-t">
              <h4 className="text-sm font-medium">Recent Shares</h4>
              
              <div className="space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 space-y-1">
                    <p className="text-sm font-medium leading-none">Contract_Q4_2024.pdf</p>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <IconMail className="h-3 w-3" />
                      <span>john.doe@company.com</span>
                    </div>
                  </div>
                  <Badge variant="secondary" className="text-xs">
                    Expires in 3 days
                  </Badge>
                </div>
                
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 space-y-1">
                    <p className="text-sm font-medium leading-none">Product_Roadmap.docx</p>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <IconLink className="h-3 w-3" />
                      <span>Public link • 5 views</span>
                    </div>
                  </div>
                  <Badge variant="outline" className="text-xs">
                    Active
                  </Badge>
                </div>
                
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 space-y-1">
                    <p className="text-sm font-medium leading-none">Financial_Report.xlsx</p>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <IconUsers className="h-3 w-3" />
                      <span>3 recipients</span>
                    </div>
                  </div>
                  <Badge variant="destructive" className="text-xs">
                    Expired
                  </Badge>
                </div>
              </div>
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
            <div className="space-y-3">
              <div className="flex items-start gap-3 p-3 rounded-lg bg-blue-50 dark:bg-blue-950/30">
                <IconAlertCircle className="h-5 w-5 text-blue-600 mt-0.5" />
                <div>
                  <p className="text-sm font-medium">5 documents need categorization</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Organize your recent uploads for better search results
                  </p>
                </div>
              </div>
              
              <div className="flex items-start gap-3 p-3 rounded-lg bg-green-50 dark:bg-green-950/30">
                <IconChartBar className="h-5 w-5 text-green-600 mt-0.5" />
                <div>
                  <p className="text-sm font-medium">Contract analysis available</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    3 contracts can be analyzed for key terms and dates
                  </p>
                </div>
              </div>
              
              <div className="flex items-start gap-3 p-3 rounded-lg bg-purple-50 dark:bg-purple-950/30">
                <IconAlertCircle className="h-5 w-5 text-purple-600 mt-0.5" />
                <div>
                  <p className="text-sm font-medium">Enable smart summaries</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Get AI-generated summaries for long documents
                  </p>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
