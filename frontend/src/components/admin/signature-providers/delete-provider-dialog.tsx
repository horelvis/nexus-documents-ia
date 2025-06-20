"use client"

import { useState } from "react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { 
  IconLoader2, 
  IconAlertTriangle,
  IconTrash
} from "@tabler/icons-react"
import { SignatureProvider } from "@/lib/services/signature-service"
import { useSignatureService } from "@/lib/services/signature-service.hooks"
import { useNotifications } from "@/contexts/notifications-context"

interface DeleteProviderDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  provider: SignatureProvider | null
  onSuccess: () => void
}

export function DeleteProviderDialog({
  open,
  onOpenChange,
  provider,
  onSuccess,
}: DeleteProviderDialogProps) {
  const { addNotification } = useNotifications()
  const signatureService = useSignatureService()
  const [isDeleting, setIsDeleting] = useState(false)

  const handleDelete = async () => {
    if (!provider) return

    setIsDeleting(true)
    try {
      await signatureService.deleteProvider(provider.id)
      
      addNotification({
        type: 'success',
        title: 'Provider deleted',
        message: `${provider.display_name} has been deleted successfully`
      })
      
      onSuccess()
      onOpenChange(false)
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: 'Failed to delete provider',
        message: error.message || 'An error occurred'
      })
    } finally {
      setIsDeleting(false)
    }
  }

  if (!provider) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete Signature Provider</DialogTitle>
          <DialogDescription>
            Are you sure you want to delete this signature provider?
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <Alert variant="destructive">
            <IconAlertTriangle className="h-4 w-4" />
            <AlertDescription>
              <strong>Warning:</strong> This action cannot be undone. 
              Deleting "{provider.display_name}" will:
              <ul className="list-disc list-inside mt-2 space-y-1">
                <li>Remove all stored credentials</li>
                <li>Prevent new signature requests with this provider</li>
                <li>Not affect existing signature requests</li>
              </ul>
            </AlertDescription>
          </Alert>

          <div className="rounded-lg border p-4">
            <div className="flex items-center gap-3">
              <div className="text-2xl">
                {provider.provider_name === 'docusign' && '📝'}
                {provider.provider_name === 'yousign' && '✍️'}
                {provider.provider_name === 'signaturit' && '🖊️'}
              </div>
              <div>
                <p className="font-medium">{provider.display_name}</p>
                <p className="text-sm text-muted-foreground">
                  Type: {provider.provider_name}
                </p>
              </div>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isDeleting}
          >
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={handleDelete}
            disabled={isDeleting}
          >
            {isDeleting ? (
              <>
                <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                Deleting...
              </>
            ) : (
              <>
                <IconTrash className="mr-2 h-4 w-4" />
                Delete Provider
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}