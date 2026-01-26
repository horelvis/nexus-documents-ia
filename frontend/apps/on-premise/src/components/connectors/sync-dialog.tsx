'use client'

/**
 * Sync Dialog for Emma On-Premise
 *
 * Shows sync status and allows triggering sync/index operations with feedback.
 */

import { useState, useEffect } from 'react'
import {
  IconCloudDownload,
  IconLoader2,
  IconAlertCircle,
  IconCheck,
  IconFileText,
  IconClock,
  IconDatabase,
  IconRefresh,
  IconPlayerPlay,
} from '@tabler/icons-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  Badge,
  Button,
  Separator,
  Progress,
} from '@nexus/shared/ui'
import {
  Connector,
  PendingDocument,
  connectorService,
  connectorNames,
} from '@/lib/services/connector.service'

interface SyncDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  connector: Connector | null
  onSyncComplete?: () => void
}

export function SyncDialog({
  open,
  onOpenChange,
  connector,
  onSyncComplete,
}: SyncDialogProps) {
  const [isSyncing, setIsSyncing] = useState(false)
  const [isIndexing, setIsIndexing] = useState(false)
  const [isLoadingPending, setIsLoadingPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  const [pendingDocs, setPendingDocs] = useState<PendingDocument[]>([])
  const [pendingTotal, setPendingTotal] = useState(0)
  const [currentConnector, setCurrentConnector] = useState<Connector | null>(null)

  useEffect(() => {
    if (open && connector) {
      setCurrentConnector(connector)
      setError(null)
      setSuccessMessage(null)
      loadPendingDocuments()
    }
  }, [open, connector])

  useEffect(() => {
    if (successMessage) {
      const timer = setTimeout(() => setSuccessMessage(null), 5000)
      return () => clearTimeout(timer)
    }
  }, [successMessage])

  const loadPendingDocuments = async () => {
    if (!connector) return
    setIsLoadingPending(true)
    try {
      const result = await connectorService.getPendingDocuments(connector.id, 1, 5)
      if (result.data) {
        setPendingDocs(result.data.items)
        setPendingTotal(result.data.total)
      }
    } catch (err) {
      console.error('Failed to load pending documents:', err)
    } finally {
      setIsLoadingPending(false)
    }
  }

  const refreshConnectorData = async () => {
    if (!connector) return
    try {
      const result = await connectorService.getConnector(connector.id)
      if (result.data) {
        setCurrentConnector(result.data)
      }
    } catch (err) {
      console.error('Failed to refresh connector:', err)
    }
  }

  const handleSync = async (fullSync = false) => {
    if (!connector) return
    setIsSyncing(true)
    setError(null)
    setSuccessMessage(null)

    try {
      const result = await connectorService.syncConnector(connector.id, fullSync)
      if (result.error) {
        setError(result.error)
      } else if (result.data) {
        setSuccessMessage(result.data.message)
        setTimeout(() => {
          refreshConnectorData()
          loadPendingDocuments()
          onSyncComplete?.()
        }, 2000)
      }
    } catch (err: any) {
      setError(err.message || 'Error al sincronizar')
    } finally {
      setIsSyncing(false)
    }
  }

  const handleIndex = async () => {
    if (!connector) return
    setIsIndexing(true)
    setError(null)
    setSuccessMessage(null)

    try {
      const result = await connectorService.indexPending(connector.id, 10)
      if (result.error) {
        setError(result.error)
      } else if (result.data) {
        setSuccessMessage(`Indexando ${result.data.pending_count} documentos...`)
        setTimeout(() => {
          refreshConnectorData()
          loadPendingDocuments()
          onSyncComplete?.()
        }, 3000)
      }
    } catch (err: any) {
      setError(err.message || 'Error al indexar')
    } finally {
      setIsIndexing(false)
    }
  }

  if (!connector) return null

  const stats = currentConnector || connector
  const totalDocs = stats.documents_total || 0
  const pendingCount = stats.documents_pending || 0
  const indexedCount = stats.documents_indexed || 0
  const failedCount = stats.documents_failed || 0
  const progressPercent = totalDocs > 0 ? Math.round((indexedCount / totalDocs) * 100) : 0

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="overflow-y-auto"
        style={{ width: '500px', maxWidth: '500px', maxHeight: '90vh' }}
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <IconCloudDownload className="h-5 w-5" />
            Sincronización
          </DialogTitle>
          <DialogDescription>
            {connector.name} ({connectorNames[connector.connector_type]})
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Message area - fixed height */}
          <div className="h-10">
            {error && (
              <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 dark:bg-red-950/30 px-3 py-2 rounded">
                <IconAlertCircle className="h-4 w-4 flex-shrink-0" />
                <span className="truncate">{error}</span>
              </div>
            )}
            {successMessage && !error && (
              <div className="flex items-center gap-2 text-sm text-green-600 bg-green-50 dark:bg-green-950/30 px-3 py-2 rounded">
                <IconCheck className="h-4 w-4 flex-shrink-0" />
                <span className="truncate">{successMessage}</span>
              </div>
            )}
          </div>

          {/* Statistics - fixed grid */}
          <div className="grid grid-cols-4 gap-2">
            <div className="text-center p-2 rounded border bg-muted/30">
              <div className="text-xl font-bold">{totalDocs}</div>
              <div className="text-[10px] text-muted-foreground">Total</div>
            </div>
            <div className={`text-center p-2 rounded border ${pendingCount > 0 ? 'border-yellow-500/50 bg-yellow-50/50 dark:bg-yellow-950/20' : 'bg-muted/30'}`}>
              <div className={`text-xl font-bold ${pendingCount > 0 ? 'text-yellow-600' : ''}`}>{pendingCount}</div>
              <div className="text-[10px] text-muted-foreground">Pendientes</div>
            </div>
            <div className="text-center p-2 rounded border border-green-500/50 bg-green-50/50 dark:bg-green-950/20">
              <div className="text-xl font-bold text-green-600">{indexedCount}</div>
              <div className="text-[10px] text-muted-foreground">Indexados</div>
            </div>
            <div className={`text-center p-2 rounded border ${failedCount > 0 ? 'border-red-500/50 bg-red-50/50 dark:bg-red-950/20' : 'bg-muted/30'}`}>
              <div className={`text-xl font-bold ${failedCount > 0 ? 'text-red-600' : ''}`}>{failedCount}</div>
              <div className="text-[10px] text-muted-foreground">Fallidos</div>
            </div>
          </div>

          {/* Progress */}
          <div className="space-y-1">
            <div className="flex justify-between text-xs">
              <span className="text-muted-foreground">Progreso</span>
              <span>{progressPercent}%</span>
            </div>
            <Progress value={progressPercent} className="h-1.5" />
          </div>

          <Separator />

          {/* Actions */}
          <div className="space-y-3">
            {/* Sync */}
            <div className="flex items-center justify-between gap-3 p-3 rounded border bg-muted/20">
              <div className="flex items-center gap-2 min-w-0">
                <IconCloudDownload className="h-4 w-4 text-blue-500 flex-shrink-0" />
                <span className="text-sm font-medium truncate">Sincronizar origen</span>
              </div>
              <div className="flex gap-1.5 flex-shrink-0">
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 px-2 text-xs"
                  onClick={() => handleSync(false)}
                  disabled={isSyncing || isIndexing || !connector.sync_enabled}
                >
                  {isSyncing ? <IconLoader2 className="h-3 w-3 animate-spin" /> : 'Parcial'}
                </Button>
                <Button
                  size="sm"
                  className="h-7 px-2 text-xs"
                  onClick={() => handleSync(true)}
                  disabled={isSyncing || isIndexing || !connector.sync_enabled}
                >
                  {isSyncing ? <IconLoader2 className="h-3 w-3 animate-spin" /> : 'Completa'}
                </Button>
              </div>
            </div>

            {/* Index */}
            <div className="flex items-center justify-between gap-3 p-3 rounded border bg-muted/20">
              <div className="flex items-center gap-2 min-w-0">
                <IconDatabase className="h-4 w-4 text-purple-500 flex-shrink-0" />
                <span className="text-sm font-medium truncate">
                  Indexar pendientes
                  {pendingCount > 0 && <Badge variant="secondary" className="ml-2 text-[10px] px-1.5">{pendingCount}</Badge>}
                </span>
              </div>
              <Button
                size="sm"
                className="h-7 px-3 text-xs flex-shrink-0"
                onClick={handleIndex}
                disabled={isIndexing || isSyncing || pendingCount === 0}
              >
                {isIndexing ? <IconLoader2 className="h-3 w-3 animate-spin" /> : <><IconPlayerPlay className="h-3 w-3 mr-1" />Indexar</>}
              </Button>
            </div>
          </div>

          {/* Pending docs preview - fixed height container */}
          <div className="h-[100px] overflow-y-auto rounded border bg-muted/10 p-2">
            {isLoadingPending ? (
              <div className="flex items-center justify-center h-full">
                <IconLoader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              </div>
            ) : pendingDocs.length > 0 ? (
              <div className="space-y-1.5">
                {pendingDocs.map((doc) => (
                  <div key={doc.id} className="flex items-center gap-2 text-xs">
                    <IconFileText className="h-3 w-3 text-muted-foreground flex-shrink-0" />
                    <span className="truncate flex-1">{doc.title}</span>
                    <Badge variant="outline" className="text-[10px] px-1 flex-shrink-0">
                      {doc.mime_type?.split('/')[1] || 'file'}
                    </Badge>
                  </div>
                ))}
                {pendingTotal > 5 && (
                  <div className="text-[10px] text-muted-foreground text-center pt-1">
                    +{pendingTotal - 5} más
                  </div>
                )}
              </div>
            ) : (
              <div className="flex items-center justify-center h-full text-xs text-muted-foreground">
                No hay documentos pendientes
              </div>
            )}
          </div>

          {/* Footer info */}
          <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
            <IconClock className="h-3 w-3" />
            <span>
              Auto-sync: {connector.sync_enabled ? `cada ${connector.sync_interval_hours}h` : 'off'}
            </span>
          </div>
        </div>

        <DialogFooter className="gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => { refreshConnectorData(); loadPendingDocuments() }}
            disabled={isLoadingPending}
          >
            <IconRefresh className={`h-4 w-4 ${isLoadingPending ? 'animate-spin' : ''}`} />
          </Button>
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            Cerrar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
