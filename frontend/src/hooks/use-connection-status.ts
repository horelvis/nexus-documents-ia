import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'
import { API_CONFIG } from '@/lib/config'

interface ConnectionStatus {
  isOnline: boolean
  isBackendAvailable: boolean
  isChecking: boolean
  lastError: Error | null
  checkConnection: () => Promise<void>
}

export function useConnectionStatus(): ConnectionStatus {
  const [isOnline, setIsOnline] = useState(true)
  const [isBackendAvailable, setIsBackendAvailable] = useState(true)
  const [isChecking, setIsChecking] = useState(false)
  const [lastError, setLastError] = useState<Error | null>(null)

  // Check backend availability
  const checkBackendConnection = useCallback(async () => {
    setIsChecking(true)
    try {
      // Simple health check to backend
      // Try both /health and /docs endpoints as fallback
      try {
        const response = await axios.get(`${API_CONFIG.BASE_URL}/health`, {
          timeout: 5000, // 5 second timeout
          validateStatus: () => true // Accept any status
        })
        
        setIsBackendAvailable(response.status < 500)
        setLastError(null)
      } catch (healthError) {
        // If health endpoint fails, try the docs endpoint as fallback
        const docsResponse = await axios.get(`${API_CONFIG.BASE_URL}/docs`, {
          timeout: 5000,
          validateStatus: () => true
        })
        
        setIsBackendAvailable(docsResponse.status < 500)
        setLastError(null)
      }
    } catch (error) {
      setIsBackendAvailable(false)
      setLastError(error as Error)
    } finally {
      setIsChecking(false)
    }
  }, [])

  // Monitor online/offline status
  useEffect(() => {
    const handleOnline = () => {
      setIsOnline(true)
      checkBackendConnection()
    }
    
    const handleOffline = () => {
      setIsOnline(false)
      setIsBackendAvailable(false)
    }

    // Initial check
    setIsOnline(navigator.onLine)
    if (navigator.onLine) {
      checkBackendConnection()
    }

    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)

    // Periodic check every 30 seconds
    const interval = setInterval(() => {
      if (navigator.onLine) {
        checkBackendConnection()
      }
    }, 30000)

    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
      clearInterval(interval)
    }
  }, [checkBackendConnection])

  return {
    isOnline,
    isBackendAvailable,
    isChecking,
    lastError,
    checkConnection: checkBackendConnection
  }
}