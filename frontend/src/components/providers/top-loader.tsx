'use client'

import { useEffect, useState } from 'react'
import { usePathname, useSearchParams } from 'next/navigation'

export function TopLoader() {
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const [isLoading, setIsLoading] = useState(false)
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    // Reset on route change
    setIsLoading(false)
    setProgress(0)
  }, [pathname, searchParams])

  useEffect(() => {
    // Listen for navigation events
    const handleStart = () => {
      setIsLoading(true)
      setProgress(10)
      
      // Simulate progress
      let currentProgress = 10
      const interval = setInterval(() => {
        currentProgress += Math.random() * 30
        if (currentProgress > 90) {
          currentProgress = 90
        }
        setProgress(currentProgress)
      }, 200)

      return () => clearInterval(interval)
    }

    const handleComplete = () => {
      setProgress(100)
      setTimeout(() => {
        setIsLoading(false)
        setProgress(0)
      }, 200)
    }

    // Intercept navigation
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

    return () => {
      window.history.pushState = originalPush
      window.history.replaceState = originalReplace
    }
  }, [])

  if (!isLoading) return null

  return (
    <div
      className="fixed top-0 left-0 right-0 z-[100] h-1 bg-primary/20"
    >
      <div
        className="h-full bg-primary transition-all duration-300 ease-out"
        style={{
          width: `${progress}%`,
          boxShadow: '0 0 10px currentColor, 0 0 5px currentColor'
        }}
      />
    </div>
  )
}