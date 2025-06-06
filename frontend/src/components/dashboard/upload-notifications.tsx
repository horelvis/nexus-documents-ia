"use client"

import { useState, useEffect } from "react"
import { 
  IconCheck, 
  IconX, 
  IconCloudUpload,
  IconBell 
} from "@tabler/icons-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"

interface UploadNotification {
  id: string
  type: 'success' | 'error' | 'info'
  title: string
  message: string
  timestamp: Date
  fileCount?: number
  autoHide?: boolean
}

interface UploadNotificationsProps {
  notifications: UploadNotification[]
  onDismiss: (id: string) => void
}

export function UploadNotifications({ notifications, onDismiss }: UploadNotificationsProps) {
  const [visibleNotifications, setVisibleNotifications] = useState<UploadNotification[]>([])

  useEffect(() => {
    setVisibleNotifications(notifications)

    // Auto-hide notifications after 5 seconds
    notifications.forEach(notification => {
      if (notification.autoHide !== false) {
        setTimeout(() => {
          onDismiss(notification.id)
        }, 5000)
      }
    })
  }, [notifications, onDismiss])

  if (visibleNotifications.length === 0) return null

  const getIcon = (type: string) => {
    switch (type) {
      case 'success':
        return <IconCheck className="h-5 w-5 text-green-600" />
      case 'error':
        return <IconX className="h-5 w-5 text-red-600" />
      default:
        return <IconCloudUpload className="h-5 w-5 text-blue-600" />
    }
  }

  const getCardStyle = (type: string) => {
    switch (type) {
      case 'success':
        return 'border-green-200 bg-green-50'
      case 'error':
        return 'border-red-200 bg-red-50'
      default:
        return 'border-blue-200 bg-blue-50'
    }
  }

  return (
    <div className="fixed bottom-4 right-4 z-50 space-y-2 max-w-sm">
      {visibleNotifications.map((notification) => (
        <Card key={notification.id} className={`${getCardStyle(notification.type)} shadow-lg animate-in slide-in-from-right duration-300`}>
          <CardContent className="p-4">
            <div className="flex items-start gap-3">
              <div className="flex-shrink-0 mt-0.5">
                {getIcon(notification.type)}
              </div>
              
              <div className="flex-grow min-w-0">
                <div className="flex items-center justify-between mb-1">
                  <h4 className="text-sm font-semibold">{notification.title}</h4>
                  {notification.fileCount && (
                    <Badge variant="secondary" className="text-xs">
                      {notification.fileCount} file{notification.fileCount > 1 ? 's' : ''}
                    </Badge>
                  )}
                </div>
                <p className="text-sm text-muted-foreground">{notification.message}</p>
                <p className="text-xs text-muted-foreground mt-1">
                  {notification.timestamp.toLocaleTimeString()}
                </p>
              </div>
              
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onDismiss(notification.id)}
                className="h-6 w-6 p-0 hover:bg-transparent"
              >
                <IconX className="h-3 w-3" />
              </Button>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

// Hook to manage notifications
export function useUploadNotifications() {
  const [notifications, setNotifications] = useState<UploadNotification[]>([])

  const addNotification = (notification: Omit<UploadNotification, 'id' | 'timestamp'>) => {
    const newNotification: UploadNotification = {
      ...notification,
      id: Math.random().toString(36).substr(2, 9),
      timestamp: new Date()
    }
    setNotifications(prev => [...prev, newNotification])
  }

  const dismissNotification = (id: string) => {
    setNotifications(prev => prev.filter(n => n.id !== id))
  }

  const clearAll = () => {
    setNotifications([])
  }

  return {
    notifications,
    addNotification,
    dismissNotification,
    clearAll
  }
}