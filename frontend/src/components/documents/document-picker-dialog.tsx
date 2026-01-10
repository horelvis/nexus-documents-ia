"use client"

import { useState, useEffect, useCallback } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Checkbox } from '@/components/ui/checkbox'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import {
  Loader2,
  Search,
  Folder,
  FolderOpen,
  File,
  ChevronRight,
  Home,
  X,
  Check,
  FileText,
  Image,
  FileSpreadsheet,
  Presentation,
} from 'lucide-react'
import { useDocumentService } from '@/lib/services/document.service'
import { useFolderService, FolderInfo } from '@/lib/services/folder.service'
import { formatFileSize, getRelativeTime } from '@/lib/document-utils'
import { useTranslation } from '@/lib/i18n/hooks'
import { cn } from '@/lib/utils'

export interface SelectedItem {
  id: string
  name: string
  type: 'document' | 'folder'
  path?: string
}

interface DocumentPickerDialogProps {
  open: boolean
  onClose: () => void
  onConfirm: (selectedItems: SelectedItem[]) => void
  title?: string
  description?: string
  multiSelect?: boolean
  allowFolders?: boolean
  allowDocuments?: boolean
}

interface DocumentItem {
  id: string
  filename: string
  title?: string
  file_type: string
  file_size: number
  created_at: string
  folder_path?: string
  type?: 'document' | 'folder'
  document_count?: number
}

