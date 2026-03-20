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
} from '@/components/ui'
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

/**
 * Estimate indexing time based on document count and historical average.
 * Falls back to 6 seconds per document if no historical data available.
 */
function formatEstimatedTime(docCount: number, avgSecondsPerDoc: number | null): string {
  // Use historical average if available, otherwise fall back to conservative estimate
  const secondsPerDoc = avgSecondsPerDoc && avgSecondsPerDoc > 0 ? avgSecondsPerDoc : 6
  const totalSeconds = Math.round(docCount * secondsPerDoc)

  if (totalSeconds < 60) {
    return `${totalSeconds} segundos`
  } else if (totalSeconds < 3600) {
    const minutes = Math.ceil(totalSeconds / 60)
    return `${minutes} minuto${minutes > 1 ? 's' : ''}`
  } else {
    const hours = Math.floor(totalSeconds / 3600)
    const minutes = Math.ceil((totalSeconds % 3600) / 60)
    if (minutes === 0) {
      return `${hours} hora${hours > 1 ? 's' : ''}`
    }
    return `${hours}h ${minutes}m`
  }
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
  // Historical average indexing time per document (from backend stats)
  const [avgIndexingSeconds, setAvgIndexingSeconds] = useState<number | null>(null)

  useEffect(() => {
    if (open && connector) {
      setCurrentConnector(connector)
      setError(null)
      setSuccessMessage(null)
      loadPendingDocuments()
      loadConnectorStats()
    }
  }, [open, connector])

  // Auto-refresh every 10 seconds while dialog is open (silent - no loaders)
  useEffect(() => {
    if (!open || !connector) return

    const interval = setInterval(() => {
      silentRefresh()
    }, 10000) // 10 seconds

    return () => clearInterval(interval)
  }, [open, connector])

  useEffect(() => {
    if (successMessage) {
      const timer = setTimeout(() => setSuccessMessage(null), 5000)
      return () => clearTimeout(timer)
    }
  }, [successMessage])

  const loadPendingDocuments = async (silent = false) => {
    if (!connector) return
    if (!silent) setIsLoadingPending(true)
    try {
      const result = await connectorService.getPendingDocuments(connector.id, 1, 5)
      if (result.data) {
        setPendingDocs(result.data.items)
        setPendingTotal(result.data.total)
      }
    } catch (err) {
      console.error('Failed to load pending documents:', err)
    } finally {
      if (!silent) setIsLoadingPending(false)
    }
  }

  // Silent refresh - updates values without showing loaders (for auto-refresh)
  const silentRefresh = async () => {
    if (!connector) return
    try {
      // Fetch all data in parallel
      const [connectorResult, statsResult, pendingResult] = await Promise.all([
        connectorService.getConnector(connector.id),
        connectorService.getConnectorStats(connector.id),
        connectorService.getPendingDocuments(connector.id, 1, 5),
      ])

      // Update state only if we got valid data
      if (connectorResult.data) {
        setCurrentConnector(connectorResult.data)
      }
      if (statsResult.data?.documents?.avg_indexing_seconds) {
        setAvgIndexingSeconds(statsResult.data.documents.avg_indexing_seconds)
      }
      if (pendingResult.data) {
        setPendingDocs(pendingResult.data.items)
        setPendingTotal(pendingResult.data.total)
      }
    } catch (err) {
      // Silent fail - don't show errors on auto-refresh
      console.error('Silent refresh failed:', err)
    }
  }

  const loadConnectorStats = async () => {
    if (!connector) return
    try {
      const result = await connectorService.getConnectorStats(connector.id)
      if (result.data?.documents?.avg_indexing_seconds) {
        setAvgIndexingSeconds(result.data.documents.avg_indexing_seconds)
      }
    } catch (err) {
      console.error('Failed to load connector stats:', err)
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
        setSuccessMessage(result.data.message + ' Iniciando indexación...')
        // Auto-index after sync
        const indexResult = await connectorService.indexPending(connector.id, 10)
        if (indexResult.error) {
          setError(indexResult.error)
        } else if (indexResult.data) {
          setSuccessMessage(`Sincronización e indexación iniciadas (${indexResult.data.pending_count} docs en cola)`)
        }
        setTimeout(() => {
          refreshConnectorData()
          loadPendingDocuments()
          onSyncComplete?.()
        }, 3000)
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
        setSuccessMessage(`Indexación iniciada (${result.data.pending_count} docs en cola). Los totales se actualizan automáticamente.`)
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
      <DialogContent className="sm:max-w-[500px] max-h-[90vh] overflow-y-auto overflow-x-hidden">
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
          {/* Message area */}
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

          {/* Statistics - fixed grid */}
          <div className="grid grid-cols-4 gap-2">
            <div className="text-center p-2 rounded border bg-muted/30">
              <div className="text-xl font-bold">{totalDocs}</div>
              <div className="text-[10px] text-muted-foreground">Total</div>
            </div>
            <div className="text-center p-2 rounded border bg-muted/30">
              <div className={`text-xl font-bold ${pendingCount > 0 ? 'text-yellow-600' : ''}`}>{pendingCount}</div>
              <div className="text-[10px] text-muted-foreground">Pendientes</div>
            </div>
            <div className="text-center p-2 rounded border bg-muted/30">
              <div className="text-xl font-bold text-green-600">{indexedCount}</div>
              <div className="text-[10px] text-muted-foreground">Indexados</div>
            </div>
            <div className="text-center p-2 rounded border bg-muted/30">
              <div className={`text-xl font-bold ${failedCount > 0 ? 'text-red-600' : ''}`}>{failedCount}</div>
              <div className="text-[10px] text-muted-foreground">Fallidos</div>
            </div>
          </div>

          {/* Progress / Active operation indicator */}
          {isSyncing || isIndexing ? (
            // Show loader during active operations with time estimate
            <div className="flex flex-col items-center justify-center gap-2 py-3 rounded border bg-blue-50/50 dark:bg-blue-950/20 border-blue-200 dark:border-blue-800">
              <div className="flex items-center gap-3">
                <IconLoader2 className="h-5 w-5 animate-spin text-blue-500" />
                <span className="text-sm text-blue-600 dark:text-blue-400">
                  {isSyncing ? 'Sincronizando con el origen...' : 'Indexando documentos...'}
                </span>
              </div>
              {isIndexing && pendingCount > 0 && (
                <span className="text-xs text-muted-foreground">
                  Tiempo estimado: ~{formatEstimatedTime(pendingCount, avgIndexingSeconds)}
                </span>
              )}
            </div>
          ) : (
            // Show progress when idle (auto-refreshes every 10s)
            <div className="space-y-1">
              <div className="flex justify-between text-xs">
                <span className="text-muted-foreground flex items-center gap-1">
                  Documentos indexados
                  {pendingCount > 0 && (
                    <span className="inline-flex items-center gap-1 text-[10px] text-blue-500">
                      <IconLoader2 className="h-2.5 w-2.5 animate-spin" />
                      auto
                    </span>
                  )}
                </span>
                <span>{indexedCount} / {totalDocs}</span>
              </div>
              <Progress value={progressPercent} className="h-1.5" />
              {pendingCount > 0 && (
                <div className="text-xs text-muted-foreground text-right">
                  Pendientes: {pendingCount} (~{formatEstimatedTime(pendingCount, avgIndexingSeconds)})
                  {avgIndexingSeconds && <span className="ml-1 text-[10px] opacity-70">({avgIndexingSeconds.toFixed(1)}s/doc)</span>}
                </div>
              )}
            </div>
          )}

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
