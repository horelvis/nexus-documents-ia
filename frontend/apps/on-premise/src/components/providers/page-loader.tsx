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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#05070d]/90 backdrop-blur-sm">
          <div className="flex flex-col items-center gap-4">
            <div className="relative">
              <div className="absolute -inset-3 rounded-full bg-cyan-500/20 blur-xl" />
              <img
                src="/logo-single.png"
                alt="NouxCube AI"
                className="relative h-10 w-auto"
              />
            </div>
            <div className="h-1 w-24 overflow-hidden rounded-full bg-white/10">
              <div className="h-full w-1/2 animate-[shimmer_1.5s_ease-in-out_infinite] rounded-full bg-gradient-to-r from-transparent via-cyan-400 to-transparent" />
            </div>
          </div>
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
