'use client'

/**
 * Health Check Dialog for Emma On-Premise
 *
 * Shows detailed results of connector health check with visual feedback.
 */

import { useState, useEffect } from 'react'
import {
  IconHeart,
  IconLoader2,
  IconAlertCircle,
  IconCheck,
  IconX,
  IconClock,
  IconUser,
  IconServer,
  IconSearch,
  IconFolder,
  IconRefresh,
  IconDatabase,
  IconTable,
  IconFileText,
} from '@tabler/icons-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Badge,
  Button,
  Alert,
  AlertDescription,
  Separator,
} from '@nexus/shared/ui'
import {
  Connector,
  ConnectorType,
  HealthCheckResponse,
  connectorService,
  connectorNames,
} from '@/lib/services/connector.service'

interface HealthCheckDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  connector: Connector | null
  onHealthCheckComplete?: () => void
}

function formatResponseTime(ms: number): string {
  if (ms < 1000) {
    return `${Math.round(ms)} ms`
  }
  return `${(ms / 1000).toFixed(2)} s`
}

function getStatusIcon(status: string) {
  switch (status) {
    case 'healthy':
      return <IconCheck className="h-5 w-5 text-green-500" />
    case 'degraded':
      return <IconAlertCircle className="h-5 w-5 text-yellow-500" />
    case 'unhealthy':
      return <IconX className="h-5 w-5 text-red-500" />
    default:
      return <IconAlertCircle className="h-5 w-5 text-gray-400" />
  }
}

function getStatusColor(status: string): string {
  switch (status) {
    case 'healthy':
      return 'bg-green-50 border-green-200 text-green-700 dark:bg-green-950 dark:border-green-800 dark:text-green-300'
    case 'degraded':
      return 'bg-yellow-50 border-yellow-200 text-yellow-700 dark:bg-yellow-950 dark:border-yellow-800 dark:text-yellow-300'
    case 'unhealthy':
      return 'bg-red-50 border-red-200 text-red-700 dark:bg-red-950 dark:border-red-800 dark:text-red-300'
    default:
      return 'bg-gray-50 border-gray-200 text-gray-700 dark:bg-gray-800 dark:border-gray-700 dark:text-gray-300'
  }
}

function getStatusText(status: string): string {
  switch (status) {
    case 'healthy':
      return 'Saludable'
    case 'degraded':
      return 'Degradado'
    case 'unhealthy':
      return 'Error'
    default:
      return 'Desconocido'
  }
}

