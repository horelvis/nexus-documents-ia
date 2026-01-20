"use client"

import { useState } from "react"
import { useNotifications } from "@/contexts/app-state-context"
import { 
  IconBell, 
  IconBellRinging,
  IconCheck,
  IconX,
  IconCloudUpload,
  IconFileText,
  IconUsers,
  IconSettings,
  IconDots
} from "@tabler/icons-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { 
  DropdownMenu, 
  DropdownMenuContent, 
  DropdownMenuItem, 
  DropdownMenuTrigger,
  DropdownMenuSeparator,
  DropdownMenuLabel
} from "@/components/ui/dropdown-menu"
import { Card, CardContent } from "@/components/ui/card"

export function UserNotifications() {
  const [isOpen, setIsOpen] = useState(false)
  const { 
    notifications, 
    unreadCount, 
    markAsRead, 
    markAllAsRead, 
    removeNotification 
  } = useNotifications()

  const getIcon = (type: string) => {
    switch (type) {
      case 'upload':
        return <IconCloudUpload className="h-4 w-4 text-blue-500" />
      case 'document':
        return <IconFileText className="h-4 w-4 text-green-500" />
      case 'user':
        return <IconUsers className="h-4 w-4 text-purple-500" />
      case 'system':
        return <IconSettings className="h-4 w-4 text-orange-500" />
      default:
        return <IconBell className="h-4 w-4 text-gray-500" />
    }
  }

  const formatTime = (timestamp: Date) => {
    const now = new Date()
    const diff = now.getTime() - timestamp.getTime()
    const minutes = Math.floor(diff / (1000 * 60))
    const hours = Math.floor(diff / (1000 * 60 * 60))
    const days = Math.floor(diff / (1000 * 60 * 60 * 24))

    if (minutes < 1) return 'Just now'
    if (minutes < 60) return `${minutes}m ago`
    if (hours < 24) return `${hours}h ago`
    return `${days}d ago`
  }

  return (
    <DropdownMenu open={isOpen} onOpenChange={setIsOpen}>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm" className="relative">
          {unreadCount > 0 ? (
            <IconBellRinging className="h-4 w-4" />
          ) : (
            <IconBell className="h-4 w-4" />
          )}
          {unreadCount > 0 && (
            <Badge 
              variant="destructive" 
              className="absolute -top-1 -right-1 h-5 w-5 p-0 text-xs flex items-center justify-center"
            >
              {unreadCount > 9 ? '9+' : unreadCount}
            </Badge>
          )}
        </Button>
      </DropdownMenuTrigger>
      
      <DropdownMenuContent 
        className="w-80 max-h-96 overflow-y-auto" 
        align="end"
        side="bottom"
      >
        <div className="flex items-center justify-between px-3 py-2">
          <DropdownMenuLabel className="text-sm font-semibold">
            Notifications
          </DropdownMenuLabel>
          {unreadCount > 0 && (
            <Button 
              variant="ghost" 
              size="sm" 
              className="h-auto p-1 text-xs"
              onClick={markAllAsRead}
            >
              Mark all read
            </Button>
          )}
        </div>
        
        <DropdownMenuSeparator />
        
        {notifications.length === 0 ? (
          <div className="px-3 py-6 text-center text-sm text-muted-foreground">
            <IconBell className="h-8 w-8 mx-auto mb-2 opacity-50" />
            No notifications
          </div>
        ) : (
          <div className="max-h-64 overflow-y-auto">
            {notifications.map((notification) => (
              <DropdownMenuItem 
                key={notification.id} 
                className="p-0 focus:bg-muted"
                onSelect={(e) => e.preventDefault()}
              >
                <Card className="w-full border-0 shadow-none">
                  <CardContent className="p-3">
                    <div className="flex items-start gap-3">
                      <div className="flex-shrink-0 mt-0.5">
                        {getIcon(notification.type)}
                      </div>
                      
                      <div className="flex-grow min-w-0">
                        <div className="flex items-start justify-between">
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2">
                              <p className="text-sm font-medium truncate">
                                {notification.title}
                              </p>
                              {!notification.read && (
                                <IconDots className="h-3 w-3 text-blue-500 flex-shrink-0" />
                              )}
                            </div>
                            <p className="text-xs text-muted-foreground mt-1">
                              {notification.message}
                            </p>
                            <p className="text-xs text-muted-foreground mt-1">
                              {formatTime(notification.timestamp)}
                            </p>
                            
                            {notification.action && (
                              <Button
                                variant="link"
                                size="sm"
                                className="h-auto p-0 text-xs mt-1"
                                asChild
                              >
                                <a href={notification.action.href}>
                                  {notification.action.label}
                                </a>
                              </Button>
                            )}
                          </div>
                          
                          <div className="flex gap-1 ml-2">
                            {!notification.read && (
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-6 w-6 p-0"
                                onClick={() => markAsRead(notification.id)}
                              >
                                <IconCheck className="h-3 w-3" />
                              </Button>
                            )}
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-6 w-6 p-0"
                              onClick={() => removeNotification(notification.id)}
                            >
                              <IconX className="h-3 w-3" />
                            </Button>
                          </div>
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </DropdownMenuItem>
            ))}
          </div>
        )}
        
        {notifications.length > 0 && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem className="text-center text-sm text-muted-foreground cursor-pointer">
              <div className="w-full py-1">
                View all notifications
              </div>
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}