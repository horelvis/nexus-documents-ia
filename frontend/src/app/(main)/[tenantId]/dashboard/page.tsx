"use client"

import { useParams } from "next/navigation"
import { DocumentStats } from "@/components/dashboard/document-stats"
import { RecentActivity } from "@/components/dashboard/recent-activity"
import { QuickActions } from "@/components/dashboard/quick-actions"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { Button } from "@/components/ui/button"
import { IconChartBar, IconAlertCircle } from "@tabler/icons-react"

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
      <DocumentStats />

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 gap-6 px-4 lg:px-6 @3xl/main:grid-cols-2">
        {/* Recent Activity */}
        <RecentActivity tenantId={tenantId} />

        {/* Quick Actions */}
        <QuickActions tenantId={tenantId} />
      </div>

      {/* Storage Usage and Insights */}
      <div className="grid grid-cols-1 gap-6 px-4 lg:px-6 @3xl/main:grid-cols-2">
        {/* Storage Usage */}
        <Card>
          <CardHeader>
            <CardTitle>Storage Usage</CardTitle>
            <CardDescription>Your plan includes 10 GB of storage</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span>Used</span>
                <span className="font-medium">3.2 GB of 10 GB</span>
              </div>
              <Progress value={32} className="h-2" />
            </div>
            
            <div className="space-y-2 pt-4">
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Documents</span>
                <span>2.1 GB</span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Images</span>
                <span>892 MB</span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Others</span>
                <span>208 MB</span>
              </div>
            </div>

            <div className="pt-4 border-t">
              <Button variant="outline" className="w-full">
                <IconChartBar className="mr-2 h-4 w-4" />
                View Detailed Analytics
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
