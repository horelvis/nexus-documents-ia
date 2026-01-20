"use client"

import { useState, useEffect } from "react"
import {
  IconChartBar,
  IconLoader2,
  IconUsers,
  IconFiles,
  IconDatabase,
  IconAlertCircle,
  IconClock,
  IconCheck,
  IconX,
  IconHourglass,
} from "@tabler/icons-react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { Alert, AlertDescription } from "@/components/ui/alert"
import {
  Connector,
  ConnectorStats,
  CONNECTOR_TYPE_INFO,
  useConnectorService,
} from "@/lib/services/connector.service"

interface ConnectorStatsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  connector: Connector | null
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B"
  const k = 1024
  const sizes = ["B", "KB", "MB", "GB", "TB"]
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i]
}

export function ConnectorStatsDialog({
  open,
  onOpenChange,
  connector,
}: ConnectorStatsDialogProps) {
  const connectorService = useConnectorService()

  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [stats, setStats] = useState<ConnectorStats | null>(null)

  useEffect(() => {
    if (open && connector) {
      loadStats()
    }
  }, [open, connector])

  const loadStats = async () => {
    if (!connector) return

    setIsLoading(true)
    setError(null)

    try {
      const data = await connectorService.getStats(connector.id)
      setStats(data)
    } catch (error: any) {
      setError(error.message || "Failed to load statistics")
    } finally {
      setIsLoading(false)
    }
  }

  if (!connector) return null

  const typeInfo = CONNECTOR_TYPE_INFO[connector.connector_type]

  // Use real document stats (from IndexedDocument table)
  const docStats = stats?.documents
  const indexingProgress = docStats?.total
    ? Math.round((docStats.indexed / docStats.total) * 100)
    : 0

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <IconChartBar className="h-5 w-5" />
            Connector Statistics
          </DialogTitle>
          <DialogDescription>
            {connector.name} ({typeInfo?.name || connector.connector_type})
          </DialogDescription>
        </DialogHeader>

        <div className="py-4">
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <IconLoader2 className="h-6 w-6 animate-spin" />
              <span className="ml-2">Loading statistics...</span>
            </div>
          ) : error ? (
            <Alert variant="destructive">
              <IconAlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : stats ? (
            <div className="space-y-4">
              {/* User Stats */}
              <div className="grid grid-cols-2 gap-4">
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium flex items-center gap-2">
                      <IconUsers className="h-4 w-4 text-muted-foreground" />
                      User Authorizations
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold">
                      {stats.authorizations.valid}
                      <span className="text-sm font-normal text-muted-foreground">
                        {" "}
                        / {stats.authorizations.total}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground">Valid authorizations</p>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium flex items-center gap-2">
                      <IconUsers className="h-4 w-4 text-muted-foreground" />
                      Active Syncs
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold">
                      {stats.syncs.users_enabled}
                      <span className="text-sm font-normal text-muted-foreground">
                        {" "}
                        / {stats.syncs.total_users}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground">Users with sync enabled</p>
                  </CardContent>
                </Card>
              </div>

              {/* Document Stats - Real data from IndexedDocument table */}
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium flex items-center gap-2">
                    <IconFiles className="h-4 w-4 text-muted-foreground" />
                    Document Processing Status
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex justify-between text-sm">
                    <span>Indexing Progress</span>
                    <span className="font-medium">{indexingProgress}%</span>
                  </div>
                  <Progress value={indexingProgress} className="h-2" />

                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 pt-2">
                    <div className="text-center p-3 bg-muted/50 rounded-lg">
                      <div className="flex items-center justify-center gap-1 mb-1">
                        <IconClock className="h-4 w-4 text-yellow-600" />
                      </div>
                      <div className="text-xl font-bold text-yellow-600">
                        {docStats?.pending || 0}
                      </div>
                      <p className="text-xs text-muted-foreground">Pending</p>
                    </div>
                    <div className="text-center p-3 bg-muted/50 rounded-lg">
                      <div className="flex items-center justify-center gap-1 mb-1">
                        <IconHourglass className="h-4 w-4 text-blue-600" />
                      </div>
                      <div className="text-xl font-bold text-blue-600">
                        {docStats?.processing || 0}
                      </div>
                      <p className="text-xs text-muted-foreground">Processing</p>
                    </div>
                    <div className="text-center p-3 bg-muted/50 rounded-lg">
                      <div className="flex items-center justify-center gap-1 mb-1">
                        <IconCheck className="h-4 w-4 text-green-600" />
                      </div>
                      <div className="text-xl font-bold text-green-600">
                        {docStats?.indexed || 0}
                      </div>
                      <p className="text-xs text-muted-foreground">Indexed</p>
                    </div>
                    <div className="text-center p-3 bg-muted/50 rounded-lg">
                      <div className="flex items-center justify-center gap-1 mb-1">
                        <IconX className="h-4 w-4 text-red-600" />
                      </div>
                      <div className="text-xl font-bold text-red-600">
                        {docStats?.failed || 0}
                      </div>
                      <p className="text-xs text-muted-foreground">Failed</p>
                    </div>
                  </div>

                  <div className="text-xs text-muted-foreground pt-2 border-t">
                    Total: {docStats?.total || 0} documents
                    {docStats?.last_indexed_at && (
                      <span className="ml-2">
                        • Last indexed: {new Date(docStats.last_indexed_at).toLocaleString()}
                      </span>
                    )}
                  </div>
                </CardContent>
              </Card>

              {/* Storage Stats */}
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium flex items-center gap-2">
                    <IconDatabase className="h-4 w-4 text-muted-foreground" />
                    Storage
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">
                    {formatBytes(docStats?.total_size_bytes || 0)}
                  </div>
                  <p className="text-xs text-muted-foreground">Total synced content size</p>
                </CardContent>
              </Card>
            </div>
          ) : null}
        </div>
      </DialogContent>
    </Dialog>
  )
}
