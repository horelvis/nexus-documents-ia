'use client'

import { createContext, useContext, useEffect, useState, useTransition, Suspense } from 'react'
import { usePathname, useSearchParams } from 'next/navigation'

interface PageLoaderContextType {
  isLoading: boolean
  startLoading: () => void
  stopLoading: () => void
}

const PageLoaderContext = createContext<PageLoaderContextType>({
  isLoading: false,
  startLoading: () => {},
  stopLoading: () => {},
})

export function usePageLoader() {
  return useContext(PageLoaderContext)
}

function PageLoaderProviderInner({ children }: { children: React.ReactNode }) {
  const [isLoading, setIsLoading] = useState(false)
  const [showLoader, setShowLoader] = useState(false)
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const [isPending] = useTransition()

  // Hide loader when route changes complete
  useEffect(() => {
    setIsLoading(false)
    setShowLoader(false)
  }, [pathname, searchParams])

  // Show loader for transitions
  useEffect(() => {
    if (isPending) {
      setIsLoading(true)
      setShowLoader(true)
    } else {
      const timer = setTimeout(() => {
        setIsLoading(false)
        setShowLoader(false)
      }, 200)
      return () => clearTimeout(timer)
    }
  }, [isPending])

  const startLoading = () => {
    setIsLoading(true)
    // Show loader after a small delay to prevent flash
    const timer = setTimeout(() => {
      setShowLoader(true)
    }, 100)
    return () => clearTimeout(timer)
  }

  const stopLoading = () => {
    setIsLoading(false)
    setShowLoader(false)
  }

  return (
    <PageLoaderContext.Provider value={{ isLoading, startLoading, stopLoading }}>
      {children}
      {showLoader && (
        <div className="fixed inset-0 bg-background/80 backdrop-blur-sm z-50 flex items-center justify-center">
          <div className="animate-spin h-8 w-8 border-4 border-primary border-t-transparent rounded-full" />
        </div>
      )}
    </PageLoaderContext.Provider>
  )
}

export function PageLoaderProvider({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={
      <PageLoaderContext.Provider value={{ isLoading: false, startLoading: () => {}, stopLoading: () => {} }}>
        {children}
      </PageLoaderContext.Provider>
    }>
      <PageLoaderProviderInner>{children}</PageLoaderProviderInner>
    </Suspense>
  )
}
