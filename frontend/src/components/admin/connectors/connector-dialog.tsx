"use client"

import { useState, useEffect } from "react"
import {
  IconLoader2,
  IconPlugConnected,
} from "@tabler/icons-react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Separator } from "@/components/ui/separator"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Connector,
  ConnectorType,
  ConnectorAuthType,
  CreateConnectorData,
  UpdateConnectorData,
  CONNECTOR_TYPE_INFO,
  useConnectorService,
} from "@/lib/services/connector.service"
import { useNotifications } from "@/contexts/app-state-context"

interface ConnectorDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  connector: Connector | null
  onSuccess: () => void
}

export function ConnectorDialog({
  open,
  onOpenChange,
  connector,
  onSuccess,
}: ConnectorDialogProps) {
  const connectorService = useConnectorService()
  const { addNotification } = useNotifications()

  const isEditing = connector !== null
  const [isLoading, setIsLoading] = useState(false)

  // Form state
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [connectorType, setConnectorType] = useState<ConnectorType>(ConnectorType.ALFRESCO)
  const [authType, setAuthType] = useState<ConnectorAuthType>(ConnectorAuthType.SERVICE_ACCOUNT)
  const [syncEnabled, setSyncEnabled] = useState(true)
  const [syncIntervalHours, setSyncIntervalHours] = useState(24)
  const [config, setConfig] = useState<Record<string, any>>({})

  // Reset form when dialog opens/closes or connector changes
  useEffect(() => {
    if (open) {
      if (connector) {
        // Editing existing connector
        setName(connector.name)
        setDescription(connector.description || "")
        setConnectorType(connector.connector_type)
        setAuthType(connector.auth_type)
        setSyncEnabled(connector.sync_enabled)
        setSyncIntervalHours(connector.sync_interval_hours)
        setConfig(connector.config || {})
      } else {
        // Creating new connector
        setName("")
        setDescription("")
        setConnectorType(ConnectorType.ALFRESCO)
        setAuthType(ConnectorAuthType.SERVICE_ACCOUNT)
        setSyncEnabled(true)
        setSyncIntervalHours(24)
        setConfig({})
      }
    }
  }, [open, connector])

  // Update auth type when connector type changes
  useEffect(() => {
    const typeInfo = CONNECTOR_TYPE_INFO[connectorType]
    if (typeInfo && !typeInfo.authTypes.includes(authType)) {
      setAuthType(typeInfo.authTypes[0])
    }
  }, [connectorType])

  const handleConfigChange = (field: string, value: any) => {
    setConfig((prev) => ({
      ...prev,
      [field]: value,
    }))
  }

  const handleSubmit = async () => {
    setIsLoading(true)

    try {
      if (isEditing && connector) {
        // Update connector
        const updateData: UpdateConnectorData = {
          name,
          description: description || undefined,
          config,
          sync_enabled: syncEnabled,
          sync_interval_hours: syncIntervalHours,
        }

        await connectorService.updateConnector(connector.id, updateData)

        addNotification({
          type: "success",
          title: "Connector updated",
          message: `${name} has been updated successfully`,
        })
      } else {
        // Create connector
        const createData: CreateConnectorData = {
          name,
          description: description || undefined,
          connector_type: connectorType,
          auth_type: authType,
          config,
          sync_enabled: syncEnabled,
          sync_interval_hours: syncIntervalHours,
        }

        await connectorService.createConnector(createData)

        addNotification({
          type: "success",
          title: "Connector created",
          message: `${name} has been created successfully`,
        })
      }

      onOpenChange(false)
      onSuccess()
    } catch (error: any) {
      addNotification({
        type: "error",
        title: isEditing ? "Failed to update connector" : "Failed to create connector",
        message: error.message || "An error occurred",
      })
    } finally {
      setIsLoading(false)
    }
  }

  const typeInfo = CONNECTOR_TYPE_INFO[connectorType]

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <IconPlugConnected className="h-5 w-5" />
            {isEditing ? "Edit Connector" : "Create Connector"}
          </DialogTitle>
          <DialogDescription>
            {isEditing
              ? "Update the connector configuration"
              : "Configure a new external data source connector"}
          </DialogDescription>
        </DialogHeader>

        <ScrollArea className="max-h-[60vh] pr-4">
          <div className="space-y-6 py-4">
            {/* Basic Info */}
            <div className="space-y-4">
              <h3 className="font-medium">Basic Information</h3>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="name">Name *</Label>
                  <Input
                    id="name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="My Connector"
                  />
                </div>

                {!isEditing && (
                  <div className="space-y-2">
                    <Label htmlFor="type">Connector Type *</Label>
                    <Select
                      value={connectorType}
                      onValueChange={(value) => setConnectorType(value as ConnectorType)}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {Object.values(CONNECTOR_TYPE_INFO).map((info) => (
                          <SelectItem key={info.type} value={info.type}>
                            {info.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                )}
              </div>

              <div className="space-y-2">
                <Label htmlFor="description">Description</Label>
                <Textarea
                  id="description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Optional description of this connector"
                  rows={2}
                />
              </div>
            </div>

            <Separator />

            {/* Authentication */}
            {!isEditing && (
              <>
                <div className="space-y-4">
                  <h3 className="font-medium">Authentication</h3>

                  <div className="space-y-2">
                    <Label htmlFor="auth-type">Authentication Type</Label>
                    <Select
                      value={authType}
                      onValueChange={(value) => setAuthType(value as ConnectorAuthType)}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {typeInfo?.authTypes.map((type) => (
                          <SelectItem key={type} value={type}>
                            {type === ConnectorAuthType.DELEGATED && "Delegated (per-user OAuth)"}
                            {type === ConnectorAuthType.SERVICE_ACCOUNT && "Service Account"}
                            {type === ConnectorAuthType.API_KEY && "API Key"}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">
                      {authType === ConnectorAuthType.DELEGATED &&
                        "Each user authorizes with their own account"}
                      {authType === ConnectorAuthType.SERVICE_ACCOUNT &&
                        "Single service account for all users"}
                      {authType === ConnectorAuthType.API_KEY &&
                        "API key based authentication"}
                    </p>
                  </div>
                </div>

                <Separator />
              </>
            )}

            {/* Type-specific Configuration */}
            <div className="space-y-4">
              <h3 className="font-medium">{typeInfo?.name} Configuration</h3>

              {typeInfo?.configFields.map((field) => (
                <div key={field.name} className="space-y-2">
                  <Label htmlFor={field.name}>
                    {field.label}
                    {field.required && " *"}
                  </Label>

                  {field.type === "textarea" ? (
                    <Textarea
                      id={field.name}
                      value={config[field.name] || ""}
                      onChange={(e) => handleConfigChange(field.name, e.target.value)}
                      placeholder={field.placeholder}
                      rows={4}
                    />
                  ) : field.type === "select" ? (
                    <Select
                      value={config[field.name] || ""}
                      onValueChange={(value) => handleConfigChange(field.name, value)}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder={field.placeholder} />
                      </SelectTrigger>
                      <SelectContent>
                        {field.options?.map((option) => (
                          <SelectItem key={option.value} value={option.value}>
                            {option.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  ) : (
                    <Input
                      id={field.name}
                      type={field.type === "password" ? "password" : field.type}
                      value={config[field.name] || field.defaultValue || ""}
                      onChange={(e) =>
                        handleConfigChange(
                          field.name,
                          field.type === "number" ? Number(e.target.value) : e.target.value
                        )
                      }
                      placeholder={field.placeholder}
                      min={field.min}
                      max={field.max}
                    />
                  )}

                  {field.description && (
                    <p className="text-xs text-muted-foreground">{field.description}</p>
                  )}
                </div>
              ))}
            </div>

            <Separator />

            {/* Sync Settings */}
            <div className="space-y-4">
              <h3 className="font-medium">Sync Settings</h3>

              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label>Enable Automatic Sync</Label>
                  <p className="text-xs text-muted-foreground">
                    Automatically sync documents from this source
                  </p>
                </div>
                <Switch checked={syncEnabled} onCheckedChange={setSyncEnabled} />
              </div>

              {syncEnabled && (
                <div className="space-y-2">
                  <Label htmlFor="sync-interval">Sync Interval (hours)</Label>
                  <Input
                    id="sync-interval"
                    type="number"
                    value={syncIntervalHours}
                    onChange={(e) => setSyncIntervalHours(Number(e.target.value))}
                    min={1}
                    max={168}
                  />
                  <p className="text-xs text-muted-foreground">
                    How often to check for new or updated documents (1-168 hours)
                  </p>
                </div>
              )}
            </div>
          </div>
        </ScrollArea>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isLoading}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={isLoading || !name}>
            {isLoading ? (
              <>
                <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                {isEditing ? "Updating..." : "Creating..."}
              </>
            ) : isEditing ? (
              "Update Connector"
            ) : (
              "Create Connector"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
