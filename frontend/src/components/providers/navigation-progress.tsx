'use client'

import { useEffect } from 'react'
import { usePathname, useSearchParams } from 'next/navigation'
import NProgress from 'nprogress'
import 'nprogress/nprogress.css'

// Configure NProgress
NProgress.configure({
  minimum: 0.3,
  easing: 'ease',
  speed: 500,
  showSpinner: false,
})

export function NavigationProgress() {
  const pathname = usePathname()
  const searchParams = useSearchParams()

  useEffect(() => {
    NProgress.done()
  }, [pathname, searchParams])

  useEffect(() => {
    const handleStart = () => NProgress.start()
    const handleComplete = () => NProgress.done()

    // Listen to route changes
    const originalPush = window.history.pushState
    const originalReplace = window.history.replaceState

    window.history.pushState = function (...args) {
      handleStart()
      originalPush.apply(window.history, args)
    }

    window.history.replaceState = function (...args) {
      handleStart()
      originalReplace.apply(window.history, args)
    }

    window.addEventListener('popstate', handleStart)

    return () => {
      window.history.pushState = originalPush
      window.history.replaceState = originalReplace
      window.removeEventListener('popstate', handleStart)
      NProgress.remove()
    }
  }, [])

  return null
}