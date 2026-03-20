'use client'

import { useState, useEffect } from 'react'
import { IconSearch, IconFile, IconCheck, IconLoader2 } from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Checkbox } from '@/components/ui/checkbox'
import { Attachment, IndexedAttachment, getFileTypeConfig } from '@/lib/types/emma'
import { connectorService, IndexedDocument } from '@/lib/services/connector.service'

interface IndexedDocsPickerProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSelect: (attachments: Attachment[]) => void
  existingIds: string[]
  maxSelectable: number
}

export function IndexedDocsPicker({
  open,
  onOpenChange,
  onSelect,
  existingIds,
  maxSelectable,
}: IndexedDocsPickerProps) {
  const [docs, setDocs] = useState<IndexedDocument[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())

  // Load documents when dialog opens
  useEffect(() => {
    if (open) {
      loadDocuments()
      setSelectedIds(new Set())
    }
  }, [open])

  const loadDocuments = async (search?: string) => {
    setIsLoading(true)
    try {
      const response = await connectorService.getIndexedDocuments({
        search: search || undefined,
        page_size: 50,
        status: 'indexed',
      })
      if (response.data) {
        setDocs(response.data.items)
      }
    } catch (error) {
      console.error('Failed to load documents:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const handleSearch = () => {
    loadDocuments(searchQuery)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      handleSearch()
    }
  }

  const toggleSelection = (docId: string) => {
    const newSelected = new Set(selectedIds)
    if (newSelected.has(docId)) {
      newSelected.delete(docId)
    } else if (newSelected.size < maxSelectable) {
      newSelected.add(docId)
    }
    setSelectedIds(newSelected)
  }

  const handleConfirm = () => {
    const attachments: IndexedAttachment[] = []

    for (const docId of selectedIds) {
      const doc = docs.find((d) => d.id === docId)
      if (doc && !existingIds.includes(doc.id)) {
        // Get a friendly name: prefer title, then extract from external_path, then use filename from external_id
        let docName = doc.title
        if (!docName && doc.external_path) {
          // Extract filename from path
          const pathParts = doc.external_path.split('/')
          docName = pathParts[pathParts.length - 1] || doc.external_path
        }
        if (!docName) {
          // Try to extract from external_id if it looks like a path
          if (doc.external_id && doc.external_id.includes('/')) {
            const idParts = doc.external_id.split('/')
            docName = idParts[idParts.length - 1]
          } else if (doc.external_id) {
            // external_id might be a UUID - try filename field or use a generic name with extension
            const ext = doc.file_extension || doc.mime_type?.split('/')[1] || 'file'
            docName = `Documento.${ext}`
          } else {
            docName = 'Documento'
          }
        }

        attachments.push({
          id: doc.id,
          name: docName,
          type: 'indexed',
          documentId: doc.id,
          fileType: doc.mime_type || undefined,
          size: doc.size_bytes,
          previewUrl: doc.external_url || undefined,
        })
      }
    }

    onSelect(attachments)
    setSearchQuery('')
  }

  const canConfirm = selectedIds.size > 0

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Seleccionar documentos</DialogTitle>
        </DialogHeader>

        {/* Search */}
        <div className="relative">
          <IconSearch className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Buscar documentos..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            className="pl-9"
          />
        </div>

        {/* Documents list */}
        <ScrollArea className="h-[300px] border rounded-md">
          {isLoading ? (
            <div className="flex items-center justify-center h-full p-4">
              <IconLoader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : docs.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full p-4 text-center text-muted-foreground">
              <IconFile className="h-10 w-10 mb-2" />
              <p className="text-sm font-medium">No hay documentos</p>
              <p className="text-xs">Conecta un servicio para sincronizar documentos</p>
            </div>
          ) : (
            <div className="p-2 space-y-1">
              {docs.map((doc) => {
                const isSelected = selectedIds.has(doc.id)
                const isAlreadyAttached = existingIds.includes(doc.id)
                const config = getFileTypeConfig(doc.mime_type, doc.file_extension)

                return (
                  <div
                    key={doc.id}
                    role="button"
                    tabIndex={isAlreadyAttached ? -1 : 0}
                    onClick={() => !isAlreadyAttached && toggleSelection(doc.id)}
                    onKeyDown={(e) => {
                      if ((e.key === 'Enter' || e.key === ' ') && !isAlreadyAttached) {
                        e.preventDefault()
                        toggleSelection(doc.id)
                      }
                    }}
                    className={cn(
                      'w-full flex items-center gap-3 p-2.5 rounded-md text-left transition-colors cursor-pointer',
                      isSelected && 'bg-primary/10 border border-primary/30',
                      !isSelected && !isAlreadyAttached && 'hover:bg-muted',
                      isAlreadyAttached && 'opacity-50 cursor-not-allowed'
                    )}
                  >
                    <Checkbox
                      checked={isSelected || isAlreadyAttached}
                      disabled={isAlreadyAttached}
                      className="pointer-events-none"
                    />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">
                        {doc.title || (doc.external_path ? doc.external_path.split('/').pop() : `Documento.${config.label.toLowerCase()}`)}
                      </p>
                      <p className="text-xs text-muted-foreground truncate">
                        <span className={cn('font-medium', config.color)}>
                          {config.label}
                        </span>
                        {doc.external_path && ` • ${doc.external_path}`}
                      </p>
                    </div>
                    {isAlreadyAttached && (
                      <IconCheck className="h-4 w-4 text-primary shrink-0" />
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </ScrollArea>

        <DialogFooter className="flex-row justify-between sm:justify-between">
          <span className="text-xs text-muted-foreground">
            {selectedIds.size > 0
              ? `${selectedIds.size} seleccionado${selectedIds.size > 1 ? 's' : ''}`
              : 'Ninguno seleccionado'}
            {maxSelectable < 10 && ` (máx. ${maxSelectable})`}
          </span>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cancelar
            </Button>
            <Button onClick={handleConfirm} disabled={!canConfirm}>
              Agregar
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
