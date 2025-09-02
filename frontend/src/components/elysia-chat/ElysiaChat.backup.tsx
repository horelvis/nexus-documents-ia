"use client"

import { useState, useCallback, useRef, useEffect, useImperativeHandle, forwardRef } from "react"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import { Brain, MessageSquare, Settings, Trash2, RefreshCw, Zap } from "lucide-react"
import { cn } from "@/lib/utils"
import { useBackendUser } from "@/contexts/user-context"
import { useAuthToken } from "@/hooks/use-auth-token"
import { ElysiaQueryInput } from "./ElysiaQueryInput"
import { ElysiaRenderChat } from "./ElysiaRenderChat"
import { toast } from "sonner"

// Message interface for Elysia
interface ElysiaMessage {
  id: string
  type: "user" | "result" | "text" | "error" | "warning" | "self_healing_error" | "system"
  content: string
  timestamp: Date
  metadata?: {
    confidence_score?: number
    decision_path?: string[]
    tools_used?: string[]
    execution_time_ms?: number
    citations?: Array<{
      id: string
      title: string
      url?: string
      page?: number
      excerpt?: string
    }>
  }
  suggestions?: string[]
  isStreaming?: boolean
}

interface ElysiaSession {
  session_id: string
  messages: ElysiaMessage[]
  created_at: Date
}

interface ElysiaChatProps {
  tenantId?: string
  className?: string
  initialMessage?: string
  onClose?: () => void
}

export interface ElysiaChatRef {
  sendQuery: (query: string) => void
}

export const ElysiaChat = forwardRef<ElysiaChatRef, ElysiaChatProps>(function ElysiaChat({
  tenantId,
  className,
  initialMessage,
  onClose
}, ref) {
  const currentUser = useBackendUser()
  const { getValidToken } = useAuthToken()
  const [session, setSession] = useState<ElysiaSession | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [currentView, setCurrentView] = useState<"chat" | "code" | "result">("chat")
  const [socketStatus, setSocketStatus] = useState<"connected" | "disconnected" | "connecting">("connected")
  
  // Use tenantId from props or current user
  const effectiveTenantId = tenantId || currentUser?.tenant_id

  // Expose methods to parent component through ref
  useImperativeHandle(ref, () => ({
    sendQuery: handleSendQuery
  }), [handleSendQuery])

  // Initialize session on mount
  useEffect(() => {
    if (effectiveTenantId && !session) {
      createNewSession()
    }
  }, [effectiveTenantId])

  // Send initial message if provided
  useEffect(() => {
    if (initialMessage && session && session.messages.length === 0) {
      handleSendQuery(initialMessage)
    }
  }, [initialMessage, session])

  const createNewSession = useCallback(() => {
    const newSession: ElysiaSession = {
      session_id: `elysia_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      messages: [],
      created_at: new Date()
    }
    setSession(newSession)
    setError(null)
  }, [])

  const handleSendQuery = useCallback(async (query: string, route?: string, mimick?: boolean) => {
    if (!session || !effectiveTenantId || !query.trim()) return

    setIsLoading(true)
    setError(null)

    try {
      // Add user message immediately
      const userMessage: ElysiaMessage = {
        id: `user_${Date.now()}`,
        type: "user",
        content: query.trim(),
        timestamp: new Date()
      }

      setSession(prev => prev ? {
        ...prev,
        messages: [...prev.messages, userMessage]
      } : null)

      // Get auth token
      const token = await getValidToken()

      // Call our Elysia API endpoint
      const apiUrl = `${process.env.NEXT_PUBLIC_API_BASE_URL || process.env.NEXT_PUBLIC_API_URL}/api/v1/weaviate/elysia/query`
      
      const response = await fetch(apiUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token || ''}`,
        },
        body: JSON.stringify({
          query: query.trim(),
          tenant_id: effectiveTenantId,
          session_id: session.session_id,
          enable_learning: true,
          context: {
            route: route || undefined,
            mimick: mimick || false,
            user_id: currentUser?.id
          }
        })
      })

      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`API Error: ${response.status} ${errorText}`)
      }

      const data = await response.json()
      
      // Process the response from our Elysia API
      const assistantMessage: ElysiaMessage = {
        id: `assistant_${Date.now()}`,
        type: determineMessageType(data),
        content: extractAnswer(data.answer) || "Sin respuesta del sistema",
        timestamp: new Date(),
        metadata: {
          confidence_score: data.confidence_score,
          decision_path: data.decision_path || [],
          tools_used: data.tools_used || [],
          execution_time_ms: data.execution_time_ms,
          citations: parseCitations(data.citations)
        },
        suggestions: data.suggestions || generateSuggestions(query)
      }

      setSession(prev => prev ? {
        ...prev,
        messages: [...prev.messages, assistantMessage]
      } : null)

      // Show success toast with execution info
      if (data.execution_time_ms) {
        toast.success(`Consulta procesada en ${data.execution_time_ms}ms`, {
          description: `Herramientas: ${data.tools_used?.join(', ') || 'Ninguna'}`
        })
      }

    } catch (err: any) {
      console.error("Error sending Elysia query:", err)
      setError(err.message || "Error conectando con el servicio de Elysia")
      
      // Add error message to chat
      const errorMessage: ElysiaMessage = {
        id: `error_${Date.now()}`,
        type: "error",
        content: `❌ Error: ${err.message || "No se pudo conectar con el servicio de Elysia"}`,
        timestamp: new Date()
      }

      setSession(prev => prev ? {
        ...prev,
        messages: [...prev.messages, errorMessage]
      } : null)

      toast.error("Error en la consulta", {
        description: err.message || "El servicio de Elysia no está disponible"
      })
    } finally {
      setIsLoading(false)
    }
  }, [session, effectiveTenantId, currentUser, getValidToken])

  const handleFeedback = useCallback((messageId: string, feedback: "positive" | "negative") => {
    // Send feedback to our API
    toast.success(`Feedback ${feedback} registrado`, {
      description: "Gracias por ayudar a mejorar las respuestas"
    })
    console.log("Feedback:", { messageId, feedback })
  }, [])

  const handleSuggestionClick = useCallback((suggestion: string) => {
    handleSendQuery(suggestion)
  }, [handleSendQuery])

  const clearSession = useCallback(() => {
    if (session) {
      setSession({
        ...session,
        messages: []
      })
      setError(null)
      toast.info("Conversación limpiada")
    }
  }, [session])

  if (!effectiveTenantId) {
    return (
      <Card className={cn("p-8 text-center", className)}>
        <Brain className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
        <h3 className="text-lg font-semibold mb-2">Elysia Chat</h3>
        <p className="text-muted-foreground">
          No se pudo determinar el tenant. Inicie sesión para continuar.
        </p>
      </Card>
    )
  }

  return (
    <Card className={cn("flex flex-col h-[600px]", className)}>
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b bg-gradient-to-r from-primary/5 to-primary/10">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-full bg-primary/10">
            <Brain className="h-6 w-6 text-primary" />
          </div>
          <div>
            <h3 className="font-semibold text-lg flex items-center gap-2">
              Elysia AI Assistant
              <Badge variant="outline" className="text-xs">
                <Zap className="h-3 w-3 mr-1" />
                Agentic RAG
              </Badge>
            </h3>
            <p className="text-sm text-muted-foreground">
              {session ? `Sesión: ${session.session_id.slice(-8)}` : "Inicializando..."}
            </p>
          </div>
        </div>
        
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="icon"
            onClick={clearSession}
            title="Limpiar conversación"
            disabled={!session || session.messages.length === 0}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={createNewSession}
            title="Nueva sesión"
          >
            <RefreshCw className="h-4 w-4" />
          </Button>
          {onClose && (
            <Button
              variant="ghost"
              size="icon"
              onClick={onClose}
              title="Cerrar"
            >
              ✕
            </Button>
          )}
        </div>
      </div>

      {/* Chat Messages */}
      <div className="flex-1 overflow-hidden">
        {session && session.messages.length > 0 ? (
          <ElysiaRenderChat
            messages={session.messages}
            isLoading={isLoading}
            error={error}
            socketStatus={socketStatus}
            onFeedback={handleFeedback}
            onSuggestionClick={handleSuggestionClick}
            currentView={currentView}
            onViewChange={setCurrentView}
          />
        ) : (
          <div className="flex items-center justify-center h-full text-center p-8">
            <div>
              <Brain className="h-16 w-16 mx-auto mb-4 text-muted-foreground/50" />
              <h4 className="text-lg font-medium mb-2">¡Bienvenido a Elysia!</h4>
              <p className="text-muted-foreground mb-4 max-w-md">
                Soy tu asistente inteligente con capacidades agentic RAG. 
                Puedo ayudarte a buscar y analizar información en tus documentos.
              </p>
              <div className="flex flex-wrap gap-2 justify-center">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleSendQuery("¿Qué documentos están disponibles?")}
                >
                  Ver documentos
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleSendQuery("¿Cómo funciona Elysia?")}
                >
                  ¿Cómo funciono?
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>

      <Separator />

      {/* Query Input */}
      <div className="p-4">
        <ElysiaQueryInput
          onSendQuery={handleSendQuery}
          isLoading={isLoading}
          disabled={!session}
          placeholder="Pregúntame sobre tus documentos..."
        />
      </div>
    </Card>
  )
})

