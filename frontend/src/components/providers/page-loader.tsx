'use client'

import { createContext, useContext, useEffect, useState, useTransition } from 'react'
import { usePathname, useSearchParams } from 'next/navigation'
import { Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

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

export function PageLoaderProvider({ children }: { children: React.ReactNode }) {
  const [isLoading, setIsLoading] = useState(false)
  const [showLoader, setShowLoader] = useState(false)
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const [isPending, startTransition] = useTransition()

  // Show loader when route changes
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
      {showLoader && <PageLoader />}
    </PageLoaderContext.Provider>
  )
}

function PageLoader() {
  return (
    <div 
      className={cn(
        "fixed inset-0 z-[100] bg-background/80 backdrop-blur-sm",
        "animate-in fade-in duration-200"
      )}
    >
      <div className="fixed left-[50%] top-[50%] -translate-x-[50%] -translate-y-[50%]">
        <div className="flex flex-col items-center space-y-4">
          <div className="relative">
            <Loader2 className="h-12 w-12 animate-spin text-primary" />
            <div className="absolute inset-0 h-12 w-12 animate-ping rounded-full bg-primary/20" />
          </div>
          <div className="space-y-2 text-center">
            <p className="text-sm font-medium">Cargando página...</p>
            <p className="text-xs text-muted-foreground">Por favor espera un momento</p>
          </div>
        </div>
      </div>
    </div>
  )
}