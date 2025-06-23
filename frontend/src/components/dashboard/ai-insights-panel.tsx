"use client"

import { useEffect, useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { IconChartBar, IconAlertCircle } from "@tabler/icons-react"
import Link from "next/link"
import { useDashboardService, type AIInsight } from "@/lib/services/dashboard.service"

interface AIInsightsPanelProps {
  tenantId: string
}

export function AIInsightsPanel({ tenantId }: AIInsightsPanelProps) {
  const [insights, setInsights] = useState<AIInsight[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const dashboardService = useDashboardService()

  useEffect(() => {
    const loadAIInsights = async () => {
      setIsLoading(true)
      setError(null)
      
      try {
        const response = await dashboardService.getAIInsights()
        if (response.error) {
          setError(response.error)
        } else {
          setInsights(response.data?.insights || [])
        }
      } catch (err) {
        setError('Failed to load AI insights')
      } finally {
        setIsLoading(false)
      }
    }

    loadAIInsights()
  }, [])

  return (
    <Card>
      <CardHeader>
        <CardTitle>AI Insights</CardTitle>
        <CardDescription>Smart recommendations for your documents</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading ? (
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
        ) : error ? (
          <p className="text-sm text-muted-foreground text-center py-4">
            Failed to load insights
          </p>
        ) : insights.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-4">
            No insights available at this time
          </p>
        ) : (
          <div className="space-y-3">
            {insights.slice(0, 3).map((insight, index) => {
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
  )
}