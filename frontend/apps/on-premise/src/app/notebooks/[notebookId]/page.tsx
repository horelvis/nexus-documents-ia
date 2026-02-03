'use client'

/**
 * NexusLM Notebook Detail Page
 *
 * Individual notebook view with:
 * - Source management (add/remove documents)
 * - Podcast audio generation
 * - Q&A chat with sources
 * - Audio player with transcript sync
 */

import { useState, useEffect, useCallback } from 'react'
import { useRouter, useParams } from 'next/navigation'
import {
  IconArrowLeft,
  IconPlus,
  IconFileText,
  IconHeadphones,
  IconMessage,
  IconPlayerPlay,
  IconPlayerPause,
  IconDownload,
  IconTrash,
  IconSettings,
  IconLoader2,
  IconVolume,
  IconSend,
  IconRefresh,
  IconAlertCircle,
  IconCircleCheck,
  IconClock,
} from '@tabler/icons-react'
import {
  Button,
  Input,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Badge,
  Progress,
  ScrollArea,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Label,
} from '@nexus/shared/ui'
import {
  SidebarProvider,
  SidebarInset,
} from '@nexus/shared/ui'
import { useAuth } from '@/contexts/auth-context'
import { AppSidebar } from '@/components/layout/app-sidebar'
import { PageHeader } from '@/components/layout/page-header'
import {
  notebookService,
  Notebook,
  NotebookSource,
  NotebookAudio,
  NotebookChat,
  AudioConfig,
  AudioStatus,
} from '@/lib/services/notebook.service'

