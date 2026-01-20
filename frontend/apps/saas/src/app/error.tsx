'use client'

import { useEffect } from 'react'
import { ConnectionError } from '@/components/errors/connection-error'

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    // Log the error to an error reporting service
    console.error('Application error:', error)
  }, [error])

  // Check if it's a connection error
  const isConnectionError = 
    error.name === 'ConnectionError' ||
    error.message.includes('Failed to fetch') ||
    error.message.includes('NetworkError') ||
    error.message.includes('ECONNREFUSED') ||
    error.message.includes('Unable to connect')

  if (isConnectionError) {
    return <ConnectionError error={error} onRetry={reset} />
  }

  // Default error UI for other errors
  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="text-center max-w-md">
        <h2 className="text-2xl font-bold mb-4">Something went wrong!</h2>
        <p className="text-muted-foreground mb-6">{error.message}</p>
        <button
          onClick={reset}
          className="px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90"
        >
          Try again
        </button>
      </div>
    </div>
  )
}