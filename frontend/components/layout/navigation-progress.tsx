"use client"

import { useEffect, useState } from "react"
import { usePathname } from "next/navigation"
import { Progress } from "@/components/ui/progress"

export function NavigationProgress() {
  const pathname = usePathname()
  const [isLoading, setIsLoading] = useState(false)
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    let timeout: NodeJS.Timeout
    let interval: NodeJS.Timeout

    const startLoading = () => {
      setIsLoading(true)
      setProgress(0)
      
      // Simulate loading progress
      interval = setInterval(() => {
        setProgress(prev => {
          if (prev >= 90) return prev
          return prev + Math.random() * 10
        })
      }, 100)
    }

    const stopLoading = () => {
      setProgress(100)
      timeout = setTimeout(() => {
        setIsLoading(false)
        setProgress(0)
      }, 200)
    }

    // Start loading on pathname change
    startLoading()
    
    // Stop loading after a short delay (simulating page load)
    const stopTimeout = setTimeout(stopLoading, 300)

    return () => {
      clearTimeout(timeout)
      clearTimeout(stopTimeout)
      clearInterval(interval)
    }
  }, [pathname])

  if (!isLoading) return null

  return (
    <div className="fixed top-0 left-0 right-0 z-50">
      <Progress 
        value={progress} 
        className="h-1 bg-transparent border-none rounded-none"
      />
    </div>
  )
}