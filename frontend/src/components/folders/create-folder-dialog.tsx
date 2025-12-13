"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Loader2, FolderPlus } from "lucide-react"
import { toast } from "sonner"
import { useFolderService } from "@/lib/services/folder.service"

interface CreateFolderDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  parentFolder?: string | null
  onFolderCreated?: (folderPath: string) => void
}

export function CreateFolderDialog({
  open,
  onOpenChange,
  parentFolder,
  onFolderCreated,
}: CreateFolderDialogProps) {
  const folderService = useFolderService()
  const [folderName, setFolderName] = useState("")
  const [isCreating, setIsCreating] = useState(false)

  const handleCreate = async () => {
    const trimmedName = folderName.trim()
    if (!trimmedName) {
      toast.error("El nombre de la carpeta no puede estar vacío")
      return
    }

    // Validate folder name (no special characters that would break paths)
    if (/[<>:"|?*\\]/.test(trimmedName)) {
      toast.error("El nombre contiene caracteres no permitidos")
      return
    }

    setIsCreating(true)
    try {
      // Build full path
      const basePath = parentFolder && parentFolder !== '/' ? parentFolder : ''
      const fullPath = `${basePath}/${trimmedName}`

      const response = await folderService.createFolder(fullPath)

      if (response.error) {
        toast.error(response.error)
      } else {
        toast.success(`Carpeta "${trimmedName}" creada`)
        setFolderName("")
        onOpenChange(false)
        onFolderCreated?.(fullPath)
      }
    } catch (error) {
      console.error('Failed to create folder:', error)
      toast.error("Error al crear la carpeta")
    } finally {
      setIsCreating(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !isCreating && folderName.trim()) {
      handleCreate()
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FolderPlus className="h-5 w-5" />
            Nueva carpeta
          </DialogTitle>
          <DialogDescription>
            {parentFolder && parentFolder !== '/' && parentFolder !== '/Sin Clasificar'
              ? `Crear carpeta dentro de "${parentFolder.split('/').pop()}"`
              : "Crear una nueva carpeta para organizar tus documentos"
            }
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="folder-name">Nombre de la carpeta</Label>
            <Input
              id="folder-name"
              placeholder="Mi carpeta"
              value={folderName}
              onChange={(e) => setFolderName(e.target.value)}
              onKeyDown={handleKeyDown}
              autoFocus
            />
          </div>

          {parentFolder && parentFolder !== '/' && parentFolder !== '/Sin Clasificar' && (
            <p className="text-sm text-muted-foreground">
              Ubicación: {parentFolder}/{folderName || '...'}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button
            onClick={handleCreate}
            disabled={isCreating || !folderName.trim()}
          >
            {isCreating ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Creando...
              </>
            ) : (
              <>
                <FolderPlus className="mr-2 h-4 w-4" />
                Crear carpeta
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
