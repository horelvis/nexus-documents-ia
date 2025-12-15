"use client"

import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Loader2, FolderOpen, Folder, ChevronRight, ChevronDown, Plus } from "lucide-react"
import { toast } from "sonner"
import { useFolderService, type FolderInfo } from "@/lib/services/folder.service"
import { cn } from "@/lib/utils"

interface MoveToFolderDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  documentIds: string[]
  onMoveComplete?: () => void
}

interface FolderItemProps {
  folder: FolderInfo
  level: number
  selectedPath: string | null
  onSelect: (path: string) => void
}

function FolderItem({ folder, level, selectedPath, onSelect }: FolderItemProps) {
  const [expanded, setExpanded] = useState(level === 0)
  const hasChildren = folder.children && folder.children.length > 0
  const isSelected = selectedPath === folder.path

  return (
    <div>
      <button
        type="button"
        className={cn(
          "w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-left text-sm transition-colors",
          isSelected
            ? "bg-primary text-primary-foreground"
            : "hover:bg-accent"
        )}
        style={{ paddingLeft: `${(level * 16) + 8}px` }}
        onClick={() => onSelect(folder.path)}
      >
        {hasChildren ? (
          <button
            type="button"
            className="p-0.5 hover:bg-accent rounded"
            onClick={(e) => {
              e.stopPropagation()
              setExpanded(!expanded)
            }}
          >
            {expanded ? (
              <ChevronDown className="h-4 w-4" />
            ) : (
              <ChevronRight className="h-4 w-4" />
            )}
          </button>
        ) : (
          <span className="w-5" />
        )}
        {isSelected ? (
          <FolderOpen className="h-4 w-4 flex-shrink-0" />
        ) : (
          <Folder className="h-4 w-4 flex-shrink-0" />
        )}
        <span className="truncate flex-1">{folder.name}</span>
        <span className={cn(
          "text-xs",
          isSelected ? "text-primary-foreground/70" : "text-muted-foreground"
        )}>
          {folder.document_count}
        </span>
      </button>

      {hasChildren && expanded && (
        <div>
          {folder.children.map((child) => (
            <FolderItem
              key={child.path}
              folder={child}
              level={level + 1}
              selectedPath={selectedPath}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export function MoveToFolderDialog({
  open,
  onOpenChange,
  documentIds,
  onMoveComplete,
}: MoveToFolderDialogProps) {
  const folderService = useFolderService()
  const [folders, setFolders] = useState<FolderInfo[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [isMoving, setIsMoving] = useState(false)
  const [selectedFolder, setSelectedFolder] = useState<string | null>(null)
  const [newFolderName, setNewFolderName] = useState("")
  const [showNewFolder, setShowNewFolder] = useState(false)

  // Load folders when dialog opens
  useEffect(() => {
    if (open) {
      loadFolders()
    } else {
      setSelectedFolder(null)
      setNewFolderName("")
      setShowNewFolder(false)
    }
  }, [open])

  const loadFolders = async () => {
    setIsLoading(true)
    try {
      const response = await folderService.getFolderTree()
      if (response.error) {
        toast.error(response.error)
      } else if (response.data) {
        setFolders(response.data.folders || [])
      }
    } catch (error) {
      console.error('Failed to load folders:', error)
      toast.error("Error al cargar las carpetas")
    } finally {
      setIsLoading(false)
    }
  }

  const handleMove = async () => {
    if (!selectedFolder) {
      toast.error("Selecciona una carpeta de destino")
      return
    }

    setIsMoving(true)
    try {
      const result = await folderService.moveDocuments(documentIds, selectedFolder)

      if (result.errors && result.errors.length > 0) {
        toast.error(`Error al mover algunos documentos: ${result.errors[0]}`)
      } else {
        toast.success(
          documentIds.length === 1
            ? "Documento movido correctamente"
            : `${documentIds.length} documentos movidos correctamente`
        )
        onOpenChange(false)
        onMoveComplete?.()
      }
    } catch (error) {
      console.error('Failed to move documents:', error)
      toast.error("Error al mover los documentos")
    } finally {
      setIsMoving(false)
    }
  }

  const handleCreateAndMove = async () => {
    if (!newFolderName.trim()) {
      toast.error("El nombre de la carpeta no puede estar vacío")
      return
    }

    setIsMoving(true)
    try {
      // Create folder first
      const folderPath = `/${newFolderName.trim()}`
      const createResponse = await folderService.createFolder(folderPath)

      if (createResponse.error) {
        toast.error(createResponse.error)
        return
      }

      // Then move documents
      const result = await folderService.moveDocuments(documentIds, folderPath)

      if (result.errors && result.errors.length > 0) {
        toast.error(`Error al mover algunos documentos: ${result.errors[0]}`)
      } else {
        toast.success(
          `Carpeta "${newFolderName}" creada y ${documentIds.length} documento(s) movido(s)`
        )
        onOpenChange(false)
        onMoveComplete?.()
      }
    } catch (error) {
      console.error('Failed to create folder and move:', error)
      toast.error("Error al crear carpeta y mover documentos")
    } finally {
      setIsMoving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[450px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FolderOpen className="h-5 w-5" />
            Mover a carpeta
          </DialogTitle>
          <DialogDescription>
            {documentIds.length === 1
              ? "Selecciona la carpeta de destino para el documento"
              : `Selecciona la carpeta de destino para ${documentIds.length} documentos`
            }
          </DialogDescription>
        </DialogHeader>

        <div className="py-4">
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : folders.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <Folder className="h-12 w-12 mx-auto mb-2 opacity-50" />
              <p>No hay carpetas creadas aún</p>
            </div>
          ) : (
            <ScrollArea className="h-[250px] pr-4">
              <div className="space-y-0.5">
                {folders.map((folder) => (
                  <FolderItem
                    key={folder.path}
                    folder={folder}
                    level={0}
                    selectedPath={selectedFolder}
                    onSelect={setSelectedFolder}
                  />
                ))}
              </div>
            </ScrollArea>
          )}

          {/* Create new folder option */}
          <div className="mt-4 pt-4 border-t">
            {showNewFolder ? (
              <div className="space-y-2">
                <input
                  type="text"
                  placeholder="Nombre de la nueva carpeta"
                  value={newFolderName}
                  onChange={(e) => setNewFolderName(e.target.value)}
                  className="w-full px-3 py-2 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-primary"
                  autoFocus
                />
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setShowNewFolder(false)
                      setNewFolderName("")
                    }}
                  >
                    Cancelar
                  </Button>
                  <Button
                    size="sm"
                    onClick={handleCreateAndMove}
                    disabled={isMoving || !newFolderName.trim()}
                  >
                    {isMoving ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      "Crear y mover"
                    )}
                  </Button>
                </div>
              </div>
            ) : (
              <Button
                variant="ghost"
                size="sm"
                className="w-full justify-start text-muted-foreground"
                onClick={() => setShowNewFolder(true)}
              >
                <Plus className="h-4 w-4 mr-2" />
                Crear nueva carpeta
              </Button>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button
            onClick={handleMove}
            disabled={isMoving || !selectedFolder}
          >
            {isMoving ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Moviendo...
              </>
            ) : (
              "Mover aquí"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
