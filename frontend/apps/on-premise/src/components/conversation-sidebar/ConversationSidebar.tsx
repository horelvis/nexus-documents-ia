'use client'

/**
 * Conversation Sidebar Component
 *
 * Displays chat history with search, create, delete functionality.
 * Supports bulk selection and deletion of conversations.
 * Uses Sheet overlay for both mobile and desktop.
 */

import { useState, useEffect, useCallback } from 'react'
import {
  IconPlus,
  IconSearch,
  IconMessage,
  IconPin,
  IconPinnedOff,
  IconTrash,
  IconDotsVertical,
  IconPencil,
  IconX,
  IconClock,
  IconCheckbox,
  IconSquare,
  IconSquareCheck,
} from '@tabler/icons-react'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui'
import { Button } from '@/components/ui'
import { Input } from '@/components/ui'
import { ScrollArea } from '@/components/ui'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui'
import { cn } from '@/lib/utils'
import { conversationService } from '@/lib/services/conversation.service'
import { ConversationListItem } from '@/lib/types/conversation'

interface ConversationSidebarProps {
  isOpen: boolean
  onOpenChange: (open: boolean) => void
  activeConversationId: string | null
  onSelectConversation: (id: string) => void
  onNewConversation: () => void
  onDeleteConversation: (id: string) => void
  onDeleteMultiple?: (ids: string[]) => void
  className?: string
}

