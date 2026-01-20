'use client'

/**
 * Conversation Sidebar Component
 *
 * Displays chat history with search, create, delete functionality.
 * Uses Sheet for mobile and fixed sidebar for desktop.
 */

import { useState, useEffect, useCallback } from 'react'
import {
  Plus,
  Search,
  MessageSquare,
  Pin,
  PinOff,
  Trash2,
  MoreHorizontal,
  Pencil,
  X,
  Clock,
  ChevronLeft,
} from 'lucide-react'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@nexus/shared/ui'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@nexus/shared/ui'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@nexus/shared/ui'
import { Button } from '@nexus/shared/ui'
import { Input } from '@nexus/shared/ui'
import { ScrollArea } from '@nexus/shared/ui'
import { Tooltip, TooltipContent, TooltipTrigger } from '@nexus/shared/ui'
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
  className?: string
}

export function ConversationSidebar({
  isOpen,
  onOpenChange,
  activeConversationId,
  onSelectConversation,
  onNewConversation,
  onDeleteConversation,
  className,
}: ConversationSidebarProps) {
  const [conversations, setConversations] = useState<ConversationListItem[]>([])
  const [searchQuery, setSearchQuery] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingTitle, setEditingTitle] = useState('')
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [conversationToDelete, setConversationToDelete] = useState<string | null>(null)

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

  // Handle delete
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

  const SidebarContent = () => (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="p-4 border-b space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-lg">Conversaciones</h2>
          <div className="flex items-center gap-1">
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8"
                  onClick={() => {
                    onNewConversation()
                    onOpenChange(false)
                  }}
                >
                  <Plus className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Nueva conversación</TooltipContent>
            </Tooltip>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 md:hidden"
              onClick={() => onOpenChange(false)}
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* Search */}
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
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
              <X className="h-3 w-3" />
            </Button>
          )}
        </div>
      </div>

      {/* Conversation List */}
      <ScrollArea className="flex-1">
        <div className="p-2 space-y-1">
          {conversations.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
              <MessageSquare className="h-12 w-12 text-muted-foreground/30 mb-3" />
              <p className="text-sm text-muted-foreground">
                {searchQuery ? 'No se encontraron conversaciones' : 'Aún no tienes conversaciones'}
              </p>
              {!searchQuery && (
                <Button
                  variant="outline"
                  size="sm"
                  className="mt-4"
                  onClick={() => {
                    onNewConversation()
                    onOpenChange(false)
                  }}
                >
                  <Plus className="h-4 w-4 mr-2" />
                  Nueva conversación
                </Button>
              )}
            </div>
          ) : (
            conversations.map((conv) => (
              <div
                key={conv.id}
                className={cn(
                  'group relative flex flex-col gap-1 p-3 rounded-lg cursor-pointer transition-colors',
                  'hover:bg-accent/50',
                  activeConversationId === conv.id && 'bg-accent'
                )}
                onClick={() => {
                  onSelectConversation(conv.id)
                  onOpenChange(false)
                }}
              >
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
                        <Pin className="h-3 w-3 text-primary shrink-0" />
                      )}
                      <span className="text-sm font-medium truncate">{conv.title}</span>
                    </div>
                  )}

                  {/* Actions dropdown */}
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6 opacity-0 group-hover:opacity-100 shrink-0"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <MoreHorizontal className="h-4 w-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="w-40">
                      <DropdownMenuItem onClick={(e) => handleTogglePin(conv.id, e)}>
                        {conv.pinned ? (
                          <>
                            <PinOff className="h-4 w-4 mr-2" />
                            Desfijar
                          </>
                        ) : (
                          <>
                            <Pin className="h-4 w-4 mr-2" />
                            Fijar
                          </>
                        )}
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        onClick={(e) => handleStartRename(conv.id, conv.title, e)}
                      >
                        <Pencil className="h-4 w-4 mr-2" />
                        Renombrar
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem
                        onClick={(e) => handleDeleteClick(conv.id, e)}
                        className="text-destructive focus:text-destructive"
                      >
                        <Trash2 className="h-4 w-4 mr-2" />
                        Eliminar
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
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
                    <Clock className="h-3 w-3" />
                    {formatRelativeTime(conv.updatedAt)}
                  </span>
                  <span className="flex items-center gap-1">
                    <MessageSquare className="h-3 w-3" />
                    {conv.messageCount}
                  </span>
                </div>
              </div>
            ))
          )}
        </div>
      </ScrollArea>

      {/* Footer */}
      {conversations.length > 0 && (
        <div className="p-3 border-t">
          <p className="text-xs text-muted-foreground text-center">
            {conversations.length} conversación{conversations.length !== 1 ? 'es' : ''}
          </p>
        </div>
      )}

      {/* Delete confirmation dialog */}
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
    </div>
  )

  return (
    <>
      {/* Mobile: Sheet */}
      <Sheet open={isOpen} onOpenChange={onOpenChange}>
        <SheetContent side="left" className="w-80 p-0 md:hidden">
          {/* Visually hidden title for accessibility */}
          <SheetTitle className="sr-only">Historial de conversaciones</SheetTitle>
          <SidebarContent />
        </SheetContent>
      </Sheet>

      {/* Desktop: Fixed Sidebar */}
      <aside
        className={cn(
          'hidden md:flex flex-col w-72 border-r bg-background shrink-0',
          'transition-all duration-300 ease-in-out',
          isOpen ? 'translate-x-0' : '-translate-x-full absolute left-0 top-0 bottom-0 z-40',
          className
        )}
      >
        <SidebarContent />
      </aside>
    </>
  )
}
