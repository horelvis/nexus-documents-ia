"use client"

import { useEffect, useState } from "react"
import { IconPlugConnectedX, IconRefresh, IconWifi, IconWifiOff, IconX } from "@tabler/icons-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"

interface ConnectionErrorProps {
  onRetry?: () => void
  error?: Error | null
  onClose?: () => void
}

export function ConnectionError({ onRetry, error, onClose }: ConnectionErrorProps) {
  const [isOnline, setIsOnline] = useState(true)
  const [retrying, setRetrying] = useState(false)

  useEffect(() => {
    const handleOnline = () => setIsOnline(true)
    const handleOffline = () => setIsOnline(false)

    // Check initial state
    setIsOnline(navigator.onLine)

    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)

    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [])

  const handleRetry = async () => {
    setRetrying(true)
    try {
      if (onRetry) {
        await onRetry()
      } else {
        window.location.reload()
      }
    } finally {
      setTimeout(() => setRetrying(false), 1000)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <Card className="max-w-md w-full relative">
        {/* Close Button */}
        <Button
          variant="ghost"
          size="icon"
          onClick={onClose || (() => window.history.back())}
          className="absolute right-2 top-2 h-8 w-8"
        >
          <IconX className="h-4 w-4" />
        </Button>
        
        <CardHeader className="text-center">
          <div className="mx-auto mb-4">
            <IconPlugConnectedX className="h-24 w-24 text-destructive opacity-50" />
          </div>
          <CardTitle className="text-2xl">Unable to Connect to Server</CardTitle>
          <CardDescription>
            We're having trouble reaching the backend server
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Network Status */}
          <Alert variant={isOnline ? "default" : "destructive"}>
            <div className="flex items-center gap-2">
              {isOnline ? (
                <IconWifi className="h-4 w-4" />
              ) : (
                <IconWifiOff className="h-4 w-4" />
              )}
              <AlertTitle className="mb-0">
                {isOnline ? "Internet Connected" : "No Internet Connection"}
              </AlertTitle>
            </div>
            <AlertDescription className="mt-2">
              {isOnline 
                ? "Your internet is working, but the server is not responding"
                : "Please check your internet connection"
              }
            </AlertDescription>
          </Alert>

          {/* Error Details */}
          {error && (
            <Alert>
              <AlertTitle>Error Details</AlertTitle>
              <AlertDescription className="mt-2 font-mono text-xs">
                {error.message || "Connection refused"}
              </AlertDescription>
            </Alert>
          )}

          {/* Possible Solutions */}
          <div className="space-y-2">
            <p className="text-sm font-medium">Possible solutions:</p>
            <ul className="text-sm text-muted-foreground space-y-1 ml-4 list-disc">
              <li>Check if the backend server is running</li>
              <li>Verify the API URL configuration</li>
              <li>Check your firewall settings</li>
              <li>Try again in a few moments</li>
            </ul>
          </div>

          {/* Actions */}
          <div className="flex gap-2 pt-4">
            <Button 
              onClick={handleRetry} 
              disabled={retrying}
              className="flex-1"
            >
              {retrying ? (
                <IconRefresh className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <IconRefresh className="h-4 w-4 mr-2" />
              )}
              Try Again
            </Button>
            <Button 
              variant="outline" 
              onClick={() => window.location.href = '/'}
              className="flex-1"
            >
              Go Home
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}