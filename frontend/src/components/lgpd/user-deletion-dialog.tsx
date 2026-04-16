"use client"

import React, { useEffect, useState } from 'react'
import { AlertTriangle, Trash2, Shield, Eye, Building2 } from 'lucide-react'
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import {
  Alert,
  AlertDescription,
  AlertTitle,
} from "@/components/ui/alert"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Separator } from "@/components/ui/separator"
import { Switch } from "@/components/ui/switch"
import { useAuth, useUser } from '@clerk/nextjs'
import { useBackendUser } from '@/contexts/user-context'
import { useApiClient } from '@/lib/api-client'

interface UserDataSummary {
  user_id: string
  email: string
  full_name: string | null
  tenant: string
  created_at: string
  data_summary: {
    profile_data: {
      user_record: number
      user_image: number
      external_accounts: {
        clerk: boolean
        stripe: boolean
      }
    }
    document_data: {
      documents_created: number
      document_views: number
    }
    access_data: {
      role_assignments: number
    }
    audit_data: {
      note: string
      retention_reason: string
    }
  }
  lgpd_rights: {
    article_18: string
    deletion_scope: string
    audit_retention: string
    external_services: string
  }
}

interface DeletionResult {
  user_id: string
  deletion_id: string
  status: string
  deleted_at: string
  summary: {
    deleted_records: Record<string, number>
    anonymized_records: number
    storage_deletions: Record<string, Record<string, unknown>>
    external_deletions: Record<string, Record<string, unknown>>
    errors: string[]
    tenant_deleted?: boolean
    tenant_name?: string
    user_deletions?: Array<Record<string, unknown>>
  }
  lgpd_compliance: {
    article: string
    method: string
    anonymization_applied: boolean
    external_services_notified: Record<string, unknown>
  }
}

