"use client"

import { useRouter } from "next/navigation"
import { useState, useTransition } from "react"

export function useNavigation() {
  const router = useRouter()
  const [isPending, startTransition] = useTransition()
  const [isNavigating, setIsNavigating] = useState(false)

  const navigate = (href: string) => {
    setIsNavigating(true)
    startTransition(() => {
      router.push(href)
      // Reset after a small delay to account for page transition
      setTimeout(() => {
        setIsNavigating(false)
      }, 100)
    })
  }

  return {
    navigate,
    isNavigating: isPending || isNavigating,
    router
  }
}