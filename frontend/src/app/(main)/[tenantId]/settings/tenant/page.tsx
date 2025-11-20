"use client"

import { useState, useEffect, useCallback } from "react"
import { 
  IconDatabase, 
  IconRefresh, 
  IconTrash, 
  IconAlertTriangle,
  IconLoader2,
  IconInfoCircle,
  IconDownload,
  IconTool
} from "@tabler/icons-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Progress } from "@/components/ui/progress"
import { Badge } from "@/components/ui/badge"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { useBackendUser } from "@/contexts/user-context"
import { useNotifications } from "@/contexts/app-state-context"
import { useTenantService, TenantInfo, TenantStats, ReindexStatus } from "@/lib/services/tenant.service"
import { formatBytes } from "@/lib/utils"
import { UserDeletionDialog } from "@/components/lgpd/user-deletion-dialog"

export default function TenantSettingsPage() {
  const { backendUser: user } = useBackendUser()
  const { addNotification } = useNotifications()
  const tenantService = useTenantService()

  // States
  const [isLoading, setIsLoading] = useState(true)
  const [tenantInfo, setTenantInfo] = useState<TenantInfo | null>(null)
  const [tenantStats, setTenantStats] = useState<TenantStats | null>(null)
  const [reindexStatus, setReindexStatus] = useState<ReindexStatus | null>(null)
  const [isReindexing, setIsReindexing] = useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [deleteConfirmText, setDeleteConfirmText] = useState("")
  const [isDeleting, setIsDeleting] = useState(false)

  // Check if user is admin (tenant owner, admin role, or superuser)
  const isAdmin = Boolean(
    user &&
      (
        user.is_superuser ||
        user.is_admin ||
        user.is_team_member === false
      )
  )

  // Load initial data
  const loadTenantData = useCallback(async () => {
    setIsLoading(true)
    try {
      const [infoResponse, statsResponse, indexResponse] = await Promise.all([
        tenantService.getCurrentTenant(),
        tenantService.getTenantStats(),
        tenantService.getReindexStatus()
      ])

      if (!infoResponse.error) setTenantInfo(infoResponse.data)
      if (!statsResponse.error) setTenantStats(statsResponse.data)
      if (!indexResponse.error) setReindexStatus(indexResponse.data)
    } catch (error) {
      console.error(error)
      addNotification({
        type: 'error',
        title: 'Error al cargar los datos',
        message: 'No pudimos obtener la información de la organización'
      })
    } finally {
      setIsLoading(false)
    }
  }, [addNotification, tenantService])

  useEffect(() => {
    if (!user) {
      return
    }

    if (!isAdmin) {
      setIsLoading(false)
      return
    }

    loadTenantData()
  }, [isAdmin, loadTenantData, user])

  // Reindex operations
  const handleReindexMissing = async () => {
    setIsReindexing(true)
    try {
      const response = await tenantService.reindexMissingDocuments()
      
      if (response.error) {
        throw new Error(response.error)
      }

      addNotification({
        type: 'success',
        title: 'Reindexado completado',
        message: `Se reindexaron ${response.data?.successful || 0} documentos`
      })

      // Reload status
      const statusResponse = await tenantService.getReindexStatus()
      if (!statusResponse.error) setReindexStatus(statusResponse.data)
    } catch (error) {
      addNotification({
        type: 'error',
        title: 'Error al reindexar',
        message: (error as Error).message || 'No pudimos reindexar los documentos'
      })
    } finally {
      setIsReindexing(false)
    }
  }

  const handleForceReindex = async () => {
    if (!confirm('Esto reindexará TODOS los documentos y puede tardar varios minutos. ¿Deseas continuar?')) {
      return
    }

    setIsReindexing(true)
    try {
      const response = await tenantService.forceReindexAll()
      
      if (response.error) {
        throw new Error(response.error)
      }

      addNotification({
        type: 'success',
        title: 'Reindexado iniciado',
        message: 'La reconstrucción completa se está ejecutando en segundo plano'
      })
    } catch (error) {
      addNotification({
        type: 'error',
        title: 'No se pudo iniciar el reindexado',
        message: (error as Error).message || 'Intenta nuevamente en unos segundos'
      })
    } finally {
      setIsReindexing(false)
    }
  }

  // Delete operations
  const handleDeleteAllDocuments = async () => {
    if (deleteConfirmText !== "DELETE ALL DOCUMENTS") return

    setIsDeleting(true)
    try {
      const response = await tenantService.deleteAllDocuments()
      
      if (response.error) {
        throw new Error(response.error)
      }

      addNotification({
        type: 'success',
        title: 'Documentos eliminados',
        message: `Se eliminaron ${response.data?.deleted_count || 0} documentos`
      })

      setDeleteDialogOpen(false)
      setDeleteConfirmText("")
      
      // Reload stats
      loadTenantData()
    } catch (error) {
      addNotification({
        type: 'error',
        title: 'No se pudieron eliminar',
        message: (error as Error).message || 'Revisa tu conexión y vuelve a intentar'
      })
    } finally {
      setIsDeleting(false)
    }
  }

  const handleClearVectorDB = async () => {
    if (!confirm('Esto borrará todos los embeddings de búsqueda. Después tendrás que reindexar los documentos. ¿Continuar?')) {
      return
    }

    setIsDeleting(true)
    try {
      const response = await tenantService.clearVectorDatabase()
      
      if (response.error) {
        throw new Error(response.error)
      }

      addNotification({
        type: 'success',
        title: 'Índice vectorial vaciado',
        message: 'Se eliminaron todos los embeddings del tenant'
      })

      // Reload status
      loadTenantData()
    } catch (error) {
      addNotification({
        type: 'error',
        title: 'No se pudo limpiar',
        message: (error as Error).message || 'Intenta nuevamente en unos minutos'
      })
    } finally {
      setIsDeleting(false)
    }
  }

  // Maintenance operations
  const handleRunMaintenance = async () => {
    setIsLoading(true)
    try {
      const response = await tenantService.runMaintenance()
      
      if (response.error) {
        throw new Error(response.error)
      }

      addNotification({
        type: 'success',
        title: 'Mantenimiento completado',
        message: `Se ejecutaron ${response.data?.operations_performed?.length || 0} tareas en ${response.data?.duration_seconds || 0}s`
      })
    } catch (error) {
      addNotification({
        type: 'error',
        title: 'Falló el mantenimiento',
        message: (error as Error).message || 'No pudimos ejecutar las tareas de optimización'
      })
    } finally {
      setIsLoading(false)
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <IconLoader2 className="h-8 w-8 animate-spin" />
      </div>
    )
  }

  if (!isAdmin) {
    return (
      <div className="space-y-4 p-4 md:p-6">
        <Alert>
          <IconAlertTriangle className="h-4 w-4" />
          <AlertTitle>Acceso restringido</AlertTitle>
          <AlertDescription>
            Solo los administradores de la organización pueden acceder a esta página de configuración.
          </AlertDescription>
        </Alert>
      </div>
    )
  }

  return (
    <div className="max-w-6xl space-y-8 p-4 md:p-6">
      <div>
        <h1 className="mb-2 text-3xl font-bold">Configuración de la organización</h1>
        <p className="text-muted-foreground">
          Administra los datos, la seguridad y el mantenimiento de tu tenant
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Información de la organización</CardTitle>
            <CardDescription>Datos básicos del tenant y su actividad</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <p className="text-sm font-medium text-muted-foreground">Nombre</p>
                <p className="text-lg">{tenantInfo?.display_name || tenantInfo?.name}</p>
              </div>
              <div>
                <p className="text-sm font-medium text-muted-foreground">Creado el</p>
                <p className="text-lg">
                  {tenantInfo?.created_at ? new Date(tenantInfo.created_at).toLocaleDateString('es-ES') : 'N/A'}
                </p>
              </div>
              <div>
                <p className="text-sm font-medium text-muted-foreground">Usuarios totales</p>
                <p className="text-lg">{tenantStats?.total_users || 0}</p>
              </div>
              <div>
                <p className="text-sm font-medium text-muted-foreground">Documentos totales</p>
                <p className="text-lg">{tenantStats?.total_documents || 0}</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Uso de almacenamiento</CardTitle>
            <CardDescription>Supervisa el espacio contratado y disponible</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div>
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-sm font-medium">
                    {formatBytes(tenantStats?.storage_used_bytes || 0)} de {formatBytes(tenantStats?.storage_limit_bytes || 0)}
                  </span>
                  <span className="text-sm text-muted-foreground">
                    {tenantStats?.storage_limit_bytes > 0 
                      ? Math.round((tenantStats.storage_used_bytes / tenantStats.storage_limit_bytes) * 100) 
                      : 0}%
                  </span>
                </div>
                <Progress 
                  value={tenantStats?.storage_limit_bytes > 0 
                    ? (tenantStats.storage_used_bytes / tenantStats.storage_limit_bytes) * 100 
                    : 0} 
                />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <section>
        <Card>
          <CardHeader>
            <CardTitle>Estado del índice de búsqueda</CardTitle>
            <CardDescription>Supervisa y reconstruye el índice semántico cuando sea necesario</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div className="grid gap-4 md:grid-cols-3">
                <div className="rounded-lg border p-4 text-center">
                  <p className="text-2xl font-bold">{reindexStatus?.total_documents || 0}</p>
                  <p className="text-sm text-muted-foreground">Documentos totales</p>
                </div>
                <div className="rounded-lg border p-4 text-center">
                  <p className="text-2xl font-bold text-green-600">
                    {reindexStatus?.indexed_documents || 0}
                  </p>
                  <p className="text-sm text-muted-foreground">Indexados</p>
                </div>
                <div className="rounded-lg border p-4 text-center">
                  <p className="text-2xl font-bold text-orange-600">
                    {reindexStatus?.missing_documents || 0}
                  </p>
                  <p className="text-sm text-muted-foreground">Pendientes</p>
                </div>
              </div>

              <div className="flex items-center justify-between rounded-lg bg-muted p-4">
                <div className="flex items-center gap-2">
                  <IconInfoCircle className="h-4 w-4 text-muted-foreground" />
                  <span className="text-sm">
                    Estado actual: 
                    <Badge variant={reindexStatus?.status === 'ready' ? 'success' : 'warning'} className="ml-2">
                      {reindexStatus?.status || 'desconocido'}
                    </Badge>
                  </span>
                </div>
              </div>

              <div className="flex flex-col gap-2 md:flex-row">
                <Button
                  onClick={handleReindexMissing}
                  disabled={isReindexing || reindexStatus?.missing_documents === 0}
                  className="flex-1"
                >
                  {isReindexing ? (
                    <>
                      <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                      Reindexando…
                    </>
                  ) : (
                    <>
                      <IconRefresh className="mr-2 h-4 w-4" />
                      Reindexar pendientes
                    </>
                  )}
                </Button>

                <Button
                  variant="outline"
                  onClick={handleForceReindex}
                  disabled={isReindexing}
                  className="flex-1"
                >
                  <IconDatabase className="mr-2 h-4 w-4" />
                  Reindexado completo
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Mantenimiento del sistema</CardTitle>
            <CardDescription>
              Ejecuta tareas de optimización para mantener el rendimiento del tenant
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="rounded-lg bg-muted p-4">
              <h4 className="mb-2 font-medium">Incluye las siguientes tareas:</h4>
              <ul className="space-y-1 text-sm text-muted-foreground">
                <li>• Optimizar tablas e índices de la base de datos</li>
                <li>• Limpiar archivos huérfanos en el almacenamiento</li>
                <li>• Eliminar datos temporales vencidos</li>
                <li>• Compactar la base vectorial</li>
              </ul>
            </div>

            <Button
              onClick={handleRunMaintenance}
              disabled={isLoading}
            >
              <IconTool className="mr-2 h-4 w-4" />
              Ejecutar mantenimiento
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Copias de seguridad</CardTitle>
            <CardDescription>
              Próximamente podrás descargar respaldos completos de la organización
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button variant="outline" disabled className="w-full">
              <IconDownload className="mr-2 h-4 w-4" />
              Crear backup (muy pronto)
            </Button>
          </CardContent>
        </Card>
      </section>

      <section>
        <Card className="border-destructive/40">
          <CardHeader>
            <CardTitle className="text-destructive">Zona de peligro</CardTitle>
            <CardDescription>
              Estas operaciones son irreversibles. Úsalas solo si estás completamente seguro.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
              <div>
                <p className="font-medium text-destructive">Eliminar todos los documentos</p>
                <p className="text-sm text-muted-foreground">
                  Borra permanentemente cada archivo almacenado en el tenant.
                </p>
              </div>
              <Button
                variant="destructive"
                onClick={() => setDeleteDialogOpen(true)}
              >
                <IconTrash className="mr-2 h-4 w-4" />
                Eliminar documentos
              </Button>
            </div>

            <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
              <div>
                <p className="font-medium text-destructive">Limpiar índice semántico</p>
                <p className="text-sm text-muted-foreground">
                  Elimina todos los embeddings de búsqueda. Luego deberás reindexar los documentos.
                </p>
              </div>
              <Button
                variant="destructive"
                onClick={handleClearVectorDB}
                disabled={isDeleting}
              >
                <IconDatabase className="mr-2 h-4 w-4" />
                Vaciar base vectorial
              </Button>
            </div>

            <div className="rounded-lg border border-dashed border-destructive/40 p-4">
              <div className="mb-4 flex items-center gap-3">
                <IconAlertTriangle className="h-5 w-5 text-destructive" />
                <div>
                  <p className="font-medium text-destructive">Derecho de supresión (LGPD)</p>
                  <p className="text-sm text-muted-foreground">
                    Ejecuta la eliminación total del tenant, usuarios y documentos según la Ley de Protección de Datos.
                  </p>
                </div>
              </div>
              <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                <p className="text-sm text-muted-foreground">
                  Esta acción abre el asistente LGPD donde podrás confirmar si solo eliminas tu cuenta o toda la organización.
                </p>
                <UserDeletionDialog />
              </div>
            </div>
          </CardContent>
        </Card>
      </section>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>¿Seguro que deseas continuar?</DialogTitle>
            <DialogDescription>
              Esta acción eliminará de forma permanente todos los documentos del tenant.
              No se puede deshacer.
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4 py-4">
            <Alert className="border-destructive/50">
              <IconAlertTriangle className="h-4 w-4 text-destructive" />
              <AlertDescription>
                Escribe <strong>DELETE ALL DOCUMENTS</strong> para confirmar.
              </AlertDescription>
            </Alert>
            
            <Input
              placeholder="Introduce el texto de confirmación"
              value={deleteConfirmText}
              onChange={(e) => setDeleteConfirmText(e.target.value)}
            />
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setDeleteDialogOpen(false)
                setDeleteConfirmText("")
              }}
            >
              Cancelar
            </Button>
            <Button
              variant="destructive"
              onClick={handleDeleteAllDocuments}
              disabled={deleteConfirmText !== "DELETE ALL DOCUMENTS" || isDeleting}
            >
              {isDeleting ? (
                <>
                  <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                  Eliminando…
                </>
              ) : (
                'Eliminar todos los documentos'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
