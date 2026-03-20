'use client'

/**
 * NexusLM Notebooks Page
 *
 * Main listing page for NexusLM notebooks - an on-premise NotebookLM alternative.
 * Displays all notebooks with search, stats, and creation options.
 */

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import {
  IconPlus,
  IconSearch,
  IconNotebook,
  IconFileText,
  IconHeadphones,
  IconMessage,
  IconDotsVertical,
  IconTrash,
  IconArchive,
  IconRefresh,
  IconLoader2,
} from '@tabler/icons-react'
import {
  Button,
  Input,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  Label,
  Textarea,
} from '@/components/ui'
import {
  SidebarProvider,
  SidebarInset,
} from '@/components/ui'
import { useAuth } from '@/contexts/auth-context'
import { AppSidebar } from '@/components/layout/app-sidebar'
import { PageHeader } from '@/components/layout/page-header'
import { notebookService, Notebook as NotebookType, NotebookStats } from '@/lib/services/notebook.service'

// Emoji picker options
const EMOJI_OPTIONS = ['📓', '📚', '📖', '📝', '💡', '🎯', '🔬', '📊', '🎓', '🚀']

export default function NotebooksPage() {
  const { isLoaded, isAuthenticated } = useAuth()
  const router = useRouter()

  // State
  const [notebooks, setNotebooks] = useState<NotebookType[]>([])
  const [stats, setStats] = useState<NotebookStats | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')

  // Create dialog state
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const [newNotebook, setNewNotebook] = useState({
    title: '',
    description: '',
    emoji: '📓',
  })
  const [isCreating, setIsCreating] = useState(false)

  // Load notebooks
  const loadNotebooks = async () => {
    setIsLoading(true)
    setError(null)

    try {
      const [notebooksRes, statsRes] = await Promise.all([
        notebookService.list({ search: searchQuery || undefined }),
        notebookService.getStats(),
      ])

      if (notebooksRes.error) {
        setError(notebooksRes.error)
      } else {
        setNotebooks(notebooksRes.data?.notebooks || [])
      }

      if (!statsRes.error && statsRes.data) {
        setStats(statsRes.data)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al cargar notebooks')
    } finally {
      setIsLoading(false)
    }
  }

  // Load on mount and search change
  useEffect(() => {
    if (isAuthenticated) {
      loadNotebooks()
    }
  }, [isAuthenticated, searchQuery])

  // Redirect if not authenticated
  useEffect(() => {
    if (isLoaded && !isAuthenticated) {
      router.push('/auth/sign-in')
    }
  }, [isLoaded, isAuthenticated, router])

  // Handle create notebook
  const handleCreate = async () => {
    if (!newNotebook.title.trim()) return

    setIsCreating(true)
    try {
      const response = await notebookService.create({
        title: newNotebook.title.trim(),
        description: newNotebook.description.trim() || undefined,
        emoji: newNotebook.emoji,
      })

      if (response.error) {
        setError(response.error)
      } else if (response.data) {
        setCreateDialogOpen(false)
        setNewNotebook({ title: '', description: '', emoji: '📓' })
        router.push(`/notebooks/${response.data.id}`)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al crear notebook')
    } finally {
      setIsCreating(false)
    }
  }

  // Handle delete notebook
  const handleDelete = async (notebook: NotebookType) => {
    if (!confirm(`¿Eliminar "${notebook.title}"? Esta acción no se puede deshacer.`)) {
      return
    }

    try {
      const response = await notebookService.delete(notebook.id)
      if (response.error) {
        setError(response.error)
      } else {
        loadNotebooks()
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al eliminar')
    }
  }

  // Handle archive notebook
  const handleArchive = async (notebook: NotebookType) => {
    try {
      const response = await notebookService.update(notebook.id, {
        is_archived: !notebook.is_archived,
      })
      if (response.error) {
        setError(response.error)
      } else {
        loadNotebooks()
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al archivar')
    }
  }

  // Loading state
  if (!isLoaded) {
    return (
      <div className="flex items-center justify-center h-screen bg-background">
        <IconLoader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  if (!isAuthenticated) {
    return null
  }

  return (
    <SidebarProvider>
      <AppSidebar variant="inset" />

      <SidebarInset>
        {/* Header */}
        <PageHeader>
          <div className="flex items-center gap-2">
            <IconNotebook className="h-5 w-5 text-primary" />
            <span className="font-semibold">NouxCube Podcast</span>
          </div>
        </PageHeader>

        {/* Main Content */}
        <main className="flex-1 p-6 space-y-6 overflow-auto">
          {/* Page Header */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold">Mis Notebooks</h1>
              <p className="text-muted-foreground">
                Crea notebooks para analizar documentos y generar podcasts
              </p>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={loadNotebooks} disabled={isLoading}>
                <IconRefresh className={`mr-2 h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
                Actualizar
              </Button>
              <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
                <DialogTrigger asChild>
                  <Button>
                    <IconPlus className="mr-2 h-4 w-4" />
                    Nuevo Notebook
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Crear Notebook</DialogTitle>
                    <DialogDescription>
                      Crea un nuevo notebook para organizar tus documentos y generar contenido.
                    </DialogDescription>
                  </DialogHeader>
                  <div className="space-y-4 py-4">
                    <div className="space-y-2">
                      <Label>Emoji</Label>
                      <div className="flex gap-2 flex-wrap">
                        {EMOJI_OPTIONS.map((emoji) => (
                          <button
                            key={emoji}
                            type="button"
                            onClick={() => setNewNotebook({ ...newNotebook, emoji })}
                            className={`text-2xl p-2 rounded-lg hover:bg-muted transition-colors ${
                              newNotebook.emoji === emoji ? 'bg-primary/10 ring-2 ring-primary' : ''
                            }`}
                          >
                            {emoji}
                          </button>
                        ))}
                      </div>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="title">Título</Label>
                      <Input
                        id="title"
                        placeholder="Mi notebook de investigación"
                        value={newNotebook.title}
                        onChange={(e) => setNewNotebook({ ...newNotebook, title: e.target.value })}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="description">Descripción (opcional)</Label>
                      <Textarea
                        id="description"
                        placeholder="Describe el propósito de este notebook..."
                        value={newNotebook.description}
                        onChange={(e) => setNewNotebook({ ...newNotebook, description: e.target.value })}
                      />
                    </div>
                  </div>
                  <DialogFooter>
                    <Button variant="outline" onClick={() => setCreateDialogOpen(false)}>
                      Cancelar
                    </Button>
                    <Button onClick={handleCreate} disabled={!newNotebook.title.trim() || isCreating}>
                      {isCreating && <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />}
                      Crear Notebook
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
            </div>
          </div>

          {/* Stats Cards */}
          {stats && (
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>Notebooks</CardDescription>
                  <CardTitle className="text-2xl">{stats.total_notebooks}</CardTitle>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription className="flex items-center gap-1">
                    <IconFileText className="h-4 w-4" /> Fuentes
                  </CardDescription>
                  <CardTitle className="text-2xl">{stats.total_sources}</CardTitle>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription className="flex items-center gap-1">
                    <IconHeadphones className="h-4 w-4" /> Podcasts
                  </CardDescription>
                  <CardTitle className="text-2xl">{stats.total_audios}</CardTitle>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription className="flex items-center gap-1">
                    <IconMessage className="h-4 w-4" /> Chats
                  </CardDescription>
                  <CardTitle className="text-2xl">{stats.total_chats}</CardTitle>
                </CardHeader>
              </Card>
            </div>
          )}

          {/* Search */}
          <div className="relative">
            <IconSearch className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Buscar notebooks..."
              className="pl-10"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>

          {/* Error */}
          {error && (
            <div className="rounded-lg border border-destructive bg-destructive/10 p-4 text-destructive">
              {error}
            </div>
          )}

          {/* Notebooks Grid */}
          {isLoading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-48 rounded-lg border bg-muted animate-pulse" />
              ))}
            </div>
          ) : notebooks.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <div className="rounded-full bg-muted p-4 mb-4">
                <IconNotebook className="h-8 w-8 text-muted-foreground" />
              </div>
              <h3 className="text-lg font-semibold">No hay notebooks</h3>
              <p className="text-muted-foreground mb-4">
                {searchQuery
                  ? 'No se encontraron notebooks con ese criterio'
                  : 'Crea tu primer notebook para comenzar'}
              </p>
              {!searchQuery && (
                <Button onClick={() => setCreateDialogOpen(true)}>
                  <IconPlus className="mr-2 h-4 w-4" />
                  Crear Notebook
                </Button>
              )}
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {notebooks.map((notebook) => (
                <Card
                  key={notebook.id}
                  className="cursor-pointer hover:border-primary/50 transition-colors group"
                  onClick={() => router.push(`/notebooks/${notebook.id}`)}
                >
                  <CardHeader className="pb-2">
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-2xl">{notebook.emoji}</span>
                        <CardTitle className="text-lg line-clamp-1">{notebook.title}</CardTitle>
                      </div>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 opacity-0 group-hover:opacity-100 transition-opacity"
                          >
                            <IconDotsVertical className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem
                            onClick={(e) => {
                              e.stopPropagation()
                              handleArchive(notebook)
                            }}
                          >
                            <IconArchive className="mr-2 h-4 w-4" />
                            {notebook.is_archived ? 'Desarchivar' : 'Archivar'}
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            onClick={(e) => {
                              e.stopPropagation()
                              handleDelete(notebook)
                            }}
                            className="text-destructive"
                          >
                            <IconTrash className="mr-2 h-4 w-4" />
                            Eliminar
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                    {notebook.description && (
                      <CardDescription className="line-clamp-2">
                        {notebook.description}
                      </CardDescription>
                    )}
                  </CardHeader>
                  <CardContent>
                    <div className="flex items-center gap-4 text-sm text-muted-foreground">
                      <span className="flex items-center gap-1">
                        <IconFileText className="h-4 w-4" />
                        {notebook.source_count}
                      </span>
                      <span className="flex items-center gap-1">
                        <IconHeadphones className="h-4 w-4" />
                        {notebook.audio_count}
                      </span>
                      <span className="flex items-center gap-1">
                        <IconMessage className="h-4 w-4" />
                        {notebook.chat_count}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-2">
                      Actualizado {new Date(notebook.last_activity_at).toLocaleDateString()}
                    </p>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}
