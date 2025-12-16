'use client'

import { useEffect, useState, useRef, Suspense } from 'react'
import { usePathname, useSearchParams } from 'next/navigation'
import { TopProgressBar } from '@/components/ui/unified-loader'

function TopLoaderInner() {
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const [isLoading, setIsLoading] = useState(false)
  const [progress, setProgress] = useState(0)
  const intervalRef = useRef<NodeJS.Timeout | null>(null)
  const timeoutRef = useRef<NodeJS.Timeout | null>(null)

  // Complete loading when route changes
  useEffect(() => {
    // Clear any running intervals
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current)
      timeoutRef.current = null
    }

    // Complete the progress bar
    if (isLoading) {
      setProgress(100)
      timeoutRef.current = setTimeout(() => {
        setIsLoading(false)
        setProgress(0)
      }, 200)
    }
  }, [pathname, searchParams])

  // Intercept link clicks to start loading
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement
      const link = target.closest('a')

      if (!link) return

      const href = link.getAttribute('href')
      if (!href) return

      // Skip external links, hash links, downloads, and special protocols
      if (
        href.startsWith('http') ||
        href.startsWith('mailto:') ||
        href.startsWith('tel:') ||
        href.startsWith('#') ||
        href.startsWith('blob:') ||
        link.target === '_blank' ||
        link.hasAttribute('download')
      ) {
        return
      }

      // Skip if same page (exact match or with trailing slash)
      const currentPath = pathname + (searchParams?.toString() ? `?${searchParams.toString()}` : '')
      if (href === pathname || href === currentPath || href === `${pathname}/`) {
        return
      }

      // Skip if modifier keys are pressed (open in new tab)
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) {
        return
      }

      // Start the loading animation
      startLoading()
    }

    // Also handle programmatic navigation via router.push
    // by intercepting the Next.js router events if available
    const handleRouteChangeStart = () => {
      startLoading()
    }

    document.addEventListener('click', handleClick, true)

    // Intercept history methods as fallback for programmatic navigation
    const originalPush = window.history.pushState
    const originalReplace = window.history.replaceState

    window.history.pushState = function (...args) {
      startLoading()
      return originalPush.apply(window.history, args)
    }

    window.history.replaceState = function (...args) {
      // Only start loading for actual navigation, not state updates
      if (args[2] && typeof args[2] === 'string' && args[2] !== window.location.href) {
        startLoading()
      }
      return originalReplace.apply(window.history, args)
    }

    return () => {
      document.removeEventListener('click', handleClick, true)
      window.history.pushState = originalPush
      window.history.replaceState = originalReplace

      if (intervalRef.current) {
        clearInterval(intervalRef.current)
      }
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current)
      }
    }
  }, [pathname, searchParams])

  const startLoading = () => {
    // Clear any existing intervals
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
    }

    setIsLoading(true)
    setProgress(20)

    // Simulate progress
    let currentProgress = 20
    intervalRef.current = setInterval(() => {
      currentProgress += Math.random() * 15
      if (currentProgress > 90) {
        currentProgress = 90
        if (intervalRef.current) {
          clearInterval(intervalRef.current)
          intervalRef.current = null
        }
      }
      setProgress(currentProgress)
    }, 300)
  }

  // Safety timeout - auto-complete after 8 seconds
  useEffect(() => {
    if (!isLoading) return

    const safetyTimeout = setTimeout(() => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
      setProgress(100)
      setTimeout(() => {
        setIsLoading(false)
        setProgress(0)
      }, 200)
    }, 8000)

    return () => clearTimeout(safetyTimeout)
  }, [isLoading])

  return <TopProgressBar isLoading={isLoading} progress={progress} />
}

export function TopLoader() {
  return (
    <Suspense fallback={null}>
      <TopLoaderInner />
    </Suspense>
  )
}