export function DocumentPickerDialog({
  open,
  onClose,
  onConfirm,
  title,
  description,
  multiSelect = true,
  allowFolders = true,
  allowDocuments = true,
}: DocumentPickerDialogProps) {
  const { t } = useTranslation()
  const documentService = useDocumentService()
  const folderService = useFolderService()

  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [folders, setFolders] = useState<FolderInfo[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [currentPath, setCurrentPath] = useState<string>('')
  const [pathHistory, setPathHistory] = useState<string[]>([''])
  const [searchQuery, setSearchQuery] = useState('')

  const [selectedItems, setSelectedItems] = useState<Map<string, SelectedItem>>(new Map())

  // Load folder tree on mount
  useEffect(() => {
    if (open) {
      loadFolderTree()
      loadDocuments('')
    }
  }, [open])

  const loadFolderTree = async () => {
    const response = await folderService.getFolderTree()
    if (response.data?.folders) {
      setFolders(response.data.folders)
    }
  }

  const loadDocuments = async (folder: string, search?: string) => {
    setIsLoading(true)
    setError(null)

    try {
      const response = await documentService.getDocuments({
        folder: folder || undefined,
        search: search || undefined,
        per_page: 100,
      })

      if (response.error) {
        setError(response.error)
        setDocuments([])
      } else if (response.data) {
        // Combine folders and documents
        const items: DocumentItem[] = []

        // Add subfolders for current path
        const currentFolders = findSubfolders(folder)
        currentFolders.forEach(f => {
          items.push({
            id: `folder:${f.path}`,
            filename: f.name,
            file_type: 'folder',
            file_size: 0,
            created_at: '',
            folder_path: f.path,
            type: 'folder',
            document_count: f.document_count,
          })
        })

        // Add documents
        response.data.items?.forEach((doc: any) => {
          items.push({
            ...doc,
            type: 'document',
          })
        })

        setDocuments(items)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error loading documents')
    } finally {
      setIsLoading(false)
    }
  }

  const findSubfolders = (parentPath: string): FolderInfo[] => {
    const findInTree = (items: FolderInfo[], path: string): FolderInfo[] => {
      if (!path) {
        return items
      }

      for (const item of items) {
        if (item.path === path) {
          return item.children || []
        }
        if (item.children?.length) {
          const found = findInTree(item.children, path)
          if (found.length > 0) return found
        }
      }
      return []
    }

    return findInTree(folders, parentPath)
  }

  const handleFolderClick = (folderPath: string) => {
    setCurrentPath(folderPath)
    setPathHistory(prev => [...prev, folderPath])
    loadDocuments(folderPath, searchQuery)
  }

  const handleBreadcrumbClick = (index: number) => {
    const newPath = pathHistory[index]
    setCurrentPath(newPath)
    setPathHistory(prev => prev.slice(0, index + 1))
    loadDocuments(newPath, searchQuery)
  }

  const handleSearch = useCallback((query: string) => {
    setSearchQuery(query)
    loadDocuments(currentPath, query)
  }, [currentPath])

  const toggleItemSelection = (item: DocumentItem) => {
    const key = item.type === 'folder' ? `folder:${item.folder_path}` : item.id

    setSelectedItems(prev => {
      const newMap = new Map(prev)

      if (newMap.has(key)) {
        newMap.delete(key)
      } else {
        if (!multiSelect) {
          newMap.clear()
        }
        newMap.set(key, {
          id: item.type === 'folder' ? item.folder_path! : item.id,
          name: item.title || item.filename,
          type: item.type || 'document',
          path: item.folder_path,
        })
      }

      return newMap
    })
  }

  const removeSelectedItem = (key: string) => {
    setSelectedItems(prev => {
      const newMap = new Map(prev)
      newMap.delete(key)
      return newMap
    })
  }

  const handleConfirm = () => {
    onConfirm(Array.from(selectedItems.values()))
    setSelectedItems(new Map())
    onClose()
  }

  const handleClose = () => {
    setSelectedItems(new Map())
    setCurrentPath('')
    setPathHistory([''])
    setSearchQuery('')
    onClose()
  }

  const getFileIcon = (fileType: string) => {
    switch (fileType?.toLowerCase()) {
      case 'pdf':
        return <FileText className="h-5 w-5 text-red-500" />
      case 'doc':
      case 'docx':
        return <FileText className="h-5 w-5 text-blue-500" />
      case 'xls':
      case 'xlsx':
        return <FileSpreadsheet className="h-5 w-5 text-green-500" />
      case 'ppt':
      case 'pptx':
        return <Presentation className="h-5 w-5 text-orange-500" />
      case 'png':
      case 'jpg':
      case 'jpeg':
      case 'gif':
        return <Image className="h-5 w-5 text-purple-500" />
      case 'folder':
        return <Folder className="h-5 w-5 text-yellow-500" />
      default:
        return <File className="h-5 w-5 text-gray-500" />
    }
  }

  const getBreadcrumbs = () => {
    const parts = currentPath ? currentPath.split('/').filter(Boolean) : []
    return [
      { name: t('documentPicker.root') || 'Root', path: '' },
      ...parts.map((part, index) => ({
        name: part,
        path: '/' + parts.slice(0, index + 1).join('/'),
      })),
    ]
  }

  const isItemSelected = (item: DocumentItem) => {
    const key = item.type === 'folder' ? `folder:${item.folder_path}` : item.id
    return selectedItems.has(key)
  }

  const canSelectItem = (item: DocumentItem) => {
    if (item.type === 'folder') return allowFolders
    return allowDocuments
  }

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && handleClose()}>
      <DialogContent className="sm:max-w-[900px] h-[600px] flex flex-col p-0">
        <DialogHeader className="px-6 py-4 border-b">
          <DialogTitle>{title || t('documentPicker.title') || 'Select Documents'}</DialogTitle>
          <DialogDescription>
            {description || t('documentPicker.description') || 'Browse and select documents or folders to share'}
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 flex overflow-hidden">
          {/* Main Content */}
          <div className="flex-1 flex flex-col min-w-0">
            {/* Search & Breadcrumbs */}
            <div className="px-4 py-3 border-b space-y-3">
              {/* Search */}
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder={t('documentPicker.searchPlaceholder') || 'Search documents...'}
                  value={searchQuery}
                  onChange={(e) => handleSearch(e.target.value)}
                  className="pl-9"
                />
              </div>

              {/* Breadcrumbs */}
              <div className="flex items-center gap-1 text-sm overflow-x-auto">
                {getBreadcrumbs().map((crumb, index) => (
                  <div key={crumb.path} className="flex items-center">
                    {index > 0 && <ChevronRight className="h-4 w-4 mx-1 text-muted-foreground flex-shrink-0" />}
                    <button
                      onClick={() => handleBreadcrumbClick(index)}
                      className={cn(
                        "px-2 py-1 rounded hover:bg-muted transition-colors whitespace-nowrap",
                        index === getBreadcrumbs().length - 1 && "font-medium text-primary"
                      )}
                    >
                      {index === 0 ? <Home className="h-4 w-4" /> : crumb.name}
                    </button>
                  </div>
                ))}
              </div>
            </div>

            {/* Document List */}
            <ScrollArea className="flex-1">
              {isLoading ? (
                <div className="flex items-center justify-center h-48">
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
              ) : error ? (
                <div className="p-4 text-center text-destructive">{error}</div>
              ) : documents.length === 0 ? (
                <div className="p-8 text-center text-muted-foreground">
                  {t('documentPicker.noDocuments') || 'No documents found'}
                </div>
              ) : (
                <div className="divide-y">
                  {documents.map((item) => {
                    const isSelected = isItemSelected(item)
                    const canSelect = canSelectItem(item)

                    return (
                      <div
                        key={item.id}
                        className={cn(
                          "flex items-center gap-3 px-4 py-3 hover:bg-muted/50 transition-colors",
                          isSelected && "bg-primary/5",
                          item.type === 'folder' && "cursor-pointer"
                        )}
                        onClick={() => {
                          if (item.type === 'folder') {
                            handleFolderClick(item.folder_path!)
                          }
                        }}
                      >
                        {/* Checkbox */}
                        {canSelect && (
                          <Checkbox
                            checked={isSelected}
                            onCheckedChange={() => toggleItemSelection(item)}
                            onClick={(e) => e.stopPropagation()}
                          />
                        )}
                        {!canSelect && <div className="w-4" />}

                        {/* Icon */}
                        <div className="flex-shrink-0">
                          {item.type === 'folder' ? (
                            isSelected ? (
                              <FolderOpen className="h-5 w-5 text-yellow-500" />
                            ) : (
                              <Folder className="h-5 w-5 text-yellow-500" />
                            )
                          ) : (
                            getFileIcon(item.file_type)
                          )}
                        </div>

                        {/* Name & Details */}
                        <div className="flex-1 min-w-0">
                          <div className="font-medium truncate">
                            {item.title || item.filename}
                          </div>
                          <div className="text-xs text-muted-foreground">
                            {item.type === 'folder' ? (
                              <span>{item.document_count} {t('documentPicker.documents') || 'documents'}</span>
                            ) : (
                              <>
                                <span>{formatFileSize(item.file_size)}</span>
                                <span className="mx-2">•</span>
                                <span>{getRelativeTime(item.created_at)}</span>
                              </>
                            )}
                          </div>
                        </div>

                        {/* Folder indicator */}
                        {item.type === 'folder' && (
                          <ChevronRight className="h-5 w-5 text-muted-foreground" />
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </ScrollArea>
          </div>

          {/* Selected Items Panel */}
          <div className="w-64 border-l flex flex-col bg-muted/30">
            <div className="px-4 py-3 border-b">
              <h4 className="font-medium text-sm">
                {t('documentPicker.selected') || 'Selected'} ({selectedItems.size})
              </h4>
            </div>

            <ScrollArea className="flex-1">
              {selectedItems.size === 0 ? (
                <div className="p-4 text-center text-sm text-muted-foreground">
                  {t('documentPicker.noSelection') || 'No items selected'}
                </div>
              ) : (
                <div className="p-2 space-y-1">
                  {Array.from(selectedItems.entries()).map(([key, item]) => (
                    <div
                      key={key}
                      className="flex items-center gap-2 p-2 rounded bg-background border text-sm"
                    >
                      {item.type === 'folder' ? (
                        <Folder className="h-4 w-4 text-yellow-500 flex-shrink-0" />
                      ) : (
                        <File className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                      )}
                      <span className="flex-1 truncate">{item.name}</span>
                      <button
                        onClick={() => removeSelectedItem(key)}
                        className="p-1 rounded hover:bg-muted"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </ScrollArea>
          </div>
        </div>

        <DialogFooter className="px-6 py-4 border-t">
          <div className="flex items-center justify-between w-full">
            <div className="text-sm text-muted-foreground">
              {selectedItems.size > 0 && (
                <>
                  {selectedItems.size} {t('documentPicker.itemsSelected') || 'items selected'}
                </>
              )}
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={handleClose}>
                {t('common.cancel') || 'Cancel'}
              </Button>
              <Button onClick={handleConfirm} disabled={selectedItems.size === 0}>
                <Check className="h-4 w-4 mr-2" />
                {t('documentPicker.confirm') || 'Confirm Selection'}
              </Button>
            </div>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
