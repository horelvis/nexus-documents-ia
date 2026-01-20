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
import { IconLoader2, IconTrash, IconAlertTriangle } from "@tabler/icons-react"
import { Document } from "@/lib/types"
import { Progress } from "@/components/ui/progress"

interface DeleteMultipleDocumentsDialogProps {
  documents: Document[]
  open: boolean
  onOpenChange: (open: boolean) => void
  onConfirm: (id: string) => Promise<void>
  onComplete?: () => void
}

export function DeleteMultipleDocumentsDialog({
  documents,
  open,
  onOpenChange,
  onConfirm,
  onComplete
}: DeleteMultipleDocumentsDialogProps) {
  const [isLoading, setIsLoading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [deletedCount, setDeletedCount] = useState(0)
  const [errors, setErrors] = useState<string[]>([])

  const handleConfirm = async () => {
    if (documents.length === 0) return

    setIsLoading(true)
    setProgress(0)
    setDeletedCount(0)
    setErrors([])

    const totalDocs = documents.length
    let successCount = 0
    const errorList: string[] = []

    // Delete documents sequentially to avoid overwhelming the server
    for (let i = 0; i < documents.length; i++) {
      const doc = documents[i]
      try {
        await onConfirm(doc.id)
        successCount++
        setDeletedCount(successCount)
      } catch (error) {
        const errorMsg = `${doc.title || doc.filename}: ${error instanceof Error ? error.message : 'Error desconocido'}`
        errorList.push(errorMsg)
      }
      setProgress(Math.round(((i + 1) / totalDocs) * 100))
    }

    setErrors(errorList)
    setIsLoading(false)

    // If all successful, close dialog and notify completion
    if (errorList.length === 0) {
      onOpenChange(false)
      onComplete?.()
    }
  }

  const handleClose = () => {
    if (!isLoading) {
      setProgress(0)
      setDeletedCount(0)
      setErrors([])
      onOpenChange(false)
      if (deletedCount > 0) {
        onComplete?.()
      }
    }
  }

  if (documents.length === 0) return null

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-red-100">
              <IconAlertTriangle className="h-5 w-5 text-red-600" />
            </div>
            <div>
              <DialogTitle>Eliminar {documents.length} documentos</DialogTitle>
              <DialogDescription>
                Esta acción no se puede deshacer.
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="py-4 space-y-4">
          {!isLoading && errors.length === 0 && (
            <>
              <p className="text-sm text-muted-foreground">
                ¿Estás seguro de que deseas eliminar los siguientes documentos?
                Se eliminarán permanentemente junto con todos sus datos asociados.
              </p>
              <div className="max-h-40 overflow-y-auto border rounded-md p-2 bg-muted/50">
                <ul className="text-sm space-y-1">
                  {documents.map((doc) => (
                    <li key={doc.id} className="truncate">
                      • {doc.title || doc.filename}
                    </li>
                  ))}
                </ul>
              </div>
            </>
          )}

          {isLoading && (
            <div className="space-y-3">
              <div className="flex items-center justify-between text-sm">
                <span>Eliminando documentos...</span>
                <span>{deletedCount} / {documents.length}</span>
              </div>
              <Progress value={progress} className="h-2" />
            </div>
          )}

          {errors.length > 0 && (
            <div className="space-y-2">
              <p className="text-sm text-green-600">
                ✓ {deletedCount} documentos eliminados correctamente
              </p>
              <p className="text-sm text-red-600">
                ✗ {errors.length} errores:
              </p>
              <div className="max-h-32 overflow-y-auto border border-red-200 rounded-md p-2 bg-red-50">
                <ul className="text-xs text-red-700 space-y-1">
                  {errors.map((error, idx) => (
                    <li key={idx}>• {error}</li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </div>

        <DialogFooter>
          {errors.length === 0 ? (
            <>
              <Button variant="outline" onClick={handleClose} disabled={isLoading}>
                Cancelar
              </Button>
              <Button variant="destructive" onClick={handleConfirm} disabled={isLoading}>
                {isLoading ? (
                  <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <IconTrash className="mr-2 h-4 w-4" />
                )}
                {isLoading ? 'Eliminando...' : `Eliminar ${documents.length} documentos`}
              </Button>
            </>
          ) : (
            <Button variant="outline" onClick={handleClose}>
              Cerrar
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
