"use client"

import React, { createContext, useContext, useState, ReactNode } from 'react'

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
  // Notifications management
  const [notifications, setNotifications] = useState<Notification[]>([])

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

  const contextValue: AppStateContextType = {
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
// useConnection removed. Show ConnectionError only on real API failures.

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
