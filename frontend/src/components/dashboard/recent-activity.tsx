"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import {
  IconFile,
  IconUpload,
  IconEye,
  IconDownload,
  IconEdit,
  IconTrash,
  IconUserPlus,
  IconRobot,
  IconAlertCircle,
  IconShare2
} from "@tabler/icons-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { useDashboardService, type ActivityLog } from "@/lib/services/dashboard.service"
import { getFileIcon, getRelativeTime } from "@/lib/document-utils"
import { ScrollArea } from "@/components/ui/scroll-area"
import { useTranslation } from "@/lib/i18n/hooks"

export function RecentActivity({ tenantId }: { tenantId: string }) {
  const { t } = useTranslation()
  const [activities, setActivities] = useState<ActivityLog[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const router = useRouter()
  const dashboardService = useDashboardService()

  useEffect(() => {
    loadRecentActivity()
  }, [])

  const loadRecentActivity = async () => {
    setIsLoading(true)
    setError(null)

    try {
      const response = await dashboardService.getRecentActivity(15)

      if (response.error) {
        setError(response.error)
      } else {
        setActivities(response.data?.activities || [])
      }
    } catch (err) {
      setError('Failed to load recent activity')
      console.error('Failed to load activity:', err)
    } finally {
      setIsLoading(false)
    }
  }

  const getActivityIcon = (type: string) => {
    switch (type) {
      case 'document_upload':
        return <IconUpload className="h-4 w-4" />
      case 'document_view':
        return <IconEye className="h-4 w-4" />
      case 'document_share':
        return <IconShare2 className="h-4 w-4" />
      case 'document_download':
        return <IconDownload className="h-4 w-4" />
      case 'document_edit':
        return <IconEdit className="h-4 w-4" />
      case 'document_delete':
        return <IconTrash className="h-4 w-4" />
      case 'agent_execution':
        return <IconRobot className="h-4 w-4" />
      case 'user_action':
        return <IconUserPlus className="h-4 w-4" />
      case 'error':
        return <IconAlertCircle className="h-4 w-4" />
      default:
        return <IconFile className="h-4 w-4" />
    }
  }

  const getActivityColor = (type: string) => {
    switch (type) {
      case 'document_upload':
        return 'text-blue-600 dark:text-blue-400 bg-blue-500/10 dark:bg-blue-500/10'
      case 'document_view':
        return 'text-purple-600 dark:text-purple-400 bg-purple-500/10 dark:bg-purple-500/10'
      case 'document_share':
        return 'text-teal-600 dark:text-teal-400 bg-teal-500/10 dark:bg-teal-500/10'
      case 'document_download':
        return 'text-green-600 dark:text-green-400 bg-green-500/10 dark:bg-green-500/10'
      case 'document_edit':
        return 'text-yellow-600 dark:text-yellow-400 bg-yellow-500/10 dark:bg-yellow-500/10'
      case 'document_delete':
        return 'text-red-600 dark:text-red-400 bg-red-500/10 dark:bg-red-500/10'
      case 'agent_execution':
        return 'text-indigo-600 dark:text-indigo-400 bg-indigo-500/10 dark:bg-indigo-500/10'
      case 'user_action':
        return 'text-cyan-600 dark:text-cyan-400 bg-cyan-500/10 dark:bg-cyan-500/10'
      case 'error':
        return 'text-red-600 dark:text-red-400 bg-red-500/10 dark:bg-red-500/10'
      default:
        return 'text-gray-600 dark:text-gray-400 bg-gray-500/10 dark:bg-gray-500/10'
    }
  }

  const handleActivityClick = (activity: ActivityLog) => {
    if (activity.metadata?.document_id) {
      router.push(`/${tenantId}/documents/${activity.metadata.document_id}`)
    } else {
      router.push(`/${tenantId}/documents`)
    }
  }

  return (
    <Card className="h-full">
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle>{t('dashboard.recentActivity.title')}</CardTitle>
          <CardDescription>{t('dashboard.recentActivity.description')}</CardDescription>
        </div>
        <Button variant="outline" size="sm" onClick={() => router.push(`/${tenantId}/documents`)}>
          {t('dashboard.recentActivity.viewAll')}
        </Button>
      </CardHeader>
      <CardContent className="p-0">
        <ScrollArea className="h-[400px]">
          {isLoading ? (
            <div className="space-y-3 p-6">
              {[1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="flex items-start gap-3">
                  <Skeleton className="h-10 w-10 rounded-full" />
                  <div className="flex-1 space-y-2">
                    <Skeleton className="h-4 w-3/4" />
                    <Skeleton className="h-3 w-1/2" />
                  </div>
                </div>
              ))}
            </div>
          ) : activities.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <IconFile className="h-12 w-12 text-muted-foreground mb-4" />
              <p className="text-sm text-muted-foreground">{t('dashboard.recentActivity.empty')}</p>
            </div>
          ) : (
            <div className="divide-y">
              {activities.map((activity) => (
                <div
                  key={activity.id}
                  className="flex items-start gap-3 p-4 hover:bg-muted/50 transition-colors cursor-pointer"
                  onClick={() => handleActivityClick(activity)}
                >
                  <div className={`rounded-full p-2 ${getActivityColor(activity.type)}`}>
                    {activity.metadata?.filename && activity.metadata?.file_type ?
                      getFileIcon(activity.metadata.file_type, activity.metadata.mime_type, activity.metadata.filename, 'sm') :
                      getActivityIcon(activity.type)
                    }
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium truncate">{activity.title}</p>
                        <p className="text-sm text-muted-foreground truncate">{activity.description}</p>
                      </div>
                      <Badge variant="outline" className="text-xs shrink-0">
                        {getRelativeTime(activity.timestamp)}
                      </Badge>
                    </div>
                    {activity.user_name && (
                      <p className="text-xs text-muted-foreground mt-1">{t('dashboard.recentActivity.by', { user: activity.user_name })}</p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </ScrollArea>
      </CardContent>
    </Card>
  )
}