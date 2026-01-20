'use client'

/**
 * NotebookPanel - NexusLM Panel Component
 *
 * Inline panel for notebook management, similar to NotebookLM.
 * Shows sources, allows adding documents, and generates podcasts.
 * Can be collapsed/expanded with a toggle button.
 */

import { useState, useEffect } from 'react'
import {
  IconChevronDown,
  IconChevronRight,
  IconChevronLeft,
  IconPlus,
  IconFileText,
  IconHeadphones,
  IconTrash,
  IconLoader2,
  IconLayoutSidebarRightCollapse,
  IconLayoutSidebarRight,
} from '@tabler/icons-react'
import {
  Button,
  ScrollArea,
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@nexus/shared/ui'
import { cn } from '@/lib/utils'
import { notebookService, Notebook, NotebookSource, NotebookAudio, AudioConfig } from '@/lib/services/notebook.service'
import { SourceSelector } from './source-selector'
import { AudioPlayer } from './audio-player'

interface NotebookPanelProps {
  className?: string
  isOpen: boolean
  onOpenChange: (open: boolean) => void
}

export function NotebookPanel({ className, isOpen, onOpenChange }: NotebookPanelProps) {
  // State
  const [notebooks, setNotebooks] = useState<Notebook[]>([])
  const [activeNotebook, setActiveNotebook] = useState<Notebook | null>(null)
  const [sources, setSources] = useState<NotebookSource[]>([])
  const [audios, setAudios] = useState<NotebookAudio[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // UI State
  const [sourcesExpanded, setSourcesExpanded] = useState(true)
  const [audioExpanded, setAudioExpanded] = useState(true)
  const [isGenerating, setIsGenerating] = useState(false)
  const [showSourceSelector, setShowSourceSelector] = useState(false)

  // Audio config
  const [audioConfig, setAudioConfig] = useState<AudioConfig>({
    tone: 'conversational',
    length: 'standard',
    language: 'es-ES',
  })

  // Load notebooks on mount
  useEffect(() => {
    loadNotebooks()
  }, [])

  // Load notebook details when active notebook changes
  useEffect(() => {
    if (activeNotebook) {
      loadNotebookDetails(activeNotebook.id)
    }
  }, [activeNotebook?.id])

  const loadNotebooks = async () => {
    setIsLoading(true)
    setError(null)

    try {
      const response = await notebookService.list({ per_page: 50 })
      if (response.error) {
        setError(response.error)
      } else {
        setNotebooks(response.data?.notebooks || [])
        // Auto-select first notebook if none selected
        if (!activeNotebook && response.data?.notebooks?.length) {
          setActiveNotebook(response.data.notebooks[0])
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error loading notebooks')
    } finally {
      setIsLoading(false)
    }
  }

  const loadNotebookDetails = async (notebookId: string) => {
    try {
      const [sourcesRes, audiosRes] = await Promise.all([
        notebookService.listSources(notebookId),
        notebookService.listAudios(notebookId),
      ])

      if (!sourcesRes.error && sourcesRes.data) {
        setSources(sourcesRes.data)
      }
      if (!audiosRes.error && audiosRes.data) {
        setAudios(audiosRes.data)
      }
    } catch (err) {
      console.error('Error loading notebook details:', err)
    }
  }

  const handleCreateNotebook = async () => {
    try {
      const response = await notebookService.create({
        title: `Notebook ${new Date().toLocaleDateString('es-ES')}`,
        emoji: '📓',
      })
      if (!response.error && response.data) {
        setNotebooks(prev => [response.data!, ...prev])
        setActiveNotebook(response.data)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error creating notebook')
    }
  }

  const handleAddSource = async (documentId: string) => {
    if (!activeNotebook) return

    try {
      const response = await notebookService.addSource(activeNotebook.id, {
        indexed_document_id: documentId,
      })
      if (!response.error && response.data) {
        setSources(prev => [...prev, response.data!])
        setShowSourceSelector(false)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error adding source')
    }
  }

  const handleRemoveSource = async (sourceId: string) => {
    if (!activeNotebook) return

    try {
      const response = await notebookService.removeSource(activeNotebook.id, sourceId)
      if (!response.error) {
        setSources(prev => prev.filter(s => s.id !== sourceId))
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error removing source')
    }
  }

  const handleGenerateAudio = async () => {
    if (!activeNotebook || sources.length === 0) return

    setIsGenerating(true)
    setError(null)

    try {
      const response = await notebookService.generateAudio(activeNotebook.id, audioConfig)
      if (response.error) {
        setError(response.error)
      } else if (response.data) {
        setAudios(prev => [response.data!, ...prev])
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error generating audio')
    } finally {
      setIsGenerating(false)
    }
  }

  // Collapsed state - show only toggle button
  if (!isOpen) {
    return (
      <div className={cn(
        "flex flex-col items-center py-4 px-2 border-l bg-[var(--sidebar-background)]",
        className
      )}>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => onOpenChange(true)}
          className="h-8 w-8"
        >
          <IconLayoutSidebarRight className="h-4 w-4" />
        </Button>
      </div>
    )
  }

  // Full panel content
  return (
    <div className={cn(
      "flex flex-col h-full border-l bg-[var(--sidebar-background)] w-80",
      className
    )}>
      {/* Header with collapse button */}
      <div className="p-3 border-b flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold">NexusLM</h2>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            onClick={handleCreateNotebook}
          >
            <IconPlus className="h-4 w-4" />
          </Button>
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => onOpenChange(false)}
          className="h-8 w-8"
        >
          <IconLayoutSidebarRightCollapse className="h-4 w-4" />
        </Button>
      </div>

      {/* Notebook Selector */}
      <div className="p-3 border-b shrink-0">
        {notebooks.length > 0 ? (
          <Select
            value={activeNotebook?.id || ''}
            onValueChange={(id) => {
              const notebook = notebooks.find(n => n.id === id)
              if (notebook) setActiveNotebook(notebook)
            }}
          >
            <SelectTrigger className="w-full h-9">
              <SelectValue placeholder="Seleccionar notebook">
                {activeNotebook && (
                  <span className="flex items-center gap-2">
                    <span>{activeNotebook.emoji}</span>
                    <span className="truncate">{activeNotebook.title}</span>
                  </span>
                )}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {notebooks.map((notebook) => (
                <SelectItem key={notebook.id} value={notebook.id}>
                  <span className="flex items-center gap-2">
                    <span>{notebook.emoji}</span>
                    <span>{notebook.title}</span>
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : (
          <Button variant="outline" className="w-full h-9" onClick={handleCreateNotebook}>
            <IconPlus className="h-4 w-4 mr-2" />
            Crear Notebook
          </Button>
        )}
      </div>

      {/* Scrollable content */}
      <ScrollArea className="flex-1">
        <div className="p-3 space-y-3">
          {/* Error display */}
          {error && (
            <div className="p-2 rounded-lg bg-destructive/10 text-destructive text-xs">
              {error}
            </div>
          )}

          {activeNotebook && (
            <>
              {/* Sources Section */}
              <Collapsible open={sourcesExpanded} onOpenChange={setSourcesExpanded}>
                <CollapsibleTrigger asChild>
                  <Button variant="ghost" className="w-full justify-between p-2 h-auto">
                    <span className="flex items-center gap-2">
                      <IconFileText className="h-4 w-4" />
                      <span className="font-medium text-sm">Fuentes</span>
                      <span className="text-xs text-muted-foreground">({sources.length})</span>
                    </span>
                    {sourcesExpanded ? (
                      <IconChevronDown className="h-4 w-4" />
                    ) : (
                      <IconChevronRight className="h-4 w-4" />
                    )}
                  </Button>
                </CollapsibleTrigger>
                <CollapsibleContent className="space-y-2 mt-2">
                  {sources.length === 0 ? (
                    <p className="text-xs text-muted-foreground text-center py-3">
                      No hay fuentes añadidas
                    </p>
                  ) : (
                    sources.map((source) => (
                      <div
                        key={source.id}
                        className="flex items-center gap-2 p-2 rounded-lg bg-muted/50 group"
                      >
                        <IconFileText className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                        <span className="text-xs truncate flex-1">{source.title}</span>
                        <span className={cn(
                          "text-[10px] px-1 py-0.5 rounded",
                          source.status === 'ready' && "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
                          source.status === 'processing' && "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
                          source.status === 'error' && "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
                        )}>
                          {source.status === 'ready' ? '✓' : source.status === 'processing' ? '...' : '!'}
                        </span>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-5 w-5 opacity-0 group-hover:opacity-100 transition-opacity"
                          onClick={() => handleRemoveSource(source.id)}
                        >
                          <IconTrash className="h-3 w-3" />
                        </Button>
                      </div>
                    ))
                  )}

                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full h-8 text-xs"
                    onClick={() => setShowSourceSelector(true)}
                  >
                    <IconPlus className="h-3.5 w-3.5 mr-1.5" />
                    Añadir fuente
                  </Button>
                </CollapsibleContent>
              </Collapsible>

              {/* Audio Generation Section */}
              <Collapsible open={audioExpanded} onOpenChange={setAudioExpanded}>
                <CollapsibleTrigger asChild>
                  <Button variant="ghost" className="w-full justify-between p-2 h-auto">
                    <span className="flex items-center gap-2">
                      <IconHeadphones className="h-4 w-4" />
                      <span className="font-medium text-sm">Podcast</span>
                    </span>
                    {audioExpanded ? (
                      <IconChevronDown className="h-4 w-4" />
                    ) : (
                      <IconChevronRight className="h-4 w-4" />
                    )}
                  </Button>
                </CollapsibleTrigger>
                <CollapsibleContent className="space-y-2 mt-2">
                  {/* Audio config */}
                  <div className="grid grid-cols-2 gap-2">
                    <Select
                      value={audioConfig.tone}
                      onValueChange={(v) => setAudioConfig(prev => ({ ...prev, tone: v as AudioConfig['tone'] }))}
                    >
                      <SelectTrigger className="h-7 text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="conversational">Conversacional</SelectItem>
                        <SelectItem value="formal">Formal</SelectItem>
                        <SelectItem value="educational">Educativo</SelectItem>
                      </SelectContent>
                    </Select>

                    <Select
                      value={audioConfig.length}
                      onValueChange={(v) => setAudioConfig(prev => ({ ...prev, length: v as AudioConfig['length'] }))}
                    >
                      <SelectTrigger className="h-7 text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="short">3-5 min</SelectItem>
                        <SelectItem value="standard">5-10 min</SelectItem>
                        <SelectItem value="long">10-15 min</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <Button
                    className="w-full h-8 text-xs"
                    onClick={handleGenerateAudio}
                    disabled={isGenerating || sources.length === 0}
                  >
                    {isGenerating ? (
                      <>
                        <IconLoader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
                        Generando...
                      </>
                    ) : (
                      <>
                        <IconHeadphones className="h-3.5 w-3.5 mr-1.5" />
                        Generar Podcast
                      </>
                    )}
                  </Button>

                  {sources.length === 0 && (
                    <p className="text-[10px] text-muted-foreground text-center">
                      Añade fuentes para generar un podcast
                    </p>
                  )}

                  {/* Recent audios */}
                  {audios.length > 0 && (
                    <div className="space-y-2 pt-2 border-t">
                      <p className="text-xs text-muted-foreground">Podcasts generados</p>
                      {audios.slice(0, 3).map((audio) => (
                        <AudioPlayer
                          key={audio.id}
                          audio={audio}
                          notebookId={activeNotebook.id}
                        />
                      ))}
                    </div>
                  )}
                </CollapsibleContent>
              </Collapsible>
            </>
          )}
        </div>
      </ScrollArea>

      {/* Source selector sheet */}
      <SourceSelector
        isOpen={showSourceSelector}
        onOpenChange={setShowSourceSelector}
        onSelect={handleAddSource}
        existingSourceIds={sources.map(s => s.indexed_document_id || s.document_id || '')}
      />
    </div>
  )
}
