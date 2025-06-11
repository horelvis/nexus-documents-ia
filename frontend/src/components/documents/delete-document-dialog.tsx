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

interface DeleteDocumentDialogProps {
  document: Document | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onConfirm: (id: string) => Promise<void>
}

export function DeleteDocumentDialog({ document, open, onOpenChange, onConfirm }: DeleteDocumentDialogProps) {
  const [isLoading, setIsLoading] = useState(false)

  const handleConfirm = async () => {
    if (!document) return

    setIsLoading(true)
    try {
      await onConfirm(document.id)
      onOpenChange(false)
    } catch (error) {
      console.error('Failed to delete document:', error)
    } finally {
      setIsLoading(false)
    }
  }

  if (!document) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-red-100">
              <IconAlertTriangle className="h-5 w-5 text-red-600" />
            </div>
            <div>
              <DialogTitle>Delete Document</DialogTitle>
              <DialogDescription>
                This action cannot be undone.
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>
        
        <div className="py-4">
          <p className="text-sm text-muted-foreground">
            Are you sure you want to delete <strong>&quot;{document.title || document.filename}&quot;</strong>?
            This will permanently remove the document and all its associated data.
          </p>
        </div>
        
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isLoading}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={handleConfirm} disabled={isLoading}>
            {isLoading && <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />}
            <IconTrash className="mr-2 h-4 w-4" />
            Delete Document
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}