// Helper functions
function determineMessageType(data: any): ElysiaMessage["type"] {
  if (data.error) return "error"
  if (data.confidence_score && data.confidence_score < 0.5) return "warning"
  return "result"
}

function extractAnswer(answer: any): string {
  if (typeof answer === "string") return answer
  if (Array.isArray(answer) && answer.length > 0) {
    return typeof answer[0] === "string" ? answer[0] : String(answer[0])
  }
  if (answer && typeof answer === "object") {
    return answer.content || answer.text || String(answer)
  }
  return String(answer || "")
}

function parseCitations(citations: any[]): ElysiaMessage["metadata"]["citations"] {
  if (!Array.isArray(citations)) return []
  
  return citations.map((citation, index) => ({
    id: citation.id || `ref_${index}`,
    title: citation.title || citation.name || `Referencia ${index + 1}`,
    url: citation.url,
    page: citation.page,
    excerpt: citation.excerpt || citation.content?.substring(0, 100)
  }))
}

function generateSuggestions(query: string): string[] {
  // Generate contextual suggestions based on the query
  if (query.toLowerCase().includes("documento")) {
    return [
      "¿Qué tipos de documentos tienes?",
      "Buscar por fecha",
      "Mostrar documentos recientes"
    ]
  }
  
  if (query.toLowerCase().includes("contrato")) {
    return [
      "Analizar términos del contrato",
      "Buscar cláusulas específicas", 
      "Verificar fechas de vencimiento"
    ]
  }

  return [
    "¿Qué más puedes hacer?",
    "Buscar información específica",
    "Mostrar estadísticas"
  ]
}