"use client"

import { useEffect, useState } from "react"
import { 
  IconFile, 
  IconFileCheck, 
  IconClock, 
  IconAlertCircle,
  IconTrendingUp,
  IconTrendingDown,
  IconCloud,
  IconUsers,
  IconUpload
} from "@tabler/icons-react"
import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardAction,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { useDashboardService, type DashboardStats } from "@/lib/services/dashboard.service"
import { Skeleton } from "@/components/ui/skeleton"
import { formatFileSize } from "@/lib/document-utils"

export function DocumentStats() {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const dashboardService = useDashboardService()

  useEffect(() => {
    loadStats()
  }, [])

  const loadStats = async () => {
    setIsLoading(true)
    setError(null)
    
    try {
      const response = await dashboardService.getDashboardStats()
      
      if (response.error) {
        setError(response.error)
      } else if (response.data) {
        setStats(response.data)
      }
    } catch (err) {
      setError('Failed to load dashboard statistics')
      console.log('Failed to load stats:', err)
    } finally {
      setIsLoading(false)
    }
  }

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-4 px-4 lg:px-6 @xl/main:grid-cols-2 @5xl/main:grid-cols-4">
        {[1, 2, 3, 4].map((i) => (
          <Card key={i} className="@container/card">
            <CardHeader>
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-8 w-32 mt-2" />
            </CardHeader>
            <CardFooter className="flex-col items-start gap-1.5">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-3 w-3/4" />
            </CardFooter>
          </Card>
        ))}
      </div>
    )
  }

  const statCards = [
    {
      title: "Total Documents",
      value: stats?.total_documents || 0,
      description: "Documents in your library",
      trend: stats?.trends.documents || 0,
      icon: IconFile,
      footer: "All uploaded documents"
    },
    {
      title: "Processed",
      value: stats?.processed_documents || 0,
      description: "Ready for search & analysis",
      trend: stats?.trends.processed || 0,
      icon: IconFileCheck,
      footer: "Successfully indexed",
      color: "text-green-600"
    },
    {
      title: "Storage Used",
      value: formatFileSize(stats?.total_storage_bytes || 0),
      description: "Total storage consumption",
      trend: stats?.trends.storage || 0,
      icon: IconCloud,
      footer: "Across all documents"
    },
    {
      title: "Active Users",
      value: stats?.active_users || 0,
      description: "Team members this month",
      trend: stats?.trends.active_users || 0,
      icon: IconUsers,
      footer: "Accessed documents recently"
    },
    {
      title: "Recent Uploads",
      value: stats?.recent_uploads || 0,
      description: "New documents this week",
      trend: stats?.trends.recent_uploads || 0,
      icon: IconUpload,
      footer: "Added in last 7 days"
    }
  ]

  return (
    <div className="grid grid-cols-1 gap-4 px-4 lg:px-6 @xl/main:grid-cols-2 @5xl/main:grid-cols-4">
      {statCards.map((stat, index) => {
        const Icon = stat.icon
        const isPositiveTrend = stat.trend > 0
        const TrendIcon = isPositiveTrend ? IconTrendingUp : IconTrendingDown
        
        return (
          <Card key={index} className="@container/card bg-gradient-to-t from-primary/5 to-card shadow-xs">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardDescription>{stat.title}</CardDescription>
                <Icon className={`h-5 w-5 ${stat.color || 'text-muted-foreground'}`} />
              </div>
              <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
                {stat.value.toLocaleString()}
              </CardTitle>
              {stat.trend !== 0 && (
                <CardAction>
                  <Badge 
                    variant="outline" 
                    className={isPositiveTrend ? 'text-green-600' : 'text-red-600'}
                  >
                    <TrendIcon className="h-3 w-3" />
                    {isPositiveTrend ? '+' : ''}{stat.trend}%
                  </Badge>
                </CardAction>
              )}
            </CardHeader>
            <CardFooter className="flex-col items-start gap-1.5 text-sm">
              <div className="line-clamp-1 flex gap-2 font-medium">
                {stat.description}
              </div>
              <div className="text-muted-foreground">
                {stat.footer}
              </div>
            </CardFooter>
          </Card>
        )
      })}
      
      {/* Additional status cards for processing and errors */}
      {(stats?.processing_documents || 0) > 0 && (
        <Card className="@container/card border-yellow-200 bg-yellow-50 dark:border-yellow-900 dark:bg-yellow-950/20">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardDescription>Processing</CardDescription>
              <IconClock className="h-5 w-5 text-yellow-600" />
            </div>
            <CardTitle className="text-2xl font-semibold tabular-nums">
              {stats.processing_documents}
            </CardTitle>
          </CardHeader>
          <CardFooter className="text-sm text-yellow-800 dark:text-yellow-200">
            Documents being indexed
          </CardFooter>
        </Card>
      )}
      
      {(stats?.error_documents || 0) > 0 && (
        <Card className="@container/card border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-950/20">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardDescription>Errors</CardDescription>
              <IconAlertCircle className="h-5 w-5 text-red-600" />
            </div>
            <CardTitle className="text-2xl font-semibold tabular-nums">
              {stats.error_documents}
            </CardTitle>
          </CardHeader>
          <CardFooter className="text-sm text-red-800 dark:text-red-200">
            Need attention
          </CardFooter>
        </Card>
      )}
    </div>
  )
}