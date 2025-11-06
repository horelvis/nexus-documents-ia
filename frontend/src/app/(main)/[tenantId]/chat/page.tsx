"use client"

import React, { useEffect, useState, useRef } from "react"
import { useSearchParams } from "next/navigation"
import { 
  MessageSquare, 
  Settings, 
  Zap, 
  Brain, 
  RefreshCw
} from "lucide-react"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"

// Usar nuestros componentes de Elysia existentes
import { ElysiaChat, type ElysiaChatRef } from "@/components/elysia-chat"
import { useBackendUser } from "@/contexts/user-context"

interface ChatPageProps {
  params: Promise<{
    tenantId: string
  }>
}

// Prompts de ejemplo para comenzar
const examplePrompts = [
  "¿Qué documentos hay disponibles en mi biblioteca?",
  "Busca información sobre contratos firmados",
  "Resume los documentos más recientes",
  "¿Hay algún documento sobre facturación?",
  "Muéstrame los documentos compartidos conmigo",
  "Encuentra documentos con firmas digitales",
  "¿Qué documentos necesitan revisión?",
  "Busca documentos por fecha de creación"
]

function getRandomPrompts(count: number = 4): string[] {
  const shuffled = [...examplePrompts].sort(() => 0.5 - Math.random())
  return shuffled.slice(0, count)
}