export function HealthCheckDialog({
  open,
  onOpenChange,
  connector,
  onHealthCheckComplete,
}: HealthCheckDialogProps) {
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<HealthCheckResponse | null>(null)

  useEffect(() => {
    if (open && connector) {
      runHealthCheck()
    }
  }, [open, connector])

  const runHealthCheck = async () => {
    if (!connector) return

    setIsLoading(true)
    setError(null)
    setResult(null)

    try {
      const response = await connectorService.testConnector(connector.id)
      if (response.error) {
        setError(response.error)
      } else if (response.data) {
        setResult(response.data)
        onHealthCheckComplete?.()
      }
    } catch (err: any) {
      setError(err.message || 'Error al realizar el health check')
    } finally {
      setIsLoading(false)
    }
  }

  if (!connector) return null

  const details = result?.details || {}

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <IconHeart className="h-5 w-5" />
            Resultado del Health Check
          </DialogTitle>
          <DialogDescription>
            {connector.name} ({connectorNames[connector.connector_type]})
          </DialogDescription>
        </DialogHeader>

        <div className="py-4 space-y-4">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-12">
              <IconLoader2 className="h-8 w-8 animate-spin text-primary mb-4" />
              <p className="text-muted-foreground">Ejecutando health check...</p>
              <p className="text-xs text-muted-foreground mt-2">
                Probando autenticación, API y servicios
              </p>
            </div>
          ) : error ? (
            <Alert variant="destructive">
              <IconAlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : result ? (
            <>
              {/* Status Banner */}
              <div className={`p-4 rounded-lg border ${getStatusColor(result.status)}`}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    {getStatusIcon(result.status)}
                    <div>
                      <h3 className="font-semibold">{getStatusText(result.status)}</h3>
                      <p className="text-sm opacity-80">{result.message}</p>
                    </div>
                  </div>
                  <Badge variant="outline" className="bg-white/50 dark:bg-black/20">
                    <IconClock className="h-3 w-3 mr-1" />
                    {details.response_time_ms
                      ? formatResponseTime(details.response_time_ms)
                      : 'N/A'}
                  </Badge>
                </div>
              </div>

              {/* Alfresco-specific Details */}
              {connector.connector_type === 'alfresco' && (
                <div className="grid grid-cols-2 gap-4">
                  {/* Authentication */}
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-medium flex items-center gap-2">
                        <IconUser className="h-4 w-4 text-muted-foreground" />
                        Autenticación
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      {details.authenticated_user ? (
                        <div>
                          <div className="text-lg font-semibold text-green-600 dark:text-green-400">
                            {details.authenticated_user}
                          </div>
                          {details.user_id && (
                            <p className="text-xs text-muted-foreground">
                              ID: {details.user_id}
                            </p>
                          )}
                        </div>
                      ) : (
                        <div className="text-red-600 dark:text-red-400">Autenticación fallida</div>
                      )}
                    </CardContent>
                  </Card>

                  {/* Server Info */}
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-medium flex items-center gap-2">
                        <IconServer className="h-4 w-4 text-muted-foreground" />
                        Información del Servidor
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      {details.api_version ? (
                        <div>
                          <div className="text-lg font-semibold">
                            v{details.api_version}
                          </div>
                          {details.edition && (
                            <p className="text-xs text-muted-foreground">
                              {details.edition}
                            </p>
                          )}
                          {details.repository_id && (
                            <p className="text-xs text-muted-foreground truncate">
                              Repo: {details.repository_id}
                            </p>
                          )}
                        </div>
                      ) : (
                        <div className="text-muted-foreground">
                          Versión no disponible
                        </div>
                      )}
                    </CardContent>
                  </Card>

                  {/* Search API */}
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-medium flex items-center gap-2">
                        <IconSearch className="h-4 w-4 text-muted-foreground" />
                        Search API (AFTS)
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      {details.search_api === 'working' ? (
                        <div>
                          <div className="flex items-center gap-2 text-green-600 dark:text-green-400">
                            <IconCheck className="h-4 w-4" />
                            <span className="font-semibold">Funcionando</span>
                          </div>
                          {details.total_folders !== undefined && (
                            <p className="text-xs text-muted-foreground mt-1">
                              {details.total_folders.toLocaleString()} carpetas encontradas
                            </p>
                          )}
                        </div>
                      ) : (
                        <div className="flex items-center gap-2 text-red-600 dark:text-red-400">
                          <IconX className="h-4 w-4" />
                          <span>{details.search_api || 'No funciona'}</span>
                        </div>
                      )}
                    </CardContent>
                  </Card>

                  {/* Sites */}
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-medium flex items-center gap-2">
                        <IconFolder className="h-4 w-4 text-muted-foreground" />
                        Acceso a Sites
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="text-lg font-semibold">
                        {details.sites_count || 0} sites
                      </div>
                      {details.sites && details.sites.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-2">
                          {details.sites.slice(0, 3).map((site: string) => (
                            <Badge key={site} variant="secondary" className="text-xs">
                              {site}
                            </Badge>
                          ))}
                          {details.sites.length > 3 && (
                            <Badge variant="outline" className="text-xs">
                              +{details.sites.length - 3} más
                            </Badge>
                          )}
                        </div>
                      )}
                      {details.default_site_accessible !== undefined && (
                        <p
                          className={`text-xs mt-2 ${
                            details.default_site_accessible
                              ? 'text-green-600 dark:text-green-400'
                              : 'text-yellow-600 dark:text-yellow-400'
                          }`}
                        >
                          Site por defecto:{' '}
                          {details.default_site_accessible
                            ? 'accesible'
                            : 'no encontrado'}
                        </p>
                      )}
                    </CardContent>
                  </Card>
                </div>
              )}

              {/* Microsoft/Google specific details */}
              {(connector.connector_type === 'sharepoint' ||
                connector.connector_type === 'onedrive' ||
                connector.connector_type === 'google_drive' ||
                connector.connector_type === 'google_workspace') && (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium flex items-center gap-2">
                      <IconServer className="h-4 w-4 text-muted-foreground" />
                      Estado de Configuración
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      {details.auth_type && (
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Tipo de Auth</span>
                          <span className="font-medium">{details.auth_type}</span>
                        </div>
                      )}
                      {details.tenant_id && (
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Tenant ID</span>
                          <span className="font-mono text-xs">{details.tenant_id}</span>
                        </div>
                      )}
                      {details.client_id && (
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Client ID</span>
                          <span className="font-mono text-xs">{details.client_id}</span>
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* S3/Azure specific details */}
              {(connector.connector_type === 's3' ||
                connector.connector_type === 'azure_blob') && (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium flex items-center gap-2">
                      <IconServer className="h-4 w-4 text-muted-foreground" />
                      Configuración de Almacenamiento
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      {details.bucket && (
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Bucket</span>
                          <span className="font-medium">{details.bucket}</span>
                        </div>
                      )}
                      {details.container && (
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Container</span>
                          <span className="font-medium">{details.container}</span>
                        </div>
                      )}
                      {details.region && (
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Región</span>
                          <span className="font-medium">{details.region}</span>
                        </div>
                      )}
                      {details.storage_account && (
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Storage Account</span>
                          <span className="font-medium">{details.storage_account}</span>
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Database-specific details */}
              {connector.connector_type === 'database' && (
                <div className="grid grid-cols-2 gap-4">
                  {/* Connection Info */}
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-medium flex items-center gap-2">
                        <IconDatabase className="h-4 w-4 text-muted-foreground" />
                        Conexión
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      {details.connected ? (
                        <div>
                          <div className="flex items-center gap-2 text-green-600 dark:text-green-400">
                            <IconCheck className="h-4 w-4" />
                            <span className="font-semibold">Conectado</span>
                          </div>
                          {details.engine && (
                            <p className="text-sm mt-1">
                              Motor: <span className="font-medium">{details.engine}</span>
                            </p>
                          )}
                          {details.database_version && (
                            <p className="text-xs text-muted-foreground">
                              Versión: {details.database_version}
                            </p>
                          )}
                        </div>
                      ) : (
                        <div className="flex items-center gap-2 text-red-600 dark:text-red-400">
                          <IconX className="h-4 w-4" />
                          <span>Conexión fallida</span>
                        </div>
                      )}
                    </CardContent>
                  </Card>

                  {/* Server Info */}
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-medium flex items-center gap-2">
                        <IconServer className="h-4 w-4 text-muted-foreground" />
                        Servidor
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      {details.host && (
                        <div className="text-lg font-semibold truncate">
                          {details.host}
                          {details.port && <span className="text-muted-foreground">:{details.port}</span>}
                        </div>
                      )}
                      {details.database_name && (
                        <p className="text-xs text-muted-foreground mt-1">
                          BD: {details.database_name}
                        </p>
                      )}
                      {details.ssl_enabled !== undefined && (
                        <Badge variant={details.ssl_enabled ? 'secondary' : 'outline'} className="mt-2">
                          SSL: {details.ssl_enabled ? 'Habilitado' : 'Deshabilitado'}
                        </Badge>
                      )}
                    </CardContent>
                  </Card>

                  {/* Table/Query Info */}
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-medium flex items-center gap-2">
                        <IconTable className="h-4 w-4 text-muted-foreground" />
                        Origen de Datos
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      {details.table_name && (
                        <div>
                          <p className="text-sm">
                            Tabla: <span className="font-mono font-medium">{details.table_name}</span>
                          </p>
                        </div>
                      )}
                      {details.uses_custom_query && (
                        <Badge variant="secondary" className="mt-2">
                          Query Personalizado
                        </Badge>
                      )}
                      {details.storage_type && (
                        <p className="text-xs text-muted-foreground mt-2">
                          Almacenamiento: {details.storage_type === 'blob' ? 'BLOB' : details.storage_type === 'file_path' ? 'Ruta de Archivo' : 'URL'}
                        </p>
                      )}
                    </CardContent>
                  </Card>

                  {/* Documents Count */}
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-medium flex items-center gap-2">
                        <IconFileText className="h-4 w-4 text-muted-foreground" />
                        Documentos
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="text-2xl font-bold">
                        {details.total_documents !== undefined
                          ? details.total_documents.toLocaleString()
                          : '—'}
                      </div>
                      <p className="text-xs text-muted-foreground">
                        documentos disponibles
                      </p>
                      {details.sample_query_success !== undefined && (
                        <div className={`flex items-center gap-1 mt-2 text-xs ${details.sample_query_success ? 'text-green-600' : 'text-red-600'}`}>
                          {details.sample_query_success ? (
                            <>
                              <IconCheck className="h-3 w-3" />
                              Query de prueba exitoso
                            </>
                          ) : (
                            <>
                              <IconX className="h-3 w-3" />
                              Error en query de prueba
                            </>
                          )}
                        </div>
                      )}
                    </CardContent>
                  </Card>
                </div>
              )}

              {/* Connection Details */}
              <Separator />

              <div className="text-xs text-muted-foreground space-y-1">
                {details.url && (
                  <p>
                    <strong>URL:</strong> {details.url}
                  </p>
                )}
                <p>
                  <strong>Comprobado:</strong>{' '}
                  {new Date(result.checked_at).toLocaleString()}
                </p>
              </div>
            </>
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cerrar
          </Button>
          <Button onClick={runHealthCheck} disabled={isLoading}>
            {isLoading ? (
              <>
                <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                Probando...
              </>
            ) : (
              <>
                <IconRefresh className="mr-2 h-4 w-4" />
                Volver a Probar
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
