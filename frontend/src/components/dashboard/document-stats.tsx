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
  IconUsers
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
import { useDocumentService } from "@/lib/services/document.service"
import { Skeleton } from "@/components/ui/skeleton"
import { formatFileSize } from "@/lib/document-utils"

interface DocumentStats {
  totalDocuments: number
  processedDocuments: number
  processingDocuments: number
  errorDocuments: number
  totalStorage: number
  activeUsers: number
  recentUploads: number
  trends: {
    documents: number
    storage: number
    users: number
    uploads: number
  }
}

export function DocumentStats() {
  const [stats, setStats] = useState<DocumentStats | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const documentService = useDocumentService()

  useEffect(() => {
    loadStats()
  }, [])

  const loadStats = async () => {
    setIsLoading(true)
    try {
      // For now, calculate stats from documents list
      // In production, this should be a dedicated stats endpoint
      const response = await documentService.getDocuments({
        per_page: 100,
        page: 1
      })
      
      if (response.data) {
        const documents = response.data.documents || []
        const totalDocs = response.data.pagination?.total || documents.length
        const processed = documents.filter(d => d.indexed === 'INDEXED').length
        const processing = documents.filter(d => d.indexed === 'PROCESSING').length
        const errors = documents.filter(d => d.indexed === 'INDEXING_ERROR').length
        const totalSize = documents.reduce((sum, doc) => sum + (doc.file_size || 0), 0)
        
        // Mock data for demo - in production these would come from API
        setStats({
          totalDocuments: totalDocs,
          processedDocuments: processed,
          processingDocuments: processing,
          errorDocuments: errors,
          totalStorage: totalSize,
          activeUsers: 12,
          recentUploads: 8,
          trends: {
            documents: 12.5,
            storage: 8.3,
            users: -5,
            uploads: 24
          }
        })
      }
    } catch (error) {
      console.error('Failed to load stats:', error)
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
      value: stats?.totalDocuments || 0,
      description: "Documents in your library",
      trend: stats?.trends.documents || 0,
      icon: IconFile,
      footer: "All uploaded documents"
    },
    {
      title: "Processed",
      value: stats?.processedDocuments || 0,
      description: "Ready for search & analysis",
      trend: stats?.trends.documents || 0,
      icon: IconFileCheck,
      footer: "Successfully indexed",
      color: "text-green-600"
    },
    {
      title: "Storage Used",
      value: formatFileSize(stats?.totalStorage || 0),
      description: "Total storage consumption",
      trend: stats?.trends.storage || 0,
      icon: IconCloud,
      footer: "Across all documents"
    },
    {
      title: "Active Users",
      value: stats?.activeUsers || 0,
      description: "Team members this month",
      trend: stats?.trends.users || 0,
      icon: IconUsers,
      footer: "Collaborating on documents"
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
      {(stats?.processingDocuments || 0) > 0 && (
        <Card className="@container/card border-yellow-200 bg-yellow-50 dark:border-yellow-900 dark:bg-yellow-950/20">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardDescription>Processing</CardDescription>
              <IconClock className="h-5 w-5 text-yellow-600" />
            </div>
            <CardTitle className="text-2xl font-semibold tabular-nums">
              {stats.processingDocuments}
            </CardTitle>
          </CardHeader>
          <CardFooter className="text-sm text-yellow-800 dark:text-yellow-200">
            Documents being indexed
          </CardFooter>
        </Card>
      )}
      
      {(stats?.errorDocuments || 0) > 0 && (
        <Card className="@container/card border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-950/20">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardDescription>Errors</CardDescription>
              <IconAlertCircle className="h-5 w-5 text-red-600" />
            </div>
            <CardTitle className="text-2xl font-semibold tabular-nums">
              {stats.errorDocuments}
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