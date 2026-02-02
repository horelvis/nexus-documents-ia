'use client'

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@nexus/shared/ui'
import { GoogleDriveOAuthStep } from './GoogleDriveOAuthStep'
import { Connector } from '@/lib/services/connector.service'

interface ReconnectOAuthDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  connector: Connector | null
  onComplete: () => void
}

export function ReconnectOAuthDialog({
  open,
  onOpenChange,
  connector,
  onComplete,
}: ReconnectOAuthDialogProps) {
  if (!connector) return null

  const handleComplete = () => {
    onOpenChange(false)
    onComplete()
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Reconectar {connector.name}</DialogTitle>
          <DialogDescription>
            Vuelve a autorizar la conexión con Google Drive
          </DialogDescription>
        </DialogHeader>
        <GoogleDriveOAuthStep
          connectorId={connector.id}
          connectorName={connector.name}
          onComplete={handleComplete}
        />
      </DialogContent>
    </Dialog>
  )
}
