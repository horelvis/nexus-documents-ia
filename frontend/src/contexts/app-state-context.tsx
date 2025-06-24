"use client"

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { useConnectionStatus } from '@/hooks/use-connection-status'
import { ConnectionError } from '@/components/errors/connection-error'

// Notification types
interface Notification {
  id: string
  type: 'upload' | 'document' | 'user' | 'system' | 'success' | 'error' | 'info'
  title: string
  message: string
  timestamp: Date
  read: boolean
  action?: {
    label: string
    href: string
  }
  fileCount?: number
  autoHide?: boolean
}

// App State Context type combining notifications and connection
interface AppStateContextType {
  // Connection status
  isOnline: boolean
  isBackendAvailable: boolean
  checkConnection: () => Promise<void>
  
  // Notifications
  notifications: Notification[]
  addNotification: (notification: Omit<Notification, 'id' | 'timestamp' | 'read'>) => void
  markAsRead: (id: string) => void
  markAllAsRead: () => void
  removeNotification: (id: string) => void
  clearAllNotifications: () => void
  unreadCount: number
}

const AppStateContext = createContext<AppStateContextType | undefined>(undefined)

export function AppStateProvider({ children }: { children: ReactNode }) {
  // Connection management
  const { isOnline, isBackendAvailable, isChecking, lastError, checkConnection } = useConnectionStatus()
  const [showError, setShowError] = useState(false)
  const [hasChecked, setHasChecked] = useState(false)

  // Notifications management
  const [notifications, setNotifications] = useState<Notification[]>([])

  // Connection error handling
  useEffect(() => {
    if (!hasChecked && !isChecking) {
      setHasChecked(true)
    }
    
    if (hasChecked && isOnline && !isBackendAvailable && !isChecking) {
      // Add a small delay to prevent flash of error on initial load
      const timer = setTimeout(() => {
        setShowError(true)
      }, 1000)
      return () => clearTimeout(timer)
    } else {
      setShowError(false)
    }
  }, [isOnline, isBackendAvailable, isChecking, hasChecked])

  const handleRetry = async () => {
    setShowError(false)
    await checkConnection()
    if (isBackendAvailable) {
      window.location.reload()
    }
  }

  // Show connection error when backend is unavailable
  if (showError) {
    return <ConnectionError error={lastError} onRetry={handleRetry} />
  }

  // Notification functions
  const addNotification = (notification: Omit<Notification, 'id' | 'timestamp' | 'read'>) => {
    const newNotification: Notification = {
      ...notification,
      id: Math.random().toString(36).substr(2, 9),
      timestamp: new Date(),
      read: false
    }
    setNotifications(prev => [newNotification, ...prev])

    // Auto-hide success notifications after 5 seconds
    if (notification.type === 'success' && notification.autoHide !== false) {
      setTimeout(() => {
        removeNotification(newNotification.id)
      }, 5000)
    }
  }

  const markAsRead = (id: string) => {
    setNotifications(prev => 
      prev.map(n => n.id === id ? { ...n, read: true } : n)
    )
  }

  const markAllAsRead = () => {
    setNotifications(prev => 
      prev.map(n => ({ ...n, read: true }))
    )
  }

  const removeNotification = (id: string) => {
    setNotifications(prev => prev.filter(n => n.id !== id))
  }

  const clearAllNotifications = () => {
    setNotifications([])
  }

  const unreadCount = notifications.filter(n => !n.read).length

  // Auto-add connection restored notification
  useEffect(() => {
    let wasOffline = false
    
    if (!isBackendAvailable) {
      wasOffline = true
    } else if (wasOffline && isBackendAvailable) {
      addNotification({
        type: 'success',
        title: 'Connection Restored',
        message: 'Backend connection has been restored',
        autoHide: true
      })
      wasOffline = false
    }
  }, [isBackendAvailable])

  const contextValue: AppStateContextType = {
    // Connection
    isOnline,
    isBackendAvailable,
    checkConnection,
    
    // Notifications
    notifications,
    addNotification,
    markAsRead,
    markAllAsRead,
    removeNotification,
    clearAllNotifications,
    unreadCount
  }

  return (
    <AppStateContext.Provider value={contextValue}>
      {children}
    </AppStateContext.Provider>
  )
}

// Main hook
export function useAppState() {
  const context = useContext(AppStateContext)
  if (context === undefined) {
    throw new Error('useAppState must be used within an AppStateProvider')
  }
  return context
}

// Convenience hooks
export function useConnection() {
  const { isOnline, isBackendAvailable, checkConnection } = useAppState()
  return { isOnline, isBackendAvailable, checkConnection }
}

export function useNotifications() {
  const { 
    notifications, 
    addNotification, 
    markAsRead, 
    markAllAsRead, 
    removeNotification, 
    clearAllNotifications,
    unreadCount 
  } = useAppState()
  
  return {
    notifications,
    addNotification,
    markAsRead,
    markAllAsRead,
    removeNotification,
    clearAll: clearAllNotifications,
    unreadCount
  }
}