'use client'

/**
 * NotebookPanel - Presentation Generator Panel
 *
 * Inline panel for notebook management and presentation generation.
 * Shows sources, allows adding documents, and generates presentations.
 * Can be collapsed/expanded with a toggle button.
 */

import { useState, useEffect } from 'react'
import {
  IconChevronDown,
  IconChevronRight,
  IconPlus,
  IconFileText,
  IconPresentation,
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
} from '@/components/ui'
import { cn } from '@/lib/utils'
import {
  notebookService,
  Notebook,
  NotebookSource,
  NotebookPresentation,
  PresentationConfig,
  PresentationTemplate,
} from '@/lib/services/notebook.service'
import { SourceSelector } from './source-selector'
import { PresentationViewer } from './presentation-viewer'
import { TemplateSelector } from './template-selector'

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
  const [presentations, setPresentations] = useState<NotebookPresentation[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // UI State
  const [sourcesExpanded, setSourcesExpanded] = useState(true)
  const [generationExpanded, setGenerationExpanded] = useState(true)
  const [isGenerating, setIsGenerating] = useState(false)
  const [showSourceSelector, setShowSourceSelector] = useState(false)

  // Presentation config
  const [presentationConfig, setPresentationConfig] = useState<Partial<PresentationConfig>>({
    template: 'corporate',
    language: 'es-ES',
    max_slides: 10,
    include_speaker_notes: true,
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
      const [sourcesRes, presentationsRes] = await Promise.all([
        notebookService.listSources(notebookId),
        notebookService.listPresentations(notebookId),
      ])

      console.log('[NotebookPanel] Sources response:', sourcesRes)
      console.log('[NotebookPanel] Presentations response:', presentationsRes)

      if (!sourcesRes.error && sourcesRes.data) {
        setSources(sourcesRes.data)
      }
      if (!presentationsRes.error && presentationsRes.data) {
        setPresentations(presentationsRes.data)
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

  const handleGeneratePresentation = async () => {
    if (!activeNotebook || sources.length === 0) return

    setIsGenerating(true)
    setError(null)

    try {
      const response = await notebookService.generatePresentation(activeNotebook.id, presentationConfig)
      if (response.error) {
        setError(response.error)
      } else if (response.data) {
        setPresentations(prev => [response.data!, ...prev])
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error generating presentation')
    } finally {
      setIsGenerating(false)
    }
  }

  // Collapsed state - show only toggle button
  if (!isOpen) {
    return (
      <div className={cn(
        "flex flex-col items-center py-4 px-2 border-l bg-[var(--sidebar-background)] shrink-0",
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
      "flex flex-col h-full border-l bg-[var(--sidebar-background)] w-80 shrink-0",
      className
    )}>
      {/* Header with collapse button */}
      <div className="p-3 border-b flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold">NouxCube Studio</h2>
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

              {/* Presentation Generation Section */}
              <Collapsible open={generationExpanded} onOpenChange={setGenerationExpanded}>
                <CollapsibleTrigger asChild>
                  <Button variant="ghost" className="w-full justify-between p-2 h-auto">
                    <span className="flex items-center gap-2">
                      <IconPresentation className="h-4 w-4" />
                      <span className="font-medium text-sm">Presentación</span>
                    </span>
                    {generationExpanded ? (
                      <IconChevronDown className="h-4 w-4" />
                    ) : (
                      <IconChevronRight className="h-4 w-4" />
                    )}
                  </Button>
                </CollapsibleTrigger>
                <CollapsibleContent className="space-y-2 mt-2">
                  {/* Template selector with preview */}
                  <TemplateSelector
                    selectedTemplate={presentationConfig.template || 'corporate'}
                    onSelect={(template) => setPresentationConfig(prev => ({ ...prev, template: template as PresentationTemplate }))}
                    compact
                  />

                  {/* Slides count selector */}
                  <Select
                    value={String(presentationConfig.max_slides || 10)}
                    onValueChange={(v) => setPresentationConfig(prev => ({ ...prev, max_slides: parseInt(v) }))}
                  >
                    <SelectTrigger className="h-7 text-xs">
                      <SelectValue placeholder="Número de slides" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="5">5 slides</SelectItem>
                      <SelectItem value="10">10 slides</SelectItem>
                      <SelectItem value="15">15 slides</SelectItem>
                      <SelectItem value="20">20 slides</SelectItem>
                    </SelectContent>
                  </Select>

                  <Button
                    className="w-full h-8 text-xs"
                    onClick={handleGeneratePresentation}
                    disabled={isGenerating || sources.length === 0}
                  >
                    {isGenerating ? (
                      <>
                        <IconLoader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
                        Generando...
                      </>
                    ) : (
                      <>
                        <IconPresentation className="h-3.5 w-3.5 mr-1.5" />
                        Generar Presentación
                      </>
                    )}
                  </Button>

                  {sources.length === 0 && (
                    <p className="text-[10px] text-muted-foreground text-center">
                      Añade fuentes para generar contenido
                    </p>
                  )}

                  {/* Recent presentations */}
                  {presentations.length > 0 && (
                    <div className="space-y-2 pt-2 border-t">
                      <p className="text-xs text-muted-foreground">Presentaciones generadas</p>
                      {presentations.slice(0, 3).map((presentation) => (
                        <PresentationViewer
                          key={presentation.id}
                          presentation={presentation}
                          notebookId={activeNotebook.id}
                          onDeleted={() => {
                            setPresentations(prev => prev.filter(p => p.id !== presentation.id))
                          }}
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
