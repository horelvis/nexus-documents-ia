'use client'

import { useEffect, useState, useRef } from 'react'
import { usePathname, useSearchParams } from 'next/navigation'

export function TopLoader() {
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const [isLoading, setIsLoading] = useState(false)
  const [progress, setProgress] = useState(0)
  const intervalRef = useRef<NodeJS.Timeout | null>(null)
  const isMountedRef = useRef(false)

  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
    }
  }, [])

  useEffect(() => {
    // Reset on route change
    if (isMountedRef.current) {
      setIsLoading(false)
      setProgress(0)
    }
  }, [pathname, searchParams])

  useEffect(() => {
    // Only set up interceptors after component is mounted
    if (!isMountedRef.current) return

    const handleStart = () => {
      if (!isMountedRef.current) return
      
      // Use setTimeout to defer state updates
      setTimeout(() => {
        if (!isMountedRef.current) return
        
        setIsLoading(true)
        setProgress(10)
        
        // Clear any existing interval
        if (intervalRef.current) {
          clearInterval(intervalRef.current)
        }
        
        // Simulate progress
        let currentProgress = 10
        intervalRef.current = setInterval(() => {
          if (!isMountedRef.current) {
            if (intervalRef.current) clearInterval(intervalRef.current)
            return
          }
          
          currentProgress += Math.random() * 30
          if (currentProgress > 90) {
            currentProgress = 90
          }
          setProgress(currentProgress)
        }, 200)
      }, 0)
    }

    const handleComplete = () => {
      if (!isMountedRef.current) return
      
      setTimeout(() => {
        if (!isMountedRef.current) return
        
        setProgress(100)
        
        if (intervalRef.current) {
          clearInterval(intervalRef.current)
          intervalRef.current = null
        }
        
        setTimeout(() => {
          if (!isMountedRef.current) return
          setIsLoading(false)
          setProgress(0)
        }, 200)
      }, 0)
    }

    // Intercept navigation after a small delay to ensure proper mounting
    const setupInterceptors = setTimeout(() => {
      if (!isMountedRef.current) return
      
      const originalPush = window.history.pushState
      const originalReplace = window.history.replaceState

      window.history.pushState = function (...args) {
        handleStart()
        originalPush.apply(window.history, args)
        setTimeout(handleComplete, 100)
      }

      window.history.replaceState = function (...args) {
        handleStart()
        originalReplace.apply(window.history, args)
        setTimeout(handleComplete, 100)
      }

      // Store cleanup function
      return () => {
        window.history.pushState = originalPush
        window.history.replaceState = originalReplace
      }
    }, 100)

    return () => {
      clearTimeout(setupInterceptors)
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
      }
    }
  }, [])

  if (!isLoading) return null

  return (
    <div
      className="fixed top-0 left-0 right-0 z-[100] h-1 bg-purple-600/20 dark:bg-purple-400/20"
    >
      <div
        className="h-full bg-purple-600 dark:bg-purple-400 transition-all duration-300 ease-out"
        style={{
          width: `${progress}%`,
          boxShadow: '0 0 10px currentColor, 0 0 5px currentColor'
        }}
      />
    </div>
  )
}