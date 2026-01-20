"use client"

import { useState, useEffect } from "react"
import { useParams } from "next/navigation"
import {
  IconPlus,
  IconEdit,
  IconTrash,
  IconLoader2,
  IconSettings,
  IconAlertCircle,
  IconTestPipe,
  IconShieldLock,
  IconPlugConnected,
  IconRefresh,
  IconChartBar,
  IconRefreshDot,
  IconReload,
} from "@tabler/icons-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { Switch } from "@/components/ui/switch"
import { Alert, AlertDescription } from "@/components/ui/alert"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Connector,
  ConnectorType,
  ConnectorHealthStatus,
  CONNECTOR_TYPE_INFO,
  useConnectorService,
} from "@/lib/services/connector.service"
import { useNotifications } from "@/contexts/app-state-context"
import { ConnectorDialog } from "@/components/admin/connectors/connector-dialog"
import { DeleteConnectorDialog } from "@/components/admin/connectors/delete-connector-dialog"
import { ConnectorStatsDialog } from "@/components/admin/connectors/connector-stats-dialog"

export default function ConnectorsPage() {
  const params = useParams()
  const tenantId = params.tenantId as string
  const { addNotification } = useNotifications()
  const connectorService = useConnectorService()

  const [connectors, setConnectors] = useState<Connector[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Dialog states
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const [editDialogOpen, setEditDialogOpen] = useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [statsDialogOpen, setStatsDialogOpen] = useState(false)
  const [selectedConnector, setSelectedConnector] = useState<Connector | null>(null)

  // Test states
  const [testingConnector, setTestingConnector] = useState<string | null>(null)

  // Sync states
  const [syncingConnector, setSyncingConnector] = useState<string | null>(null)

  useEffect(() => {
    loadConnectors()
  }, [])

  const loadConnectors = async () => {
    setIsLoading(true)
    setError(null)

    try {
      const response = await connectorService.getConnectors()
      setConnectors(response.items)
    } catch (error: any) {
      setError(error.message || 'Failed to load connectors')
      addNotification({
        type: 'error',
        title: 'Failed to load connectors',
        message: error.message || 'An error occurred',
      })
    } finally {
      setIsLoading(false)
    }
  }

  const handleCreateConnector = () => {
    setSelectedConnector(null)
    setCreateDialogOpen(true)
  }

  const handleEditConnector = (connector: Connector) => {
    setSelectedConnector(connector)
    setEditDialogOpen(true)
  }

  const handleDeleteConnector = (connector: Connector) => {
    setSelectedConnector(connector)
    setDeleteDialogOpen(true)
  }

  const handleViewStats = (connector: Connector) => {
    setSelectedConnector(connector)
    setStatsDialogOpen(true)
  }

  const handleToggleActive = async (connector: Connector) => {
    try {
      await connectorService.updateConnector(connector.id, {
        is_active: !connector.is_active,
      })

      addNotification({
        type: 'success',
        title: 'Connector updated',
        message: `${connector.name} has been ${!connector.is_active ? 'activated' : 'deactivated'}`,
      })

      await loadConnectors()
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: 'Failed to update connector',
        message: error.message || 'An error occurred',
      })
    }
  }

  const handleTestConnector = async (connector: Connector) => {
    setTestingConnector(connector.id)

    try {
      const result = await connectorService.checkHealth(connector.id)

      addNotification({
        type: result.status === ConnectorHealthStatus.HEALTHY ? 'success' : 'warning',
        title: result.status === ConnectorHealthStatus.HEALTHY ? 'Test successful' : 'Test completed',
        message: result.message,
      })

      await loadConnectors()
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: 'Test failed',
        message: error.message || 'Could not test connector',
      })
    } finally {
      setTestingConnector(null)
    }
  }

  const handleSyncConnector = async (connector: Connector, fullSync: boolean = false) => {
    setSyncingConnector(connector.id)

    try {
      const result = await connectorService.triggerSync(connector.id, fullSync)

      addNotification({
        type: 'success',
        title: 'Sync started',
        message: result.message,
      })
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: 'Sync failed',
        message: error.message || 'Could not start sync',
      })
    } finally {
      setSyncingConnector(null)
    }
  }

  const getConnectorIcon = (connectorType: ConnectorType) => {
    const icons: Record<ConnectorType, string> = {
      [ConnectorType.SHAREPOINT]: '📁',
      [ConnectorType.ONEDRIVE]: '☁️',
      [ConnectorType.GOOGLE_DRIVE]: '📂',
      [ConnectorType.GOOGLE_WORKSPACE]: '🏢',
      [ConnectorType.DROPBOX]: '📦',
      [ConnectorType.BOX]: '📋',
      [ConnectorType.S3]: '🪣',
      [ConnectorType.AZURE_BLOB]: '💾',
      [ConnectorType.NETWORK_SHARE]: '🖥️',
      [ConnectorType.ALFRESCO]: '🗄️',
    }
    return icons[connectorType] || '📄'
  }

  const getHealthBadgeVariant = (status: ConnectorHealthStatus) => {
    switch (status) {
      case ConnectorHealthStatus.HEALTHY:
        return 'default'
      case ConnectorHealthStatus.DEGRADED:
        return 'secondary'
      case ConnectorHealthStatus.UNHEALTHY:
        return 'destructive'
      default:
        return 'outline'
    }
  }

  const getHealthStatusText = (status: ConnectorHealthStatus) => {
    switch (status) {
      case ConnectorHealthStatus.HEALTHY:
        return 'Healthy'
      case ConnectorHealthStatus.DEGRADED:
        return 'Degraded'
      case ConnectorHealthStatus.UNHEALTHY:
        return 'Unhealthy'
      default:
        return 'Unknown'
    }
  }

  return (
    <div className="container mx-auto p-6">
      <div className="mb-6">
        <h1 className="text-3xl font-bold">External Connectors</h1>
        <p className="text-muted-foreground">
          Manage connections to external document sources for your organization
        </p>
      </div>

      {/* Security Notice */}
      <Alert className="mb-6">
        <IconShieldLock className="h-4 w-4" />
        <AlertDescription>
          Connector credentials are encrypted and stored securely. Users can authorize their accounts to sync documents from these sources.
        </AlertDescription>
      </Alert>

      {/* Connectors List */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Configured Connectors</CardTitle>
              <CardDescription>
                Add and manage external data source integrations
              </CardDescription>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={loadConnectors} disabled={isLoading}>
                <IconRefresh className={`mr-2 h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
                Refresh
              </Button>
              <Button onClick={handleCreateConnector}>
                <IconPlus className="mr-2 h-4 w-4" />
                Add Connector
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <IconLoader2 className="h-6 w-6 animate-spin" />
              <span className="ml-2">Loading connectors...</span>
            </div>
          ) : error ? (
            <Alert variant="destructive">
              <IconAlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : connectors.length === 0 ? (
            <div className="text-center py-8">
              <IconPlugConnected className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
              <p className="text-muted-foreground mb-4">
                No connectors configured yet
              </p>
              <Button onClick={handleCreateConnector}>
                <IconPlus className="mr-2 h-4 w-4" />
                Add Your First Connector
              </Button>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Connector</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Health</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Documents</TableHead>
                  <TableHead>Sync</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {connectors.map((connector) => (
                  <TableRow key={connector.id}>
                    <TableCell className="font-medium">
                      <div className="flex items-center gap-2">
                        <span className="text-xl">{getConnectorIcon(connector.connector_type)}</span>
                        <div>
                          <span className="block">{connector.name}</span>
                          {connector.description && (
                            <span className="text-xs text-muted-foreground">{connector.description}</span>
                          )}
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">
                        {CONNECTOR_TYPE_INFO[connector.connector_type]?.name || connector.connector_type}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={getHealthBadgeVariant(connector.health_status)}>
                        {getHealthStatusText(connector.health_status)}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <Switch
                          checked={connector.is_active}
                          onCheckedChange={() => handleToggleActive(connector)}
                        />
                        <span className="text-sm text-muted-foreground">
                          {connector.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="text-sm space-y-0.5">
                        {connector.documents_total > 0 ? (
                          <>
                            <div className="flex items-center gap-1">
                              <span className="text-green-600 font-medium">{connector.documents_indexed}</span>
                              <span className="text-muted-foreground">indexed</span>
                            </div>
                            {connector.documents_pending > 0 && (
                              <div className="flex items-center gap-1">
                                <span className="text-yellow-600 font-medium">{connector.documents_pending}</span>
                                <span className="text-muted-foreground">pending</span>
                              </div>
                            )}
                            {connector.documents_failed > 0 && (
                              <div className="flex items-center gap-1">
                                <span className="text-red-600 font-medium">{connector.documents_failed}</span>
                                <span className="text-muted-foreground">failed</span>
                              </div>
                            )}
                          </>
                        ) : (
                          <span className="text-muted-foreground">No documents</span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="text-sm">
                        {connector.sync_enabled ? (
                          <span className="text-green-600">
                            Every {connector.sync_interval_hours}h
                          </span>
                        ) : (
                          <span className="text-muted-foreground">Disabled</span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="text-right">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon">
                            <IconSettings className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => handleEditConnector(connector)}>
                            <IconEdit className="mr-2 h-4 w-4" />
                            Edit Configuration
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            onClick={() => handleTestConnector(connector)}
                            disabled={testingConnector === connector.id}
                          >
                            {testingConnector === connector.id ? (
                              <>
                                <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                                Testing...
                              </>
                            ) : (
                              <>
                                <IconTestPipe className="mr-2 h-4 w-4" />
                                Test Connection
                              </>
                            )}
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => handleViewStats(connector)}>
                            <IconChartBar className="mr-2 h-4 w-4" />
                            View Statistics
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            onClick={() => handleSyncConnector(connector, false)}
                            disabled={syncingConnector === connector.id || !connector.is_active}
                          >
                            {syncingConnector === connector.id ? (
                              <>
                                <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                                Syncing...
                              </>
                            ) : (
                              <>
                                <IconRefreshDot className="mr-2 h-4 w-4" />
                                Sync Now
                              </>
                            )}
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            onClick={() => handleSyncConnector(connector, true)}
                            disabled={syncingConnector === connector.id || !connector.is_active}
                          >
                            <IconReload className="mr-2 h-4 w-4" />
                            Full Resync
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            onClick={() => handleDeleteConnector(connector)}
                            className="text-red-600 focus:text-red-600"
                          >
                            <IconTrash className="mr-2 h-4 w-4" />
                            Delete Connector
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Connector Types Info Cards */}
      <div className="mt-6">
        <h2 className="text-lg font-semibold mb-4">Supported Connector Types</h2>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {Object.values(CONNECTOR_TYPE_INFO).slice(0, 6).map((info) => (
            <Card key={info.type} className="hover:shadow-md transition-shadow">
              <CardHeader className="pb-2">
                <CardTitle className="text-base flex items-center gap-2">
                  <span className="text-xl">{getConnectorIcon(info.type)}</span>
                  {info.name}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">{info.description}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      {/* Dialogs */}
      <ConnectorDialog
        open={createDialogOpen}
        onOpenChange={setCreateDialogOpen}
        connector={null}
        onSuccess={loadConnectors}
      />

      <ConnectorDialog
        open={editDialogOpen}
        onOpenChange={setEditDialogOpen}
        connector={selectedConnector}
        onSuccess={loadConnectors}
      />

      <DeleteConnectorDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        connector={selectedConnector}
        onSuccess={loadConnectors}
      />

      <ConnectorStatsDialog
        open={statsDialogOpen}
        onOpenChange={setStatsDialogOpen}
        connector={selectedConnector}
      />
    </div>
  )
}
