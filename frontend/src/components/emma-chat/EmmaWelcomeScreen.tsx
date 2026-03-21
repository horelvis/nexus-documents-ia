'use client'

import { useState, useEffect, useRef } from 'react'
import { useAuth } from '@/contexts/auth-context'
import { useApiClient } from '@/lib/api-client'
import { API_CONFIG } from '@/lib/config'

interface EmmaWelcomeScreenProps {
  onSendQuery: (query: string) => void
  examplePrompts: string[]
}

export function EmmaWelcomeScreen({ onSendQuery, examplePrompts }: EmmaWelcomeScreenProps) {
  const { isAuthenticated, user } = useAuth()
  const apiClient = useApiClient()

  const [welcomeMessage, setWelcomeMessage] = useState('')
  const [welcomeLoaded, setWelcomeLoaded] = useState(false)
  const welcomeFetchedRef = useRef(false)

  useEffect(() => {
    if (welcomeFetchedRef.current) return
    async function loadWelcome() {
      welcomeFetchedRef.current = true
      try {
        const res = await apiClient.get<{ message: string; personalized: boolean }>(
          API_CONFIG.ENDPOINTS.EMMA_WELCOME,
        )
        if (res.data?.message) {
          setWelcomeMessage(res.data.message)
        }
      } catch {
        // Silently ignore — will show default welcome
      } finally {
        setWelcomeLoaded(true)
      }
    }
    if (isAuthenticated && user?.id) {
      loadWelcome()
    }
  }, [isAuthenticated, user?.id])

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-8 min-h-[60vh]">
      <div className="text-center space-y-4 max-w-md">
        <img
          src="/emma-welcome.png"
          alt="Emma"
          className="w-24 h-24 mx-auto rounded-full object-cover object-top shadow-lg"
        />

        {welcomeLoaded && welcomeMessage ? (
          <p className="text-lg text-foreground">{welcomeMessage}</p>
        ) : welcomeLoaded ? (
          <>
            <h2 className="text-2xl font-semibold">Hola, soy Emma</h2>
            <p className="text-muted-foreground">
              Tu asistente de inteligencia empresarial. Puedo ayudarte a buscar,
              analizar y entender tus documentos.
            </p>
          </>
        ) : (
          <p className="text-muted-foreground animate-pulse">
            Preparando tu sesión...
          </p>
        )}

        {/* Example prompts */}
        <div className="space-y-2 pt-4">
          <p className="text-sm text-muted-foreground font-medium">
            Prueba preguntarme:
          </p>
          <div className="flex flex-wrap gap-2 justify-center">
            {examplePrompts.map((prompt, idx) => (
              <button
                key={idx}
                onClick={() => onSendQuery(prompt)}
                className="px-3 py-1.5 text-sm bg-muted hover:bg-muted/80 rounded-lg transition-colors"
              >
                {prompt}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