export function ConversationSidebar({
  isOpen,
  onOpenChange,
  activeConversationId,
  onSelectConversation,
  onNewConversation,
  onDeleteConversation,
  onDeleteMultiple,
}: ConversationSidebarProps) {
  const [conversations, setConversations] = useState<ConversationListItem[]>([])
  const [searchQuery, setSearchQuery] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingTitle, setEditingTitle] = useState('')
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [conversationToDelete, setConversationToDelete] = useState<string | null>(null)

  // Selection mode state
  const [selectionMode, setSelectionMode] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())

  // Bulk/all delete dialog
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = useState(false)
  const [deleteAllDialogOpen, setDeleteAllDialogOpen] = useState(false)

  // Load conversations
  const loadConversations = useCallback(() => {
    const list = conversationService.getList({
      search: searchQuery || undefined,
      sortBy: 'updatedAt',
      sortOrder: 'desc',
    })
    setConversations(list)
  }, [searchQuery])

  useEffect(() => {
    loadConversations()
  }, [loadConversations])

  // Refresh when sidebar opens
  useEffect(() => {
    if (isOpen) {
      loadConversations()
    }
  }, [isOpen, loadConversations])

  // Exit selection mode when sidebar closes
  useEffect(() => {
    if (!isOpen) {
      setSelectionMode(false)
      setSelectedIds(new Set())
    }
  }, [isOpen])

  // Handle pin toggle
  const handleTogglePin = (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    conversationService.togglePin(id)
    loadConversations()
  }

  // Handle rename
  const handleStartRename = (id: string, currentTitle: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setEditingId(id)
    setEditingTitle(currentTitle)
  }

  const handleSaveRename = (id: string) => {
    if (editingTitle.trim()) {
      conversationService.rename(id, editingTitle.trim())
      loadConversations()
    }
    setEditingId(null)
    setEditingTitle('')
  }

  const handleCancelRename = () => {
    setEditingId(null)
    setEditingTitle('')
  }

  // Handle single delete
  const handleDeleteClick = (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setConversationToDelete(id)
    setDeleteDialogOpen(true)
  }

  const handleConfirmDelete = () => {
    if (conversationToDelete) {
      onDeleteConversation(conversationToDelete)
      conversationService.delete(conversationToDelete)
      loadConversations()
    }
    setDeleteDialogOpen(false)
    setConversationToDelete(null)
  }

  // Handle selection toggle
  const handleToggleSelection = (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  const handleSelectAll = () => {
    setSelectedIds(new Set(conversations.map((c) => c.id)))
  }

  const handleCancelSelection = () => {
    setSelectionMode(false)
    setSelectedIds(new Set())
  }

  // Bulk delete
  const handleBulkDeleteClick = () => {
    if (selectedIds.size > 0) {
      setBulkDeleteDialogOpen(true)
    }
  }

  const handleConfirmBulkDelete = () => {
    const ids = Array.from(selectedIds)
    conversationService.deleteMultiple(ids)
    onDeleteMultiple?.(ids)
    setSelectedIds(new Set())
    setSelectionMode(false)
    loadConversations()
    setBulkDeleteDialogOpen(false)
  }

  // Delete all
  const handleDeleteAllClick = () => {
    setDeleteAllDialogOpen(true)
  }

  const handleConfirmDeleteAll = () => {
    const allIds = conversations.map((c) => c.id)
    conversationService.clearAll()
    onDeleteMultiple?.(allIds)
    setSelectionMode(false)
    setSelectedIds(new Set())
    loadConversations()
    setDeleteAllDialogOpen(false)
  }

  // Handle conversation selection
  const handleSelectConversation = (id: string) => {
    if (selectionMode) {
      handleToggleSelection(id, { stopPropagation: () => {} } as React.MouseEvent)
      return
    }
    onSelectConversation(id)
    onOpenChange(false)
  }

  // Handle new conversation
  const handleNewConversation = () => {
    onNewConversation()
    onOpenChange(false)
  }

  // Format relative time
  const formatRelativeTime = (date: Date) => {
    const now = new Date()
    const diff = now.getTime() - new Date(date).getTime()
    const minutes = Math.floor(diff / 60000)
    const hours = Math.floor(minutes / 60)
    const days = Math.floor(hours / 24)

    if (minutes < 1) return 'Ahora'
    if (minutes < 60) return `${minutes}m`
    if (hours < 24) return `${hours}h`
    if (days < 7) return `${days}d`
    return new Date(date).toLocaleDateString('es', { month: 'short', day: 'numeric' })
  }

  return (
    <>
      <Sheet open={isOpen} onOpenChange={onOpenChange}>
        <SheetContent side="left" className="w-80 p-0 flex flex-col">
          <SheetHeader className="p-4 pb-3 border-b space-y-3">
            <div className="flex items-center gap-2 pr-8">
              {/* New conversation button - left side */}
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 shrink-0"
                    onClick={handleNewConversation}
                  >
                    <IconPlus className="h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Nueva conversación</TooltipContent>
              </Tooltip>

              <SheetTitle className="flex-1">Conversaciones</SheetTitle>

              {/* Selection mode toggle */}
              {conversations.length > 0 && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant={selectionMode ? 'secondary' : 'ghost'}
                      size="icon"
                      className="h-8 w-8 shrink-0"
                      onClick={() => {
                        if (selectionMode) {
                          handleCancelSelection()
                        } else {
                          setSelectionMode(true)
                        }
                      }}
                    >
                      <IconCheckbox className="h-4 w-4" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>{selectionMode ? 'Salir de selección' : 'Seleccionar'}</TooltipContent>
                </Tooltip>
              )}
            </div>

            {/* Search */}
            <div className="relative">
              <IconSearch className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Buscar conversaciones..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9 h-9"
              />
              {searchQuery && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="absolute right-1 top-1/2 -translate-y-1/2 h-6 w-6"
                  onClick={() => setSearchQuery('')}
                >
                  <IconX className="h-3 w-3" />
                </Button>
              )}
            </div>
          </SheetHeader>

          {/* Conversation List */}
          <ScrollArea className="flex-1 h-[calc(100vh-180px)]">
            <div className="p-2 space-y-1">
              {conversations.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
                  <IconMessage className="h-12 w-12 text-muted-foreground/30 mb-3" />
                  <p className="text-sm text-muted-foreground">
                    {searchQuery ? 'No se encontraron conversaciones' : 'Aún no tienes conversaciones'}
                  </p>
                  {!searchQuery && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="mt-4"
                      onClick={handleNewConversation}
                    >
                      <IconPlus className="h-4 w-4 mr-2" />
                      Nueva conversación
                    </Button>
                  )}
                </div>
              ) : (
                conversations.map((conv) => (
                  <div
                    key={conv.id}
                    className={cn(
                      'group relative flex items-start gap-2 p-3 rounded-lg cursor-pointer transition-colors',
                      'hover:bg-accent/50',
                      activeConversationId === conv.id && 'bg-accent',
                      selectionMode && selectedIds.has(conv.id) && 'bg-accent/70'
                    )}
                    onClick={() => handleSelectConversation(conv.id)}
                  >
                    {/* Checkbox in selection mode */}
                    {selectionMode && (
                      <button
                        className="shrink-0 mt-0.5"
                        onClick={(e) => handleToggleSelection(conv.id, e)}
                      >
                        {selectedIds.has(conv.id) ? (
                          <IconSquareCheck className="h-5 w-5 text-primary" />
                        ) : (
                          <IconSquare className="h-5 w-5 text-muted-foreground" />
                        )}
                      </button>
                    )}

                    <div className="flex flex-col gap-1 min-w-0 flex-1">
                      {/* Title row */}
                      <div className="flex items-start justify-between gap-2">
                        {editingId === conv.id ? (
                          <Input
                            value={editingTitle}
                            onChange={(e) => setEditingTitle(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') handleSaveRename(conv.id)
                              if (e.key === 'Escape') handleCancelRename()
                            }}
                            onBlur={() => handleSaveRename(conv.id)}
                            onClick={(e) => e.stopPropagation()}
                            className="h-7 text-sm"
                            autoFocus
                          />
                        ) : (
                          <div className="flex items-center gap-1.5 min-w-0 flex-1">
                            {conv.pinned && (
                              <IconPin className="h-3 w-3 text-primary shrink-0" />
                            )}
                            <span className="text-sm font-medium truncate">{conv.title}</span>
                          </div>
                        )}

                        {/* Actions dropdown - hidden in selection mode */}
                        {!selectionMode && (
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-6 w-6 opacity-0 group-hover:opacity-100 shrink-0"
                                onClick={(e) => e.stopPropagation()}
                              >
                                <IconDotsVertical className="h-4 w-4" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end" className="w-40">
                              <DropdownMenuItem onClick={(e) => handleTogglePin(conv.id, e)}>
                                {conv.pinned ? (
                                  <>
                                    <IconPinnedOff className="h-4 w-4 mr-2" />
                                    Desfijar
                                  </>
                                ) : (
                                  <>
                                    <IconPin className="h-4 w-4 mr-2" />
                                    Fijar
                                  </>
                                )}
                              </DropdownMenuItem>
                              <DropdownMenuItem
                                onClick={(e) => handleStartRename(conv.id, conv.title, e)}
                              >
                                <IconPencil className="h-4 w-4 mr-2" />
                                Renombrar
                              </DropdownMenuItem>
                              <DropdownMenuSeparator />
                              <DropdownMenuItem
                                onClick={(e) => handleDeleteClick(conv.id, e)}
                                className="text-destructive focus:text-destructive"
                              >
                                <IconTrash className="h-4 w-4 mr-2" />
                                Eliminar
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        )}
                      </div>

                      {/* Preview */}
                      {conv.preview && (
                        <p className="text-xs text-muted-foreground line-clamp-2">
                          {conv.preview}
                        </p>
                      )}

                      {/* Metadata row */}
                      <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                        <span className="flex items-center gap-1">
                          <IconClock className="h-3 w-3" />
                          {formatRelativeTime(conv.updatedAt)}
                        </span>
                        <span className="flex items-center gap-1">
                          <IconMessage className="h-3 w-3" />
                          {conv.messageCount}
                        </span>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </ScrollArea>

          {/* Selection action bar */}
          {selectionMode && selectedIds.size > 0 && (
            <div className="p-3 border-t bg-muted/50 flex items-center justify-between gap-2">
              <span className="text-sm text-muted-foreground">
                {selectedIds.size} seleccionada{selectedIds.size !== 1 ? 's' : ''}
              </span>
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" onClick={handleSelectAll}>
                  Todos
                </Button>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={handleBulkDeleteClick}
                >
                  <IconTrash className="h-4 w-4 mr-1" />
                  Eliminar
                </Button>
              </div>
            </div>
          )}

          {/* Footer */}
          {conversations.length > 0 && !(selectionMode && selectedIds.size > 0) && (
            <div className="p-3 border-t flex items-center justify-between">
              <p className="text-xs text-muted-foreground">
                {conversations.length} conversación{conversations.length !== 1 ? 'es' : ''}
              </p>
              <Button
                variant="ghost"
                size="sm"
                className="text-xs text-destructive hover:text-destructive h-7"
                onClick={handleDeleteAllClick}
              >
                <IconTrash className="h-3 w-3 mr-1" />
                Eliminar todo
              </Button>
            </div>
          )}
        </SheetContent>
      </Sheet>

      {/* Single delete confirmation dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Eliminar conversación?</AlertDialogTitle>
            <AlertDialogDescription>
              Esta acción no se puede deshacer. La conversación y todos sus mensajes
              serán eliminados permanentemente.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleConfirmDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Eliminar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Bulk delete confirmation dialog */}
      <AlertDialog open={bulkDeleteDialogOpen} onOpenChange={setBulkDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Eliminar {selectedIds.size} conversación{selectedIds.size !== 1 ? 'es' : ''}?</AlertDialogTitle>
            <AlertDialogDescription>
              Esta acción no se puede deshacer. Las conversaciones seleccionadas y todos
              sus mensajes serán eliminados permanentemente.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleConfirmBulkDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Eliminar {selectedIds.size}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Delete all confirmation dialog */}
      <AlertDialog open={deleteAllDialogOpen} onOpenChange={setDeleteAllDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Eliminar todas las conversaciones?</AlertDialogTitle>
            <AlertDialogDescription>
              Esta acción no se puede deshacer. Todas las conversaciones ({conversations.length})
              y sus mensajes serán eliminados permanentemente.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleConfirmDeleteAll}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Eliminar todo
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