export default function NotebookDetailPage() {
  const { isLoaded, isAuthenticated } = useAuth()
  const router = useRouter()
  const params = useParams()
  const notebookId = params.notebookId as string

  // Main data state
  const [notebook, setNotebook] = useState<Notebook | null>(null)
  const [sources, setSources] = useState<NotebookSource[]>([])
  const [audios, setAudios] = useState<NotebookAudio[]>([])
  const [chats, setChats] = useState<NotebookChat[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Active tab
  const [activeTab, setActiveTab] = useState('sources')

  // Audio generation state
  const [isGenerating, setIsGenerating] = useState(false)
  const [generatingAudioId, setGeneratingAudioId] = useState<string | null>(null)
  const [audioConfig, setAudioConfig] = useState<AudioConfig>({
    tone: 'conversational',
    length: 'standard',
    language: 'es-ES',
  })
  const [audioDialogOpen, setAudioDialogOpen] = useState(false)

  // Audio player state
  const [playingAudioId, setPlayingAudioId] = useState<string | null>(null)
  const [audioElement, setAudioElement] = useState<HTMLAudioElement | null>(null)

  // Chat state
  const [activeChatId, setActiveChatId] = useState<string | null>(null)
  const [chatMessages, setChatMessages] = useState<any[]>([])
  const [chatInput, setChatInput] = useState('')
  const [isSendingMessage, setIsSendingMessage] = useState(false)

  // Load notebook data
  const loadNotebook = useCallback(async () => {
    if (!notebookId) return

    setIsLoading(true)
    setError(null)

    try {
      const response = await notebookService.get(notebookId)

      if (response.error) {
        setError(response.error)
      } else if (response.data) {
        setNotebook(response.data)
        setSources(response.data.sources || [])
        setAudios(response.data.recent_audios || [])
        setChats(response.data.recent_chats || [])
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al cargar notebook')
    } finally {
      setIsLoading(false)
    }
  }, [notebookId])

  useEffect(() => {
    if (isAuthenticated && notebookId) {
      loadNotebook()
    }
  }, [isAuthenticated, notebookId, loadNotebook])

  // Redirect if not authenticated
  useEffect(() => {
    if (isLoaded && !isAuthenticated) {
      router.push('/auth/sign-in')
    }
  }, [isLoaded, isAuthenticated, router])

  // Poll for audio generation status
  useEffect(() => {
    if (!generatingAudioId) return

    const pollInterval = setInterval(async () => {
      try {
        const response = await notebookService.getAudioStatus(notebookId, generatingAudioId)

        if (response.data) {
          const { status, progress_percent } = response.data

          // Update audio in list
          setAudios((prev) =>
            prev.map((a) =>
              a.id === generatingAudioId
                ? { ...a, status, progress_percent }
                : a
            )
          )

          // Stop polling if completed or failed
          if (status === 'completed' || status === 'failed') {
            setIsGenerating(false)
            setGeneratingAudioId(null)
            loadNotebook() // Reload to get full audio data
          }
        }
      } catch (err) {
        console.error('Error polling audio status:', err)
      }
    }, 2000)

    return () => clearInterval(pollInterval)
  }, [generatingAudioId, notebookId, loadNotebook])

  // Generate audio
  const handleGenerateAudio = async () => {
    setAudioDialogOpen(false)
    setIsGenerating(true)

    try {
      const response = await notebookService.generateAudio(notebookId, audioConfig)

      if (response.error) {
        setError(response.error)
        setIsGenerating(false)
      } else if (response.data) {
        setGeneratingAudioId(response.data.id)
        setAudios((prev) => [response.data!, ...prev])
        setActiveTab('audio')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al generar audio')
      setIsGenerating(false)
    }
  }

  // Play/pause audio
  const handlePlayAudio = (audio: NotebookAudio) => {
    if (!audio.audio_url) return

    if (playingAudioId === audio.id && audioElement) {
      // Pause
      audioElement.pause()
      setPlayingAudioId(null)
    } else {
      // Play
      if (audioElement) {
        audioElement.pause()
      }
      const newAudio = new Audio(audio.audio_url)
      newAudio.play()
      newAudio.onended = () => setPlayingAudioId(null)
      setAudioElement(newAudio)
      setPlayingAudioId(audio.id)
    }
  }

  // Create or select chat
  const handleStartChat = async () => {
    try {
      const response = await notebookService.createChat(notebookId)
      if (response.error) {
        setError(response.error)
      } else if (response.data) {
        setActiveChatId(response.data.id)
        setChatMessages([])
        setChats((prev) => [response.data!, ...prev])
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al crear chat')
    }
  }

  // Send chat message
  const handleSendMessage = async () => {
    if (!chatInput.trim() || !activeChatId) return

    const message = chatInput.trim()
    setChatInput('')
    setIsSendingMessage(true)

    // Add user message optimistically
    const userMsg = { role: 'user', content: message, timestamp: new Date().toISOString() }
    setChatMessages((prev) => [...prev, userMsg])

    try {
      const response = await notebookService.sendMessage(notebookId, activeChatId, message)

      if (response.error) {
        setError(response.error)
      } else if (response.data) {
        setChatMessages((prev) => [...prev, response.data!.message])
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al enviar mensaje')
    } finally {
      setIsSendingMessage(false)
    }
  }

  // Get status badge for audio
  const getAudioStatusBadge = (status: AudioStatus) => {
    const statusConfig: Record<AudioStatus, { label: string; variant: any; icon: any }> = {
      pending: { label: 'Pendiente', variant: 'secondary', icon: IconClock },
      generating_script: { label: 'Generando guion', variant: 'default', icon: IconLoader2 },
      generating_audio: { label: 'Generando audio', variant: 'default', icon: IconLoader2 },
      stitching: { label: 'Finalizando', variant: 'default', icon: IconLoader2 },
      completed: { label: 'Completado', variant: 'success', icon: IconCircleCheck },
      failed: { label: 'Error', variant: 'destructive', icon: IconAlertCircle },
    }
    const config = statusConfig[status] || statusConfig.pending
    const Icon = config.icon

    return (
      <Badge variant={config.variant} className="flex items-center gap-1">
        <Icon className={`h-3 w-3 ${status.includes('generating') ? 'animate-spin' : ''}`} />
        {config.label}
      </Badge>
    )
  }

  // Loading state
  if (!isLoaded || isLoading) {
    return (
      <div className="flex items-center justify-center h-screen bg-background">
        <IconLoader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  if (!isAuthenticated || !notebook) {
    return null
  }

  return (
    <SidebarProvider>
      <AppSidebar variant="inset" />

      <SidebarInset>
        {/* Header */}
        <PageHeader>
          <Button variant="ghost" size="icon" onClick={() => router.push('/notebooks')}>
            <IconArrowLeft className="h-5 w-5" />
          </Button>
          <div className="flex items-center gap-2 flex-1">
            <span className="text-xl">{notebook.emoji}</span>
            <span className="font-semibold truncate">{notebook.title}</span>
          </div>
          <Button variant="outline" size="sm" onClick={loadNotebook}>
            <IconRefresh className="h-4 w-4" />
          </Button>
        </PageHeader>

        {/* Main Content */}
        <main className="flex-1 p-6 overflow-auto">
          {/* Error */}
          {error && (
            <div className="rounded-lg border border-destructive bg-destructive/10 p-4 text-destructive mb-4">
              {error}
            </div>
          )}

          {/* Stats Summary */}
          <div className="flex gap-4 mb-6 flex-wrap">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <IconFileText className="h-4 w-4" />
              {sources.length} fuentes
            </div>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <IconHeadphones className="h-4 w-4" />
              {audios.length} podcasts
            </div>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <IconMessage className="h-4 w-4" />
              {chats.length} chats
            </div>
          </div>

          {/* Tabs */}
          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <div className="flex items-center justify-between mb-4">
              <TabsList>
                <TabsTrigger value="sources" className="flex items-center gap-1">
                  <IconFileText className="h-4 w-4" />
                  Fuentes
                </TabsTrigger>
                <TabsTrigger value="audio" className="flex items-center gap-1">
                  <IconHeadphones className="h-4 w-4" />
                  Podcasts
                </TabsTrigger>
                <TabsTrigger value="chat" className="flex items-center gap-1">
                  <IconMessage className="h-4 w-4" />
                  Chat Q&A
                </TabsTrigger>
              </TabsList>

              {activeTab === 'audio' && (
                <Dialog open={audioDialogOpen} onOpenChange={setAudioDialogOpen}>
                  <Button onClick={() => setAudioDialogOpen(true)} disabled={sources.length === 0 || isGenerating}>
                    {isGenerating ? (
                      <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <IconHeadphones className="mr-2 h-4 w-4" />
                    )}
                    Generar Podcast
                  </Button>
                  <DialogContent>
                    <DialogHeader>
                      <DialogTitle>Generar Podcast</DialogTitle>
                      <DialogDescription>
                        Configura las opciones para generar un podcast a partir de tus fuentes.
                      </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4 py-4">
                      <div className="space-y-2">
                        <Label>Tono</Label>
                        <Select
                          value={audioConfig.tone}
                          onValueChange={(v) => setAudioConfig({ ...audioConfig, tone: v as any })}
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="conversational">Conversacional</SelectItem>
                            <SelectItem value="formal">Formal</SelectItem>
                            <SelectItem value="educational">Educativo</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-2">
                        <Label>Duración</Label>
                        <Select
                          value={audioConfig.length}
                          onValueChange={(v) => setAudioConfig({ ...audioConfig, length: v as any })}
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="short">Corto (3-5 min)</SelectItem>
                            <SelectItem value="standard">Estándar (5-10 min)</SelectItem>
                            <SelectItem value="long">Largo (10-15 min)</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-2">
                        <Label>Idioma</Label>
                        <Select
                          value={audioConfig.language}
                          onValueChange={(v) => setAudioConfig({ ...audioConfig, language: v })}
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="es-ES">Español</SelectItem>
                            <SelectItem value="en-US">Inglés</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                    <DialogFooter>
                      <Button variant="outline" onClick={() => setAudioDialogOpen(false)}>
                        Cancelar
                      </Button>
                      <Button onClick={handleGenerateAudio}>
                        <IconHeadphones className="mr-2 h-4 w-4" />
                        Generar
                      </Button>
                    </DialogFooter>
                  </DialogContent>
                </Dialog>
              )}

              {activeTab === 'chat' && (
                <Button onClick={handleStartChat}>
                  <IconMessage className="mr-2 h-4 w-4" />
                  Nueva Conversación
                </Button>
              )}
            </div>

            {/* Sources Tab */}
            <TabsContent value="sources" className="space-y-4">
              {sources.length === 0 ? (
                <Card className="text-center py-12">
                  <CardContent>
                    <IconFileText className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                    <h3 className="font-semibold mb-2">Sin fuentes</h3>
                    <p className="text-muted-foreground mb-4">
                      Añade documentos para empezar a analizar y generar contenido
                    </p>
                    <Button>
                      <IconPlus className="mr-2 h-4 w-4" />
                      Añadir Documento
                    </Button>
                  </CardContent>
                </Card>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {sources.map((source) => (
                    <Card key={source.id}>
                      <CardHeader className="pb-2">
                        <div className="flex items-start justify-between">
                          <div className="flex items-center gap-2">
                            <IconFileText className="h-5 w-5 text-muted-foreground" />
                            <CardTitle className="text-base">{source.title}</CardTitle>
                          </div>
                          <Badge variant={source.is_processed ? 'default' : 'secondary'}>
                            {source.is_processed ? 'Listo' : 'Procesando'}
                          </Badge>
                        </div>
                        <CardDescription>
                          {source.source_type.toUpperCase()} • {source.word_count.toLocaleString()} palabras
                        </CardDescription>
                      </CardHeader>
                      {source.summary && (
                        <CardContent>
                          <p className="text-sm text-muted-foreground line-clamp-3">{source.summary}</p>
                        </CardContent>
                      )}
                    </Card>
                  ))}
                </div>
              )}
            </TabsContent>

            {/* Audio Tab */}
            <TabsContent value="audio" className="space-y-4">
              {audios.length === 0 ? (
                <Card className="text-center py-12">
                  <CardContent>
                    <IconHeadphones className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                    <h3 className="font-semibold mb-2">Sin podcasts</h3>
                    <p className="text-muted-foreground mb-4">
                      Genera un podcast a partir de tus fuentes
                    </p>
                    <Button onClick={() => setAudioDialogOpen(true)} disabled={sources.length === 0}>
                      <IconHeadphones className="mr-2 h-4 w-4" />
                      Generar Podcast
                    </Button>
                  </CardContent>
                </Card>
              ) : (
                <div className="space-y-4">
                  {audios.map((audio) => (
                    <Card key={audio.id}>
                      <CardHeader className="pb-2">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            <Button
                              variant="outline"
                              size="icon"
                              disabled={audio.status !== 'completed'}
                              onClick={() => handlePlayAudio(audio)}
                            >
                              {playingAudioId === audio.id ? (
                                <IconPlayerPause className="h-4 w-4" />
                              ) : (
                                <IconPlayerPlay className="h-4 w-4" />
                              )}
                            </Button>
                            <div>
                              <CardTitle className="text-base">
                                Podcast {new Date(audio.created_at).toLocaleDateString()}
                              </CardTitle>
                              <CardDescription>
                                {audio.config?.tone} • {audio.config?.length} • {audio.config?.language}
                              </CardDescription>
                            </div>
                          </div>
                          {getAudioStatusBadge(audio.status)}
                        </div>
                      </CardHeader>
                      <CardContent>
                        {audio.status !== 'completed' && audio.status !== 'failed' && (
                          <Progress value={audio.progress_percent} className="mb-2" />
                        )}
                        {audio.duration_formatted && (
                          <p className="text-sm text-muted-foreground">
                            Duración: {audio.duration_formatted}
                          </p>
                        )}
                        {audio.error_message && (
                          <p className="text-sm text-destructive mt-2">{audio.error_message}</p>
                        )}
                        {audio.status === 'completed' && audio.audio_url && (
                          <div className="flex gap-2 mt-2">
                            <Button variant="outline" size="sm" asChild>
                              <a href={audio.audio_url} download>
                                <IconDownload className="mr-2 h-4 w-4" />
                                Descargar
                              </a>
                            </Button>
                          </div>
                        )}
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )}
            </TabsContent>

            {/* Chat Tab */}
            <TabsContent value="chat" className="h-[500px] flex flex-col">
              {!activeChatId ? (
                <Card className="text-center py-12 flex-1">
                  <CardContent>
                    <IconMessage className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                    <h3 className="font-semibold mb-2">Chat Q&A</h3>
                    <p className="text-muted-foreground mb-4">
                      Pregunta sobre tus documentos y obtén respuestas con citas
                    </p>
                    <Button onClick={handleStartChat}>
                      <IconMessage className="mr-2 h-4 w-4" />
                      Iniciar Conversación
                    </Button>
                  </CardContent>
                </Card>
              ) : (
                <>
                  <ScrollArea className="flex-1 border rounded-lg p-4 mb-4">
                    {chatMessages.length === 0 ? (
                      <p className="text-center text-muted-foreground py-8">
                        Haz una pregunta sobre tus documentos
                      </p>
                    ) : (
                      <div className="space-y-4">
                        {chatMessages.map((msg, i) => (
                          <div
                            key={i}
                            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                          >
                            <div
                              className={`max-w-[80%] rounded-lg p-3 ${
                                msg.role === 'user'
                                  ? 'bg-primary text-primary-foreground'
                                  : 'bg-muted'
                              }`}
                            >
                              <p className="whitespace-pre-wrap">{msg.content}</p>
                            </div>
                          </div>
                        ))}
                        {isSendingMessage && (
                          <div className="flex justify-start">
                            <div className="bg-muted rounded-lg p-3">
                              <IconLoader2 className="h-4 w-4 animate-spin" />
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </ScrollArea>
                  <div className="flex gap-2">
                    <Input
                      placeholder="Pregunta sobre tus documentos..."
                      value={chatInput}
                      onChange={(e) => setChatInput(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSendMessage()}
                      disabled={isSendingMessage}
                    />
                    <Button onClick={handleSendMessage} disabled={!chatInput.trim() || isSendingMessage}>
                      <IconSend className="h-4 w-4" />
                    </Button>
                  </div>
                </>
              )}
            </TabsContent>
          </Tabs>
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}
