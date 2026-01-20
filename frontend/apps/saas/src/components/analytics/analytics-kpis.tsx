"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import {
  IconFile,
  IconUsers,
  IconDatabase,
  IconTrendingUp,
  IconTrendingDown,
  IconMinus
} from "@tabler/icons-react"

interface DashboardStats {
  total_documents: number
  processed_documents: number
  processing_documents: number
  error_documents: number
  total_storage_bytes: number
  active_users: number
  recent_uploads: number
  trends: {
    documents: number
    storage: number
    active_users: number
    processed: number
    recent_uploads: number
    error_rate: number
  }
}

interface AnalyticsKPIsProps {
  stats: DashboardStats | null
}

export function AnalyticsKPIs({ stats }: AnalyticsKPIsProps) {
  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  const getTrendIcon = (trend: number) => {
    if (trend > 0) return <IconTrendingUp className="h-4 w-4 text-green-500" />
    if (trend < 0) return <IconTrendingDown className="h-4 w-4 text-red-500" />
    return <IconMinus className="h-4 w-4 text-gray-500" />
  }

  const getTrendColor = (trend: number) => {
    if (trend > 0) return "text-green-600"
    if (trend < 0) return "text-red-600"
    return "text-gray-600"
  }

  const kpis = [
    {
      title: "Total Documents",
      value: stats?.total_documents || 0,
      icon: IconFile,
      trend: stats?.trends?.documents || 0,
      description: "All documents in system"
    },
    {
      title: "Active Users",
      value: stats?.active_users || 0,
      icon: IconUsers,
      trend: stats?.trends?.active_users || 0,
      description: "Users active in last 30 days"
    },
    {
      title: "Storage Used",
      value: formatBytes(stats?.total_storage_bytes || 0),
      icon: IconDatabase,
      trend: stats?.trends?.storage || 0,
      description: "Total storage consumption"
    },
    {
      title: "Recent Uploads",
      value: stats?.recent_uploads || 0,
      icon: IconTrendingUp,
      trend: stats?.trends?.recent_uploads || 0,
      description: "Documents uploaded this week"
    }
  ]

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
      {kpis.map((kpi, index) => (
        <Card key={index}>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              {kpi.title}
            </CardTitle>
            <kpi.icon className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{kpi.value}</div>
            <div className="flex items-center gap-2 mt-1">
              <div className={`flex items-center gap-1 text-xs ${getTrendColor(kpi.trend)}`}>
                {getTrendIcon(kpi.trend)}
                <span>{Math.abs(kpi.trend).toFixed(1)}%</span>
              </div>
              <span className="text-xs text-muted-foreground">vs last period</span>
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              {kpi.description}
            </p>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}