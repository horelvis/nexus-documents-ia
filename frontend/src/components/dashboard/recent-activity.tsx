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
  IconAlertCircle
} from "@tabler/icons-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { useDocumentService } from "@/lib/services/document.service"
import { getFileIcon, getRelativeTime } from "@/lib/document-utils"
import { ScrollArea } from "@/components/ui/scroll-area"

interface Activity {
  id: string
  type: 'upload' | 'view' | 'download' | 'edit' | 'delete' | 'agent' | 'user' | 'error'
  title: string
  description: string
  timestamp: string
  user?: string
  documentId?: string
  documentName?: string
  fileType?: string
  mimeType?: string
  metadata?: any
}

export function RecentActivity({ tenantId }: { tenantId: string }) {
  const [activities, setActivities] = useState<Activity[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const router = useRouter()
  const documentService = useDocumentService()

  useEffect(() => {
    loadRecentActivity()
  }, [])

  const loadRecentActivity = async () => {
    setIsLoading(true)
    try {
      // Get recent documents as activity
      const response = await documentService.getDocuments({
        per_page: 10,
        page: 1
      })
      
      if (response.data) {
        const documents = response.data.documents || []
        
        // Convert documents to activities
        const docActivities: Activity[] = documents.map(doc => ({
          id: doc.id,
          type: 'upload',
          title: 'Document uploaded',
          description: doc.title || doc.filename,
          timestamp: doc.created_at,
          documentId: doc.id,
          documentName: doc.filename,
          fileType: doc.file_type,
          mimeType: doc.mime_type,
          user: 'You' // In production, this would show the actual user
        }))
        
        // Add some mock activities for demo
        const mockActivities: Activity[] = [
          {
            id: 'act-1',
            type: 'agent',
            title: 'AI Agent activated',
            description: 'Financial Analysis Assistant started processing quarterly report',
            timestamp: new Date(Date.now() - 1000 * 60 * 30).toISOString(),
            user: 'System'
          },
          {
            id: 'act-2',
            type: 'view',
            title: 'Document viewed',
            description: 'Contract_2024_Q4.pdf',
            timestamp: new Date(Date.now() - 1000 * 60 * 45).toISOString(),
            user: 'Sarah Chen'
          },
          {
            id: 'act-3',
            type: 'user',
            title: 'New team member',
            description: 'Michael Park joined the workspace',
            timestamp: new Date(Date.now() - 1000 * 60 * 60 * 2).toISOString(),
            user: 'Admin'
          },
          {
            id: 'act-4',
            type: 'download',
            title: 'Document downloaded',
            description: 'Financial_Report_2024.xlsx',
            timestamp: new Date(Date.now() - 1000 * 60 * 60 * 3).toISOString(),
            user: 'John Doe'
          }
        ]
        
        // Combine and sort by timestamp
        const allActivities = [...docActivities, ...mockActivities]
          .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
          .slice(0, 10)
        
        setActivities(allActivities)
      }
    } catch (error) {
      console.error('Failed to load activity:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const getActivityIcon = (type: Activity['type']) => {
    switch (type) {
      case 'upload':
        return <IconUpload className="h-4 w-4" />
      case 'view':
        return <IconEye className="h-4 w-4" />
      case 'download':
        return <IconDownload className="h-4 w-4" />
      case 'edit':
        return <IconEdit className="h-4 w-4" />
      case 'delete':
        return <IconTrash className="h-4 w-4" />
      case 'agent':
        return <IconRobot className="h-4 w-4" />
      case 'user':
        return <IconUserPlus className="h-4 w-4" />
      case 'error':
        return <IconAlertCircle className="h-4 w-4" />
      default:
        return <IconFile className="h-4 w-4" />
    }
  }

  const getActivityColor = (type: Activity['type']) => {
    switch (type) {
      case 'upload':
        return 'text-blue-600 bg-blue-50 dark:bg-blue-950/30'
      case 'view':
        return 'text-purple-600 bg-purple-50 dark:bg-purple-950/30'
      case 'download':
        return 'text-green-600 bg-green-50 dark:bg-green-950/30'
      case 'edit':
        return 'text-yellow-600 bg-yellow-50 dark:bg-yellow-950/30'
      case 'delete':
        return 'text-red-600 bg-red-50 dark:bg-red-950/30'
      case 'agent':
        return 'text-indigo-600 bg-indigo-50 dark:bg-indigo-950/30'
      case 'user':
        return 'text-teal-600 bg-teal-50 dark:bg-teal-950/30'
      case 'error':
        return 'text-red-600 bg-red-50 dark:bg-red-950/30'
      default:
        return 'text-gray-600 bg-gray-50 dark:bg-gray-950/30'
    }
  }

  const handleActivityClick = (activity: Activity) => {
    if (activity.documentId) {
      router.push(`/${tenantId}/documents`)
    }
  }

  return (
    <Card className="h-full">
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle>Recent Activity</CardTitle>
          <CardDescription>Latest actions in your workspace</CardDescription>
        </div>
        <Button variant="outline" size="sm" onClick={() => router.push(`/${tenantId}/documents`)}>
          View All
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
              <p className="text-sm text-muted-foreground">No recent activity</p>
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
                    {activity.documentName && activity.fileType ? 
                      getFileIcon(activity.fileType, activity.mimeType, activity.documentName, 'sm') :
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
                    {activity.user && (
                      <p className="text-xs text-muted-foreground mt-1">by {activity.user}</p>
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