export default function ChatPage({ params }: ChatPageProps) {
  // Unwrap params Promise using React.use()
  const { tenantId } = React.use(params)
  
  const { backendUser } = useBackendUser()
  const searchParams = useSearchParams()
  const [mode, setMode] = useState<"chat" | "settings">("chat")
  const [randomPrompts, setRandomPrompts] = useState<string[]>([])
  const [hasStartedChat, setHasStartedChat] = useState(false)
  const [initialQuery, setInitialQuery] = useState<string | null>(null)
  const elysiaChatRef = useRef<ElysiaChatRef>(null)

  // Check for initial query parameter
  useEffect(() => {
    const queryParam = searchParams.get('q')
    if (queryParam) {
      setInitialQuery(queryParam)
      setHasStartedChat(true)
    }
  }, [searchParams])

  // Generar prompts aleatorios al cargar
  useEffect(() => {
    setRandomPrompts(getRandomPrompts(4))
  }, [])

  const refreshPrompts = () => {
    setRandomPrompts(getRandomPrompts(4))
  }

  const handlePromptClick = (prompt: string) => {
    setHasStartedChat(true)
    // Enviar el prompt al componente de chat usando la referencia
    if (elysiaChatRef.current) {
      elysiaChatRef.current.sendQuery(prompt)
    }
  }

  return (
    <div className="flex flex-col w-full h-screen overflow-hidden">
      {/* Header */}
      <div className="flex w-full justify-between items-center sticky top-0 z-20 p-4 bg-background border-b">
        <div className="flex items-center gap-4">
          <Brain className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-xl font-semibold">Emma Assistant</h1>
            <p className="text-sm text-muted-foreground">
              AI-powered document intelligence
            </p>
          </div>
        </div>
        
        <div className="flex items-center gap-2">
          {/* Mode Selector */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm">
                {mode === "chat" ? (
                  <>
                    <MessageSquare className="h-4 w-4 mr-2" />
                    Chat
                  </>
                ) : (
                  <>
                    <Settings className="h-4 w-4 mr-2" />
                    Settings
                  </>
                )}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent>
              <DropdownMenuItem onClick={() => setMode("chat")}>
                <MessageSquare className="h-4 w-4 mr-2" />
                Chat
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => setMode("settings")}>
                <Settings className="h-4 w-4 mr-2" />
                Settings
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          
          <Badge variant="secondary">
            <Zap className="h-3 w-3 mr-1" />
            Online
          </Badge>
        </div>
      </div>

      {mode === "chat" ? (
        <div className="flex flex-col w-full flex-1 min-h-0">
          {!hasStartedChat ? (
            // Landing screen con prompts sugeridos
            <div className="flex flex-col items-center justify-center flex-1 p-6 overflow-y-auto">
              <div className="text-center mb-8">
                <h2 className="text-3xl font-bold mb-2">Ask Emma</h2>
                <p className="text-muted-foreground">
                  Start a conversation about your documents
                </p>
              </div>

              <div className="flex items-center gap-4 mb-6">
                <h3 className="text-lg font-semibold">Try asking:</h3>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={refreshPrompts}
                  className="gap-2"
                >
                  <RefreshCw className="h-4 w-4" />
                  Refresh
                </Button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-4xl w-full">
                {randomPrompts.map((prompt, index) => (
                  <button
                    key={index}
                    onClick={() => handlePromptClick(prompt)}
                    className="p-4 text-left border rounded-lg hover:bg-accent hover:text-accent-foreground transition-colors duration-200 group"
                  >
                    <div className="flex items-start gap-3">
                      <MessageSquare className="h-5 w-5 text-primary mt-0.5 group-hover:text-accent-foreground transition-colors" />
                      <p className="text-sm leading-relaxed">{prompt}</p>
                    </div>
                  </button>
                ))}
              </div>

              <div className="mt-8 text-center">
                <p className="text-sm text-muted-foreground">
                  Or type your own question below to start chatting
                </p>
              </div>
            </div>
          ) : null}

          {/* Chat Component */}
          <div className="flex-1 min-h-0 pb-4">
            <ElysiaChat 
              ref={elysiaChatRef}
              tenantId={tenantId}
              className="h-full"
              initialMessage="¡Hola! Soy Emma, tu asistente inteligente. ¿En qué puedo ayudarte hoy?"
              initialQuery={initialQuery || undefined}
              onFirstQuery={() => setHasStartedChat(true)}
              isAdmin={backendUser ? (
                backendUser.is_superuser || 
                backendUser.roles?.some((role: any) => role.name === 'admin') ||
                !backendUser.is_team_member
              ) : false}
            />
          </div>
        </div>
      ) : mode === "settings" ? (
        <div className="flex flex-col w-full max-w-4xl mx-auto p-6 flex-1 overflow-y-auto">
          <h2 className="text-2xl font-bold mb-6">Configuración de Emma</h2>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Model Settings */}
            <div className="p-6 border rounded-lg">
              <h3 className="font-semibold mb-4 flex items-center gap-2">
                <Brain className="h-5 w-5" />
                Configuración del Modelo
              </h3>
              <div className="space-y-4">
                <div>
                  <label className="text-sm font-medium">Temperatura</label>
                  <p className="text-sm text-muted-foreground">Controla la creatividad de las respuestas</p>
                  <Badge variant="secondary">0.7 (por defecto)</Badge>
                </div>
                <div>
                  <label className="text-sm font-medium">Máximo tokens</label>
                  <p className="text-sm text-muted-foreground">Límite de longitud de respuesta</p>
                  <Badge variant="secondary">2048</Badge>
                </div>
              </div>
            </div>

            {/* Search Settings */}
            <div className="p-6 border rounded-lg">
              <h3 className="font-semibold mb-4 flex items-center gap-2">
                <MessageSquare className="h-5 w-5" />
                Configuración de Búsqueda
              </h3>
              <div className="space-y-4">
                <div>
                  <label className="text-sm font-medium">Límite de documentos</label>
                  <p className="text-sm text-muted-foreground">Número máximo de documentos a analizar</p>
                  <Badge variant="secondary">10</Badge>
                </div>
                <div>
                  <label className="text-sm font-medium">Umbral de similitud</label>
                  <p className="text-sm text-muted-foreground">Mínimo de similitud para incluir documentos</p>
                  <Badge variant="secondary">0.7</Badge>
                </div>
              </div>
            </div>

            {/* User Info */}
            <div className="p-6 border rounded-lg">
              <h3 className="font-semibold mb-4 flex items-center gap-2">
                <Settings className="h-5 w-5" />
                Información del Usuario
              </h3>
              <div className="space-y-2">
                <p className="text-sm"><strong>Tenant:</strong> {tenantId}</p>
                <p className="text-sm"><strong>Usuario:</strong> {backendUser?.email || 'No disponible'}</p>
                <p className="text-sm"><strong>Rol:</strong> {backendUser?.is_team_member ? 'Miembro del equipo' : 'Administrador'}</p>
              </div>
            </div>

            {/* Capabilities */}
            <div className="p-6 border rounded-lg">
              <h3 className="font-semibold mb-4 flex items-center gap-2">
                <Zap className="h-5 w-5" />
                Capacidades
              </h3>
              <div className="space-y-2">
                <Badge variant="outline">RAG Agentic</Badge>
                <Badge variant="outline">Búsqueda Semántica</Badge>
                <Badge variant="outline">Análisis de Documentos</Badge>
                <Badge variant="outline">Respuestas Contextuales</Badge>
              </div>
            </div>
          </div>

          <div className="mt-6">
            <Button onClick={() => setMode("chat")} className="gap-2">
              <MessageSquare className="h-4 w-4" />
              Volver al Chat
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  )
}