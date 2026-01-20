"use client"

import { useState, useEffect } from 'react'
import { assistantService, WelcomeResponse } from '@/lib/services/assistant.service'
import { useUser } from '@clerk/nextjs'

export function useWelcomeMessage() {
  const [welcomeMessage, setWelcomeMessage] = useState<WelcomeResponse | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { user } = useUser()

  const fetchWelcomeMessage = async () => {
    if (!user) return

    setIsLoading(true)
    setError(null)

    try {
      const response = await assistantService.getWelcomeMessage()
      setWelcomeMessage(response)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error fetching welcome message')
      // Fallback message
      setWelcomeMessage({
        message: "¡Estoy aquí para ayudarte!",
        personalized: false
      })
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchWelcomeMessage()
  }, [user?.id])

  return {
    welcomeMessage,
    isLoading,
    error,
    refetch: fetchWelcomeMessage
  }
}