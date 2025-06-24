"use client"

import React from 'react'
import { ConnectionError } from './connection-error'

interface ErrorBoundaryProps {
  children: React.ReactNode
  fallback?: React.ComponentType<{ error: Error; reset: () => void }>
}

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('Error caught by boundary:', error, errorInfo)
    
    // Check if it's a network/connection error
    const isConnectionError = 
      error.message.includes('Network Error') ||
      error.message.includes('ERR_NETWORK') ||
      error.message.includes('ERR_INTERNET_DISCONNECTED') ||
      error.message.includes('ECONNREFUSED') ||
      error.message.includes('fetch failed')
    
    if (isConnectionError) {
      // Log connection errors differently
      console.error('Connection error detected:', error.message)
    }
  }

  reset = () => {
    this.setState({ hasError: false, error: null })
  }

  render() {
    if (this.state.hasError && this.state.error) {
      const { fallback: Fallback } = this.props
      
      // Check if it's a connection error
      const isConnectionError = 
        this.state.error.message.includes('Network Error') ||
        this.state.error.message.includes('ERR_NETWORK') ||
        this.state.error.message.includes('ECONNREFUSED')
      
      if (isConnectionError) {
        return <ConnectionError error={this.state.error} onRetry={this.reset} />
      }
      
      if (Fallback) {
        return <Fallback error={this.state.error} reset={this.reset} />
      }
      
      // Default error UI
      return (
        <div className="min-h-screen flex items-center justify-center p-4">
          <div className="text-center">
            <h1 className="text-2xl font-bold mb-4">Something went wrong</h1>
            <p className="text-muted-foreground mb-4">{this.state.error.message}</p>
            <button
              onClick={this.reset}
              className="px-4 py-2 bg-primary text-primary-foreground rounded-md"
            >
              Try again
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}