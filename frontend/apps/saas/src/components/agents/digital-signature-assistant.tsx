'use client'

import { useState, useRef } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Separator } from '@/components/ui/separator'
import { 
  FileSignature, 
  Send, 
  Upload, 
  User, 
  Bot, 
  Loader2, 
  MessageCircle,
  FileText,
  Users,
  CheckCircle,
  Clock,
  ArrowLeft
} from 'lucide-react'
import { Agent } from '@/lib/services/agents.service'
import { useAgentChat } from '@/hooks/use-agent-chat'
import { ChatMessage } from '@/lib/services/agents.service'

interface DigitalSignatureAssistantProps {
  agent: Agent
  onBack: () => void
}

export function DigitalSignatureAssistant({ agent, onBack }: DigitalSignatureAssistantProps) {
  const [activeTab, setActiveTab] = useState('chat')
  const [messageInput, setMessageInput] = useState('')
  const [uploadedFile, setUploadedFile] = useState<File | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  
  const { 
    messages, 
    isLoading, 
    isStreaming, 
    conversationId, 
    sendMessage, 
    clearChat 
  } = useAgentChat({
    agentId: agent.id,
    onMessage: (message) => console.log('New message:', message),
    onError: (error) => console.error('Chat error:', error)
  })

  const handleSendMessage = async () => {
    if (!messageInput.trim()) return
    
    const context: Record<string, any> = {}
    
    // Include file information if uploaded
    if (uploadedFile) {
      context.document = {
        name: uploadedFile.name,
        size: uploadedFile.size,
        type: uploadedFile.type
      }
    }
    
    await sendMessage(messageInput, context)
    setMessageInput('')
  }

  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (file) {
      setUploadedFile(file)
      // Auto-send a message about the uploaded file
      setTimeout(() => {
        setMessageInput(`He subido el documento "${file.name}". ¿Puedes ayudarme a crear una solicitud de firma digital para este documento?`)
      }, 500)
    }
  }

  const handleKeyPress = (event: React.KeyboardEvent) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      handleSendMessage()
    }
  }

  const formatMessage = (message: ChatMessage) => {
    // Simple formatting for demo
    return message.content.split('\n').map((line, index) => (
      <span key={index}>
        {line}
        {index < message.content.split('\n').length - 1 && <br />}
      </span>
    ))
  }

  const quickActions = [
    {
      title: "Crear solicitud de firma",
      description: "Ayúdame a crear una nueva solicitud de firma digital",
      action: () => setMessageInput("Quiero crear una nueva solicitud de firma digital. ¿Qué necesitas saber?")
    },
    {
      title: "Analizar documento",
      description: "Analiza un documento para firma",
      action: () => setMessageInput("Por favor analiza el documento que he subido y dime qué tipo de firmas necesita.")
    },
    {
      title: "Consultar estado",
      description: "Ver el estado de mis solicitudes de firma",
      action: () => setMessageInput("¿Puedes mostrarme el estado de mis solicitudes de firma pendientes?")
    },
    {
      title: "Buscar documentos",
      description: "Buscar documentos en mi biblioteca",
      action: () => setMessageInput("Busca documentos relacionados con contratos en mi biblioteca.")
    }
  ]

  return (
    <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6">
      <div className="px-4 lg:px-6">
        {/* Header */}
        <div className="flex items-center gap-4 mb-6">
          <Button variant="outline" onClick={onBack}>
            <ArrowLeft className="h-4 w-4 mr-2" />
            Volver
          </Button>
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-100 rounded-lg">
              <FileSignature className="h-6 w-6 text-blue-600" />
            </div>
            <div>
              <h1 className="text-3xl font-bold">{agent.name}</h1>
              <p className="text-muted-foreground">{agent.description}</p>
            </div>
          </div>
          <div className="ml-auto">
            <Badge variant="secondary" className="bg-green-100 text-green-800">
              <div className="h-2 w-2 bg-green-500 rounded-full mr-2" />
              Conectado
            </Badge>
          </div>
        </div>

        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="chat">Chat Inteligente</TabsTrigger>
            <TabsTrigger value="workflow">Flujo de Trabajo</TabsTrigger>
            <TabsTrigger value="history">Historial</TabsTrigger>
          </TabsList>

          <TabsContent value="chat" className="space-y-6">
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Chat Interface */}
              <div className="lg:col-span-2 space-y-4">
                <Card className="h-[600px] flex flex-col">
                  <CardHeader className="pb-3">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-lg">Chat con el Asistente</CardTitle>
                      <div className="flex items-center gap-2">
                        {conversationId && (
                          <Badge variant="outline" className="text-xs">
                            ID: {conversationId.slice(0, 8)}...
                          </Badge>
                        )}
                        <Button variant="outline" size="sm" onClick={clearChat}>
                          Nuevo Chat
                        </Button>
                      </div>
                    </div>
                  </CardHeader>
                  
                  <CardContent className="flex-1 flex flex-col p-0">
                    {/* Messages Area */}
                    <ScrollArea className="flex-1 px-4">
                      <div className="space-y-4 py-4">
                        {messages.length === 0 && (
                          <div className="text-center py-8">
                            <Bot className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
                            <h3 className="text-lg font-semibold mb-2">¡Hola! Soy tu asistente de firma digital</h3>
                            <p className="text-muted-foreground mb-4">
                              Puedo ayudarte a crear solicitudes de firma, analizar documentos y gestionar tus workflows de firma digital.
                            </p>
                            <p className="text-sm text-muted-foreground">
                              Comienza escribiendo un mensaje o usa una de las acciones rápidas →
                            </p>
                          </div>
                        )}
                        
                        {messages.map((message, index) => (
                          <div key={index} className={`flex gap-3 ${message.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}>
                            <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
                              message.role === 'user' 
                                ? 'bg-blue-500 text-white' 
                                : 'bg-gray-100 text-gray-600'
                            }`}>
                              {message.role === 'user' ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
                            </div>
                            <div className={`flex-1 max-w-[80%] ${message.role === 'user' ? 'text-right' : 'text-left'}`}>
                              <div className={`inline-block p-3 rounded-lg ${
                                message.role === 'user' 
                                  ? 'bg-blue-500 text-white' 
                                  : 'bg-gray-100 text-gray-900'
                              }`}>
                                <div className="text-sm">
                                  {formatMessage(message)}
                                </div>
                              </div>
                              <div className="text-xs text-muted-foreground mt-1">
                                {new Date(message.timestamp).toLocaleTimeString()}
                              </div>
                            </div>
                          </div>
                        ))}
                        
                        {isLoading && (
                          <div className="flex gap-3">
                            <div className="w-8 h-8 rounded-full bg-gray-100 flex items-center justify-center">
                              <Bot className="h-4 w-4 text-gray-600" />
                            </div>
                            <div className="flex-1">
                              <div className="inline-block p-3 rounded-lg bg-gray-100">
                                <div className="flex items-center gap-2 text-sm text-gray-600">
                                  <Loader2 className="h-4 w-4 animate-spin" />
                                  {isStreaming ? 'Procesando...' : 'Escribiendo...'}
                                </div>
                              </div>
                            </div>
                          </div>
                        )}
                      </div>
                    </ScrollArea>
                    
                    <Separator />
                    
                    {/* Input Area */}
                    <div className="p-4 space-y-3">
                      {uploadedFile && (
                        <div className="flex items-center gap-2 p-2 bg-blue-50 rounded-lg">
                          <FileText className="h-4 w-4 text-blue-600" />
                          <span className="text-sm text-blue-800">{uploadedFile.name}</span>
                          <Button 
                            variant="ghost" 
                            size="sm" 
                            onClick={() => setUploadedFile(null)}
                            className="ml-auto h-6 w-6 p-0"
                          >
                            ×
                          </Button>
                        </div>
                      )}
                      
                      <div className="flex gap-2">
                        <Textarea
                          value={messageInput}
                          onChange={(e) => setMessageInput(e.target.value)}
                          onKeyPress={handleKeyPress}
                          placeholder="Escribe tu mensaje aquí... (Shift+Enter para nueva línea)"
                          className="flex-1 min-h-[40px] max-h-[120px] resize-none"
                        />
                        <div className="flex flex-col gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => fileInputRef.current?.click()}
                            className="h-10 w-10 p-0"
                          >
                            <Upload className="h-4 w-4" />
                          </Button>
                          <Button
                            onClick={handleSendMessage}
                            disabled={!messageInput.trim() || isLoading}
                            className="h-10 w-10 p-0"
                          >
                            {isLoading ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                              <Send className="h-4 w-4" />
                            )}
                          </Button>
                        </div>
                      </div>
                      
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept=".pdf,.doc,.docx,.txt"
                        onChange={handleFileUpload}
                        className="hidden"
                      />
                    </div>
                  </CardContent>
                </Card>
              </div>

              {/* Quick Actions Sidebar */}
              <div className="space-y-4">
                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">Acciones Rápidas</CardTitle>
                    <CardDescription>
                      Comandos comunes para empezar rápidamente
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {quickActions.map((action, index) => (
                      <Button
                        key={index}
                        variant="outline"
                        className="w-full justify-start h-auto p-3"
                        onClick={action.action}
                      >
                        <div className="text-left">
                          <div className="font-medium text-sm">{action.title}</div>
                          <div className="text-xs text-muted-foreground mt-1">
                            {action.description}
                          </div>
                        </div>
                      </Button>
                    ))}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">Estado del Agente</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <div className="flex items-center justify-between text-sm">
                      <span>Tipo de Agente:</span>
                      <Badge variant="secondary">{agent.type}</Badge>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span>Herramientas:</span>
                      <span className="text-muted-foreground">{agent.tools.length} disponibles</span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span>Estado:</span>
                      <div className="flex items-center gap-1">
                        <CheckCircle className="h-3 w-3 text-green-500" />
                        <span className="text-green-600">Activo</span>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>
            </div>
          </TabsContent>

          <TabsContent value="workflow" className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Flujo de Trabajo de Firma Digital</CardTitle>
                <CardDescription>
                  Proceso paso a paso para crear solicitudes de firma
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-6">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="text-center p-4 border rounded-lg">
                      <Upload className="h-8 w-8 mx-auto mb-2 text-blue-500" />
                      <h3 className="font-semibold">1. Subir Documento</h3>
                      <p className="text-sm text-muted-foreground">
                        Sube el documento que necesita firma
                      </p>
                    </div>
                    <div className="text-center p-4 border rounded-lg">
                      <Users className="h-8 w-8 mx-auto mb-2 text-green-500" />
                      <h3 className="font-semibold">2. Configurar Firmantes</h3>
                      <p className="text-sm text-muted-foreground">
                        Define quién debe firmar el documento
                      </p>
                    </div>
                    <div className="text-center p-4 border rounded-lg">
                      <Send className="h-8 w-8 mx-auto mb-2 text-purple-500" />
                      <h3 className="font-semibold">3. Enviar Solicitud</h3>
                      <p className="text-sm text-muted-foreground">
                        Envía las invitaciones de firma
                      </p>
                    </div>
                  </div>
                  
                  <div className="text-center">
                    <p className="text-muted-foreground mb-4">
                      El asistente de IA te guiará a través de cada paso y configurará automáticamente 
                      los parámetros óptimos basándose en el análisis del documento.
                    </p>
                    <Button onClick={() => setActiveTab('chat')}>
                      <MessageCircle className="h-4 w-4 mr-2" />
                      Comenzar con el Asistente
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="history" className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Historial de Conversaciones</CardTitle>
                <CardDescription>
                  Conversaciones anteriores con el asistente
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="text-center py-12">
                  <Clock className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
                  <h3 className="text-lg font-semibold mb-2">No hay historial disponible</h3>
                  <p className="text-muted-foreground">
                    Las conversaciones aparecerán aquí una vez que comiences a chatear con el asistente.
                  </p>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  )
}