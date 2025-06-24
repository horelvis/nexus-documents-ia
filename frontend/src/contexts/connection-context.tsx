"use client"

import React, { createContext, useContext, useEffect, useState } from 'react'
import { useConnectionStatus } from '@/hooks/use-connection-status'
import { ConnectionError } from '@/components/errors/connection-error'

interface ConnectionContextValue {
  isOnline: boolean
  isBackendAvailable: boolean
  checkConnection: () => Promise<void>
}

const ConnectionContext = createContext<ConnectionContextValue | undefined>(undefined)

export function ConnectionProvider({ children }: { children: React.ReactNode }) {
  const { isOnline, isBackendAvailable, isChecking, lastError, checkConnection } = useConnectionStatus()
  const [showError, setShowError] = useState(false)
  const [hasChecked, setHasChecked] = useState(false)

  useEffect(() => {
    // Wait for at least one check to complete before showing errors
    if (!hasChecked && !isChecking) {
      setHasChecked(true)
    }
    
    // Show error if backend is not available and we're online
    // Only show after initial check to prevent flash of error
    if (hasChecked && isOnline && !isBackendAvailable && !isChecking) {
      setShowError(true)
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

  if (showError) {
    return <ConnectionError error={lastError} onRetry={handleRetry} />
  }

  return (
    <ConnectionContext.Provider value={{ isOnline, isBackendAvailable, checkConnection }}>
      {children}
    </ConnectionContext.Provider>
  )
}

export function useConnection() {
  const context = useContext(ConnectionContext)
  if (context === undefined) {
    throw new Error('useConnection must be used within a ConnectionProvider')
  }
  return context
}