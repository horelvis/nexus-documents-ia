"use client"

import { useEffect, useState } from "react"
import { usePathname } from "next/navigation"
import { Progress } from "@/components/ui/progress"

export function NavigationProgress() {
  const pathname = usePathname()
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    // Reset and start progress
    setProgress(10)
    
    // Simulate loading with a simple timeout progression
    const timer1 = setTimeout(() => setProgress(40), 100)
    const timer2 = setTimeout(() => setProgress(70), 200)
    const timer3 = setTimeout(() => setProgress(100), 300)
    const timer4 = setTimeout(() => setProgress(0), 500)

    return () => {
      clearTimeout(timer1)
      clearTimeout(timer2)
      clearTimeout(timer3)
      clearTimeout(timer4)
    }
  }, [pathname])

  if (progress === 0) return null

  return (
    <div className="fixed top-0 left-0 right-0 z-50">
      <Progress 
        value={progress} 
        className="h-1 bg-transparent border-none rounded-none transition-all duration-200"
      />
    </div>
  )
}