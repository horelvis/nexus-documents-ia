'use client'

/**
 * SourceSelector - Document Selection Component
 *
 * Allows users to search and select documents to add as notebook sources.
 * Uses connectorService.getIndexedDocuments() for document retrieval.
 */

import { useState, useEffect } from 'react'
import { IconSearch, IconFileText, IconLoader2, IconCheck } from '@tabler/icons-react'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  Input,
  Button,
  ScrollArea,
} from '@/components/ui'
import { cn } from '@/lib/utils'
import { connectorService, IndexedDocument } from '@/lib/services/connector.service'

interface SourceSelectorProps {
  isOpen: boolean
  onOpenChange: (open: boolean) => void
  onSelect: (documentId: string) => void
  existingSourceIds: string[]
}

export function SourceSelector({
  isOpen,
  onOpenChange,
  onSelect,
  existingSourceIds,
}: SourceSelectorProps) {
  const [documents, setDocuments] = useState<IndexedDocument[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)

  // Load documents when opened
  useEffect(() => {
    if (isOpen) {
      loadDocuments()
    }
  }, [isOpen])

  const loadDocuments = async () => {
    setIsLoading(true)

    try {
      const response = await connectorService.getIndexedDocuments({
        search: searchQuery || undefined,
        page_size: 50,
        status: 'indexed',
      })

      if (response.data) {
        setDocuments(response.data.items)
      } else if (response.error) {
        console.error('Error loading documents:', response.error)
      }
    } catch (err) {
      console.error('Error loading documents:', err)
    } finally {
      setIsLoading(false)
    }
  }

  // Manual search on Enter key
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      loadDocuments()
    }
  }

  const handleSelect = () => {
    if (selectedId) {
      onSelect(selectedId)
      setSelectedId(null)
    }
  }

  // Get display name for document
  const getDocumentName = (doc: IndexedDocument): string => {
    if (doc.title) return doc.title
    if (doc.external_path) {
      const parts = doc.external_path.split('/')
      return parts[parts.length - 1] || doc.external_path
    }
    return `Documento.${doc.file_extension || 'file'}`
  }

  const filteredDocuments = documents.filter(
    doc => !existingSourceIds.includes(doc.id)
  )

  return (
    <Sheet open={isOpen} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-96">
        <SheetHeader>
          <SheetTitle>Añadir Fuente</SheetTitle>
        </SheetHeader>

        <div className="mt-4 space-y-4">
          {/* Search input */}
          <div className="relative">
            <IconSearch className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Buscar documentos..."
              className="pl-10"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={handleKeyDown}
            />
          </div>

          {/* Documents list */}
          <ScrollArea className="h-[400px]">
            {isLoading ? (
              <div className="flex items-center justify-center py-8">
                <IconLoader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : filteredDocuments.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                {documents.length === 0
                  ? 'No hay documentos disponibles'
                  : 'Todos los documentos ya están añadidos'}
              </div>
            ) : (
              <div className="space-y-2">
                {filteredDocuments.map((doc) => (
                  <button
                    key={doc.id}
                    onClick={() => setSelectedId(doc.id === selectedId ? null : doc.id)}
                    className={cn(
                      "w-full flex items-center gap-3 p-3 rounded-lg border text-left transition-colors",
                      selectedId === doc.id
                        ? "border-primary bg-primary/5"
                        : "border-transparent hover:bg-muted"
                    )}
                  >
                    <div className="h-10 w-10 rounded-lg bg-muted flex items-center justify-center shrink-0">
                      <IconFileText className="h-5 w-5 text-muted-foreground" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-medium truncate">{getDocumentName(doc)}</p>
                      <p className="text-xs text-muted-foreground">
                        {(doc.file_extension || doc.mime_type?.split('/')[1] || 'file').toUpperCase()}
                        {doc.indexed_at && ` • ${new Date(doc.indexed_at).toLocaleDateString()}`}
                      </p>
                    </div>
                    {selectedId === doc.id && (
                      <IconCheck className="h-5 w-5 text-primary shrink-0" />
                    )}
                  </button>
                ))}
              </div>
            )}
          </ScrollArea>

          {/* Actions */}
          <div className="flex gap-2">
            <Button variant="outline" className="flex-1" onClick={() => onOpenChange(false)}>
              Cancelar
            </Button>
            <Button className="flex-1" onClick={handleSelect} disabled={!selectedId}>
              Añadir
            </Button>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}
