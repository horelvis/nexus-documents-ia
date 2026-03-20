'use client'

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui'
import { GoogleDriveOAuthStep } from './GoogleDriveOAuthStep'
import { Connector, connectorNames } from '@/lib/services/connector.service'

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
            Vuelve a autorizar la conexión con {connectorNames[connector.connector_type]}
          </DialogDescription>
        </DialogHeader>
        <GoogleDriveOAuthStep
          connectorId={connector.id}
          connectorName={connector.name}
          connectorType={connector.connector_type}
          onComplete={handleComplete}
        />
      </DialogContent>
    </Dialog>
  )
}
