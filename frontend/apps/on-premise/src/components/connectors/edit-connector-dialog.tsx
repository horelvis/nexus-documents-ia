'use client'

/**
 * Edit Connector Dialog
 *
 * Allows editing connector settings: name, description, sync config, active status.
 * Does NOT allow changing connector_type or auth_type (would break existing syncs).
 */

import { useState, useEffect } from 'react'
import {
  IconLoader2,
  IconAlertCircle,
  IconCheck,
  IconSettings,
} from '@tabler/icons-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  Button,
  Input,
  Label,
  Textarea,
  Switch,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Separator,
} from '@/components/ui'
import {
  Connector,
  UpdateConnectorData,
  connectorService,
  connectorNames,
} from '@/lib/services/connector.service'

interface EditConnectorDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  connector: Connector | null
  onSave?: () => void
}

const syncIntervalOptions = [
  { value: '1', label: 'Cada hora' },
  { value: '6', label: 'Cada 6 horas' },
  { value: '12', label: 'Cada 12 horas' },
  { value: '24', label: 'Cada día' },
  { value: '48', label: 'Cada 2 días' },
  { value: '168', label: 'Cada semana' },
]

export function EditConnectorDialog({
  open,
  onOpenChange,
  connector,
  onSave,
}: EditConnectorDialogProps) {
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  // Form state
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [syncEnabled, setSyncEnabled] = useState(true)
  const [syncInterval, setSyncInterval] = useState('24')
  const [isActive, setIsActive] = useState(true)
  const [config, setConfig] = useState<Record<string, any>>({})

  // Reset form when connector changes
  useEffect(() => {
    if (connector) {
      setName(connector.name)
      setDescription(connector.description || '')
      setSyncEnabled(connector.sync_enabled)
      setSyncInterval(String(connector.sync_interval_hours))
      setIsActive(connector.is_active)
      setConfig(connector.config || {})
      setError(null)
      setSuccess(false)
    }
  }, [connector])

  const handleSave = async () => {
    if (!connector) return

    setIsSaving(true)
    setError(null)
    setSuccess(false)

    const updateData: UpdateConnectorData = {
      name: name.trim(),
      description: description.trim() || undefined,
      sync_enabled: syncEnabled,
      sync_interval_hours: parseInt(syncInterval),
      is_active: isActive,
      config,
    }

    try {
      const result = await connectorService.updateConnector(connector.id, updateData)
      if (result.error) {
        setError(result.error)
      } else {
        setSuccess(true)
        setTimeout(() => {
          onSave?.()
          onOpenChange(false)
        }, 1000)
      }
    } catch (err: any) {
      setError(err.message || 'Error al guardar')
    } finally {
      setIsSaving(false)
    }
  }

  const handleConfigChange = (key: string, value: string) => {
    setConfig(prev => ({ ...prev, [key]: value }))
  }

  if (!connector) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px] max-h-[90vh] overflow-y-auto overflow-x-hidden">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <IconSettings className="h-5 w-5" />
            Editar Conector
          </DialogTitle>
          <DialogDescription>
            {connectorNames[connector.connector_type]}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* Error/Success messages */}
          <div className="h-8">
            {error && (
              <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 dark:bg-red-950/30 px-3 py-1.5 rounded">
                <IconAlertCircle className="h-4 w-4 flex-shrink-0" />
                <span className="truncate">{error}</span>
              </div>
            )}
            {success && (
              <div className="flex items-center gap-2 text-sm text-green-600 bg-green-50 dark:bg-green-950/30 px-3 py-1.5 rounded">
                <IconCheck className="h-4 w-4 flex-shrink-0" />
                <span>Guardado correctamente</span>
              </div>
            )}
          </div>

          {/* Basic Info */}
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="name" className="text-sm">Nombre</Label>
              <Input
                id="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Nombre del conector"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="description" className="text-sm">Descripción</Label>
              <Textarea
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Descripción opcional"
                rows={2}
              />
            </div>
          </div>

          <Separator />

          {/* Sync Settings */}
          <div className="space-y-3">
            <h4 className="text-sm font-medium">Sincronización</h4>

            <div className="flex items-center justify-between">
              <div>
                <Label className="text-sm">Sincronización automática</Label>
                <p className="text-xs text-muted-foreground">
                  Sincroniza documentos periódicamente
                </p>
              </div>
              <Switch
                checked={syncEnabled}
                onCheckedChange={setSyncEnabled}
              />
            </div>

            {syncEnabled && (
              <div className="space-y-1.5">
                <Label className="text-sm">Intervalo</Label>
                <Select value={syncInterval} onValueChange={setSyncInterval}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {syncIntervalOptions.map(opt => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>

          <Separator />

          {/* Status */}
          <div className="flex items-center justify-between">
            <div>
              <Label className="text-sm">Conector activo</Label>
              <p className="text-xs text-muted-foreground">
                Desactivar pausa todas las operaciones
              </p>
            </div>
            <Switch
              checked={isActive}
              onCheckedChange={setIsActive}
            />
          </div>

          <Separator />

          {/* Config Fields (editable) */}
          {Object.keys(config).length > 0 && (
            <div className="space-y-3">
              <h4 className="text-sm font-medium">Configuración</h4>
              <p className="text-xs text-muted-foreground">
                Modifica los parámetros de conexión
              </p>

              {Object.entries(config).slice(0, 5).map(([key, value]) => {
                const isPassword = key.toLowerCase().includes('password') || key.toLowerCase().includes('secret')
                const label = key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())

                return (
                  <div key={key} className="space-y-1.5">
                    <Label className="text-sm">{label}</Label>
                    <Input
                      type={isPassword ? 'password' : 'text'}
                      value={String(value || '')}
                      onChange={(e) => handleConfigChange(key, e.target.value)}
                    />
                  </div>
                )
              })}

              {Object.keys(config).length > 5 && (
                <p className="text-xs text-muted-foreground">
                  +{Object.keys(config).length - 5} campos adicionales
                </p>
              )}
            </div>
          )}
        </div>

        <DialogFooter className="gap-2">
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isSaving}
          >
            Cancelar
          </Button>
          <Button
            onClick={handleSave}
            disabled={isSaving || !name.trim()}
          >
            {isSaving ? (
              <IconLoader2 className="h-4 w-4 animate-spin mr-2" />
            ) : (
              <IconCheck className="h-4 w-4 mr-2" />
            )}
            Guardar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