export function UserDeletionDialog() {
  const { user } = useUser()
  const { getToken } = useAuth()
  const apiClient = useApiClient()
  const { backendUser } = useBackendUser()
  const [isOpen, setIsOpen] = useState(false)
  const [step, setStep] = useState<'info' | 'summary' | 'confirm' | 'processing' | 'completed'>('info')
  const [dataSummary, setDataSummary] = useState<UserDataSummary | null>(null)
  const [deletionResult, setDeletionResult] = useState<DeletionResult | null>(null)
  const [confirmationEmail, setConfirmationEmail] = useState('')
  const [confirmationText, setConfirmationText] = useState('')
  const [reason, setReason] = useState('')
  const [deleteTenant, setDeleteTenant] = useState(false)
  const [tenantName, setTenantName] = useState<string | null>(null)
  const [tenantConfirmation, setTenantConfirmation] = useState('')
  const [isTenantLoading, setIsTenantLoading] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const REQUIRED_CONFIRMATION = "DELETE"
  const canDeleteTenant = Boolean(backendUser && (backendUser.is_superuser || backendUser.is_team_member === false))

  const fetchDataSummary = async () => {
    try {
      setIsLoading(true)
      setError(null)
      const token = await getToken()
      if (!token) {
        throw new Error('No pudimos validar tus credenciales. Vuelve a iniciar sesión.')
      }
      
      const response = await fetch('/api/v1/lgpd/data-summary', {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      })
      
      if (!response.ok) {
        throw new Error('Failed to fetch data summary')
      }
      
      const summary = await response.json()
      setDataSummary(summary)
      setStep('summary')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error occurred')
    } finally {
      setIsLoading(false)
    }
  }

  const submitDeletionRequest = async () => {
    try {
      setIsLoading(true)
      setError(null)
      setStep('processing')
      const token = await getToken()
      if (!token) {
        throw new Error('No pudimos validar tus credenciales. Vuelve a iniciar sesión.')
      }
      
      const response = await fetch('/api/v1/lgpd/request-deletion', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          confirmation_email: confirmationEmail,
          confirmation_text: confirmationText,
          reason: reason.trim() || null,
          delete_tenant: deleteTenant,
          tenant_confirmation: deleteTenant ? tenantConfirmation : null
        })
      })
      
      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Deletion request failed')
      }
      
      const result = await response.json()
      setDeletionResult(result)
      setStep('completed')
      
      // User will be logged out automatically as their account no longer exists
      setTimeout(() => {
        window.location.href = '/'
      }, 10000)
      
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error occurred')
      setStep('confirm')
    } finally {
      setIsLoading(false)
    }
  }

  const resetDialog = () => {
    setStep('info')
    setDataSummary(null)
    setDeletionResult(null)
    setConfirmationEmail('')
    setConfirmationText('')
    setReason('')
    setDeleteTenant(false)
    setTenantConfirmation('')
    setTenantName(null)
    setError(null)
    setIsLoading(false)
  }

  const canProceedToConfirmation = Boolean(
    dataSummary &&
    confirmationEmail === user?.emailAddresses?.[0]?.emailAddress &&
    confirmationText === REQUIRED_CONFIRMATION &&
    (!deleteTenant || (tenantName && tenantConfirmation === tenantName))
  )

  useEffect(() => {
    if (!deleteTenant || tenantName || !canDeleteTenant) {
      return
    }
    let isMounted = true
    const loadTenant = async () => {
      try {
        setIsTenantLoading(true)
        const token = await getToken()
        if (!token) {
          throw new Error('No pudimos validar tus credenciales. Vuelve a iniciar sesión.')
        }
        const response = await apiClient.get('/tenants/current')
        if (response.error || !response.data) {
          throw new Error(response.error || 'No pudimos obtener la información del tenant')
        }
        if (isMounted) {
          const data = response.data as { name?: string; display_name?: string }
          setTenantName(data.display_name || data.name || null)
        }
      } catch (err) {
        if (isMounted) {
          setError(err instanceof Error ? err.message : 'Unable to load tenant information')
          setDeleteTenant(false)
        }
      } finally {
        if (isMounted) {
          setIsTenantLoading(false)
        }
      }
    }
    loadTenant()
    return () => {
      isMounted = false
    }
  }, [deleteTenant, tenantName, canDeleteTenant, user, getToken, apiClient])

  return (
    <Dialog open={isOpen} onOpenChange={(open) => {
      setIsOpen(open)
      if (!open) resetDialog()
    }}>
      <DialogTrigger asChild>
        <Button variant="destructive" size="sm" className="gap-2">
          <Trash2 className="h-4 w-4" />
          Eliminar cuenta (LGPD)
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-red-600">
            <AlertTriangle className="h-5 w-5" />
            Eliminación de datos - LGPD
          </DialogTitle>
          <DialogDescription>
            Ejercicio del derecho a suprimir datos personales según la Ley General de Protección de Datos
          </DialogDescription>
        </DialogHeader>

        {error && (
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>Erro</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {/* Step 1: Information */}
        {step === 'info' && (
          <div className="space-y-6">
            <Alert>
              <Shield className="h-4 w-4" />
              <AlertTitle>Tus derechos bajo la LGPD</AlertTitle>
              <AlertDescription>
                El Artículo 18 te permite solicitar la eliminación total de tus datos personales.
                Esta acción es <strong>definitiva</strong> y borrará toda tu información del sistema.
              </AlertDescription>
            </Alert>

            <div className="space-y-4">
              <h4 className="font-medium">Qué se eliminará:</h4>
              <ul className="ml-4 space-y-2 text-sm text-muted-foreground">
                <li>• Perfil y datos personales del usuario</li>
                <li>• Todos los documentos creados por ti</li>
                <li>• Historial de visualizaciones y actividades</li>
                <li>• Datos sincronizados con servicios externos (Clerk, Stripe)</li>
                <li>• Archivos en almacenamiento en la nube</li>
                <li>• Índices de búsqueda y datos vectoriales</li>
              </ul>
            </div>

            <div className="space-y-4">
              <h4 className="font-medium">Qué se conserva (anonimizado):</h4>
              <ul className="ml-4 space-y-2 text-sm text-muted-foreground">
                <li>• Registros de auditoría requeridos por ley</li>
                <li>• Logs técnicos sin información personal</li>
              </ul>
            </div>

            <div className="flex gap-4">
              <Button 
                onClick={fetchDataSummary}
                disabled={isLoading}
                className="gap-2"
              >
                <Eye className="h-4 w-4" />
                {isLoading ? 'Cargando…' : 'Ver resumen de datos'}
              </Button>
              <Button variant="outline" onClick={() => setIsOpen(false)}>
                Cancelar
              </Button>
            </div>
          </div>
        )}

        {/* Step 2: Data Summary */}
        {step === 'summary' && dataSummary && (
          <div className="space-y-6">
            <div>
              <h4 className="font-medium mb-4">Resumen de tus datos</h4>
              
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="font-medium">Email:</span> {dataSummary.email}
                </div>
                <div>
                  <span className="font-medium">Nombre:</span> {dataSummary.full_name || 'No disponible'}
                </div>
                <div>
                  <span className="font-medium">Organización:</span> {dataSummary.tenant}
                </div>
                <div>
                  <span className="font-medium">Cuenta creada:</span> {new Date(dataSummary.created_at).toLocaleDateString('es-ES')}
                </div>
              </div>
            </div>

            <Separator />

            <div>
              <h5 className="font-medium mb-2">Datos que se eliminarán:</h5>
              <div className="grid grid-cols-2 gap-4 text-sm text-muted-foreground">
                <div>Documentos creados: <strong>{dataSummary.data_summary.document_data.documents_created}</strong></div>
                <div>Visualizaciones: <strong>{dataSummary.data_summary.document_data.document_views}</strong></div>
                <div>Roles asignados: <strong>{dataSummary.data_summary.access_data.role_assignments}</strong></div>
                <div>Imagen de perfil: <strong>{dataSummary.data_summary.profile_data.user_image ? 'Sí' : 'No'}</strong></div>
                <div>Cuenta en Clerk: <strong>{dataSummary.data_summary.profile_data.external_accounts.clerk ? 'Sí' : 'No'}</strong></div>
                <div>Cuenta en Stripe: <strong>{dataSummary.data_summary.profile_data.external_accounts.stripe ? 'Sí' : 'No'}</strong></div>
              </div>
            </div>

            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>Acción irreversible</AlertTitle>
              <AlertDescription>
                Una vez confirmada no se puede deshacer. Todos los datos se eliminarán de manera permanente en un plazo máximo de 30 días.
              </AlertDescription>
            </Alert>

            {canDeleteTenant && (
              <div className="rounded-lg border border-dashed border-red-200 p-4 space-y-3">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <p className="flex items-center gap-2 font-medium">
                      <Building2 className="h-4 w-4 text-red-500" />
                      También eliminar datos de la organización
                    </p>
                    <p className="text-sm text-muted-foreground">
                      Borra usuarios, documentos y configuraciones del tenant actual. Solo los administradores pueden activarlo.
                    </p>
                  </div>
                  <Switch
                    checked={deleteTenant}
                    disabled={isTenantLoading}
                    onCheckedChange={(checked) => {
                      setDeleteTenant(checked)
                      if (!checked) {
                        setTenantConfirmation('')
                      }
                    }}
                  />
                </div>
                {deleteTenant && (
                  <Alert variant="destructive">
                    <AlertTriangle className="h-4 w-4" />
                    <AlertDescription>
                      Esta opción eliminará definitivamente la organización{" "}
                      <strong>{tenantName || 'cargando...'}</strong> y todos los datos asociados.
                      Confirma el nombre de la organización en el siguiente paso.
                    </AlertDescription>
                  </Alert>
                )}
              </div>
            )}

            <div className="flex gap-4">
              <Button 
                onClick={() => setStep('confirm')}
                variant="destructive"
                className="gap-2"
              >
                <Trash2 className="h-4 w-4" />
                Continuar con la eliminación
              </Button>
              <Button variant="outline" onClick={() => setStep('info')}>
                Volver
              </Button>
            </div>
          </div>
        )}

        {/* Step 3: Confirmation */}
        {step === 'confirm' && (
          <div className="space-y-6">
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>Confirmación final</AlertTitle>
              <AlertDescription>
                Para confirmar la eliminación permanente de tu cuenta debes completar los siguientes campos.
                {deleteTenant && (
                  <span className="block mt-2 text-red-500 font-semibold">
                    Esta acción también eliminará toda la organización y todos los usuarios asociados.
                  </span>
                )}
              </AlertDescription>
            </Alert>

            <div className="space-y-4">
              <div>
                <Label htmlFor="confirmation-email">
                  Confirma tu email: <span className="text-red-500">*</span>
                </Label>
                <Input
                  id="confirmation-email"
                  type="email"
                  value={confirmationEmail}
                  onChange={(e) => setConfirmationEmail(e.target.value)}
                  placeholder={user?.emailAddresses?.[0]?.emailAddress}
                />
              </div>

              <div>
                <Label htmlFor="confirmation-text">
                  Escribe exactamente: <code className="bg-muted px-1 rounded">{REQUIRED_CONFIRMATION}</code> <span className="text-red-500">*</span>
                </Label>
                <Input
                  id="confirmation-text"
                  value={confirmationText}
                  onChange={(e) => setConfirmationText(e.target.value)}
                  placeholder={REQUIRED_CONFIRMATION}
                />
              </div>

              <div>
                <Label htmlFor="reason">Motivo (opcional)</Label>
                <Textarea
                  id="reason"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="Cuéntanos por qué deseas eliminar la cuenta (opcional)"
                  rows={3}
                />
              </div>

              {deleteTenant && (
                <div className="space-y-2 rounded-lg border border-dashed border-red-200 p-3">
                  <Label htmlFor="tenant-confirmation" className="flex items-center gap-2">
                    Confirma el nombre de la organización <span className="text-red-500">*</span>
                  </Label>
                  <Input
                    id="tenant-confirmation"
                    value={tenantConfirmation}
                    onChange={(e) => setTenantConfirmation(e.target.value)}
                    placeholder={tenantName || 'Nombre de la organización'}
                    disabled={isTenantLoading || !tenantName}
                  />
                  <p className="text-xs text-muted-foreground">
                    Escribe exactamente <strong>{tenantName || 'el nombre del tenant'}</strong> para confirmar la eliminación total.
                  </p>
                </div>
              )}
            </div>

            <div className="flex gap-4">
              <Button 
                onClick={submitDeletionRequest}
                disabled={!canProceedToConfirmation || isLoading}
                variant="destructive"
                className="gap-2"
              >
                <Trash2 className="h-4 w-4" />
                {isLoading ? 'Procesando…' : 'Confirmar eliminación definitiva'}
              </Button>
              <Button variant="outline" onClick={() => setStep('summary')}>
                Volver
              </Button>
            </div>
          </div>
        )}

        {/* Step 4: Processing */}
        {step === 'processing' && (
          <div className="space-y-6 text-center">
            <div className="flex justify-center">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-red-600"></div>
            </div>
            <div>
              <h4 className="font-medium">Procesando la eliminación</h4>
              <p className="mt-2 text-sm text-muted-foreground">
                Estamos borrando tu información de todos los sistemas. El proceso puede tardar algunos minutos.
              </p>
            </div>
          </div>
        )}

        {/* Step 5: Completed */}
        {step === 'completed' && deletionResult && (
          <div className="space-y-6">
            <Alert>
              <Shield className="h-4 w-4" />
              <AlertTitle>Eliminación completada</AlertTitle>
              <AlertDescription>
                Tus datos se eliminaron correctamente de acuerdo con la LGPD.
                Serás redirigido automáticamente en unos segundos.
              </AlertDescription>
            </Alert>

            {deletionResult.summary.tenant_deleted && (
              <Alert variant="destructive">
                <Building2 className="h-4 w-4" />
                <AlertTitle>Organización eliminada</AlertTitle>
                <AlertDescription>
                  El tenant <strong>{deletionResult.summary.tenant_name || ''}</strong> fue eliminado definitivamente, incluidos todos los usuarios y documentos asociados.
                </AlertDescription>
              </Alert>
            )}

            <div className="space-y-4">
              <div>
                <h5 className="font-medium">Resumen de la eliminación:</h5>
                <div className="mt-2 text-sm text-muted-foreground">
                  <div>ID de referencia: <code>{deletionResult.deletion_id}</code></div>
                  <div>Fecha: {new Date(deletionResult.deleted_at).toLocaleString('es-ES')}</div>
                  <div>Registros eliminados: {Object.values(deletionResult.summary.deleted_records).reduce((a, b) => a + b, 0)}</div>
                  <div>Registros anonimizados: {deletionResult.summary.anonymized_records}</div>
                </div>
              </div>

              <div className="text-xs text-muted-foreground">
                <p><strong>Base legal:</strong> {deletionResult.lgpd_compliance.article}</p>
                <p><strong>Método aplicado:</strong> {deletionResult.lgpd_compliance.method}</p>
              </div>
            </div>

            <div className="text-center">
              <Button onClick={() => window.location.href = '/'}>
                Volver al inicio
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
