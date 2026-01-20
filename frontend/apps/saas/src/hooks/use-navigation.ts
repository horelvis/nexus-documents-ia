'use client'

import { useRouter, usePathname } from 'next/navigation'
import { usePageLoader } from '@/components/providers/page-loader'
import { useCallback } from 'react'

export function useNavigation() {
  const router = useRouter()
  const pathname = usePathname()
  const { startLoading, stopLoading } = usePageLoader()

  const navigate = useCallback((href: string) => {
    // Don't show loader for same page navigation
    if (href === pathname) {
      return
    }

    // Start loading
    startLoading()

    // Navigate
    router.push(href)
  }, [router, pathname, startLoading])

  const navigateWithLoader = useCallback(async (href: string) => {
    // Don't show loader for same page navigation
    if (href === pathname) {
      return
    }

    try {
      startLoading()
      await router.push(href)
    } finally {
      // Router will handle stopping the loader when navigation completes
    }
  }, [router, pathname, startLoading])

  return {
    navigate,
    navigateWithLoader,
    router,
    pathname
  }
}