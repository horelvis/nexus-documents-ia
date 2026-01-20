"use client"

import { useState } from "react"
import { IconAlertTriangle, IconLoader2, IconTrash } from "@tabler/icons-react"
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Alert, AlertDescription } from "@/components/ui/alert"
import {
  Connector,
  CONNECTOR_TYPE_INFO,
  useConnectorService,
} from "@/lib/services/connector.service"
import { useNotifications } from "@/contexts/app-state-context"

interface DeleteConnectorDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  connector: Connector | null
  onSuccess: () => void
}

export function DeleteConnectorDialog({
  open,
  onOpenChange,
  connector,
  onSuccess,
}: DeleteConnectorDialogProps) {
  const connectorService = useConnectorService()
  const { addNotification } = useNotifications()

  const [isLoading, setIsLoading] = useState(false)
  const [confirmName, setConfirmName] = useState("")

  const handleDelete = async () => {
    if (!connector) return

    setIsLoading(true)

    try {
      await connectorService.deleteConnector(connector.id)

      addNotification({
        type: "success",
        title: "Connector deleted",
        message: `${connector.name} has been deleted successfully`,
      })

      onOpenChange(false)
      setConfirmName("")
      onSuccess()
    } catch (error: any) {
      addNotification({
        type: "error",
        title: "Failed to delete connector",
        message: error.message || "An error occurred",
      })
    } finally {
      setIsLoading(false)
    }
  }

  const handleOpenChange = (open: boolean) => {
    if (!open) {
      setConfirmName("")
    }
    onOpenChange(open)
  }

  if (!connector) return null

  const typeInfo = CONNECTOR_TYPE_INFO[connector.connector_type]
  const canDelete = confirmName === connector.name

  return (
    <AlertDialog open={open} onOpenChange={handleOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2 text-destructive">
            <IconTrash className="h-5 w-5" />
            Delete Connector
          </AlertDialogTitle>
          <AlertDialogDescription>
            Are you sure you want to delete this connector? This action cannot be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>

        <div className="space-y-4 py-4">
          {/* Connector info */}
          <div className="rounded-lg border p-4 bg-muted/50">
            <div className="font-medium">{connector.name}</div>
            <div className="text-sm text-muted-foreground">
              {typeInfo?.name || connector.connector_type}
            </div>
            {connector.users_connected > 0 && (
              <div className="text-sm text-muted-foreground mt-1">
                {connector.users_connected} users connected
              </div>
            )}
          </div>

          {/* Warning */}
          <Alert variant="destructive">
            <IconAlertTriangle className="h-4 w-4" />
            <AlertDescription>
              <strong>Warning:</strong> This will:
              <ul className="list-disc list-inside mt-2 space-y-1">
                <li>Remove the connector configuration</li>
                <li>Revoke all user authorizations ({connector.users_connected} users)</li>
                <li>Stop all active document syncs</li>
                <li>Orphan indexed documents (they will remain but lose sync)</li>
              </ul>
            </AlertDescription>
          </Alert>

          {/* Confirm name */}
          <div className="space-y-2">
            <Label htmlFor="confirm-name">
              Type <strong>{connector.name}</strong> to confirm
            </Label>
            <Input
              id="confirm-name"
              value={confirmName}
              onChange={(e) => setConfirmName(e.target.value)}
              placeholder="Enter connector name"
            />
          </div>
        </div>

        <AlertDialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)} disabled={isLoading}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={handleDelete}
            disabled={isLoading || !canDelete}
          >
            {isLoading ? (
              <>
                <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                Deleting...
              </>
            ) : (
              <>
                <IconTrash className="mr-2 h-4 w-4" />
                Delete Connector
              </>
            )}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
