"use client"

import { useEffect, useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { IconChartBar, IconAlertCircle } from "@tabler/icons-react"
import Link from "next/link"
import { useDashboardService, type AIInsight } from "@/lib/services/dashboard.service"
import { useTranslation } from "@/lib/i18n/hooks"

export function AIInsightsPanel() {
  const { t } = useTranslation()
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
        <CardTitle>{t('dashboard.aiInsights.title')}</CardTitle>
        <CardDescription>{t('dashboard.aiInsights.description')}</CardDescription>
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
            {t('dashboard.aiInsights.failedToLoad')}
          </p>
        ) : insights.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-4">
            {t('dashboard.aiInsights.noInsights')}
          </p>
        ) : (
          <div className="space-y-3">
            {insights.slice(0, 3).map((insight, index) => {
              const bgColor = insight.priority === 'high'
                ? 'bg-red-500/10 dark:bg-red-500/10 hover:bg-red-500/15 dark:hover:bg-red-500/15'
                : insight.priority === 'medium'
                  ? 'bg-yellow-500/10 dark:bg-yellow-500/10 hover:bg-yellow-500/15 dark:hover:bg-yellow-500/15'
                  : 'bg-blue-500/10 dark:bg-blue-500/10 hover:bg-blue-500/15 dark:hover:bg-blue-500/15'

              const iconColor = insight.priority === 'high'
                ? 'text-red-600 dark:text-red-400'
                : insight.priority === 'medium'
                  ? 'text-yellow-600 dark:text-yellow-400'
                  : 'text-blue-600 dark:text-blue-400'

              const Icon = insight.type === 'warning' ? IconAlertCircle : IconChartBar

              return (
                <div key={index} className={`flex items-start gap-3 p-3 rounded-lg border border-border/40 transition-all duration-200 ${bgColor}`}>
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
                          {insight.action_text || t('dashboard.aiInsights.takeAction')}
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