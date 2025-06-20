"use client"

import { useState, useEffect } from "react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { 
  IconLoader2, 
  IconAlertCircle,
  IconInfoCircle,
  IconKey,
  IconShieldLock,
  IconTestPipe
} from "@tabler/icons-react"
import { 
  SignatureProvider, 
  CreateProviderData,
  DocuSignCredentials,
  YouSignCredentials,
  SignaturitCredentials,
  SupportedProvider
} from "@/lib/services/signature-service"
import { useSignatureService } from "@/lib/services/signature-service.hooks"
import { useNotifications } from "@/contexts/notifications-context"

interface ProviderConfigDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  provider: SignatureProvider | null
  isCreating: boolean
  onSuccess: () => void
}

export function ProviderConfigDialog({
  open,
  onOpenChange,
  provider,
  isCreating,
  onSuccess,
}: ProviderConfigDialogProps) {
  const { addNotification } = useNotifications()
  const signatureService = useSignatureService()
  
  // Form state
  const [providerName, setProviderName] = useState<'docusign' | 'yousign' | 'signaturit'>('docusign')
  const [displayName, setDisplayName] = useState('')
  const [isActive, setIsActive] = useState(true)
  const [isDefault, setIsDefault] = useState(false)
  
  // Credential states
  const [docusignCreds, setDocusignCreds] = useState<DocuSignCredentials>({
    integration_key: '',
    secret_key: '',
    account_id: '',
    base_url: 'https://demo.docusign.net/restapi'
  })
  
  const [yousignCreds, setYousignCreds] = useState<YouSignCredentials>({
    api_key: '',
    environment: 'sandbox'
  })
  
  const [signaturitCreds, setSignaturitCreds] = useState<SignaturitCredentials>({
    access_token: '',
    environment: 'sandbox'
  })
  
  // Loading states
  const [isSaving, setIsSaving] = useState(false)
  const [isTesting, setIsTesting] = useState(false)
  const [supportedProviders, setSupportedProviders] = useState<SupportedProvider[]>([])
  const [loadingProviders, setLoadingProviders] = useState(true)

  useEffect(() => {
    if (open) {
      loadSupportedProviders()
      
      if (provider && !isCreating) {
        // Editing existing provider
        setProviderName(provider.provider_name)
        setDisplayName(provider.display_name)
        setIsActive(provider.is_active)
        setIsDefault(provider.is_default)
        
        // Note: We can't load existing credentials as they're encrypted
        // User will need to re-enter them if updating
      } else {
        // Creating new provider
        resetForm()
      }
    }
  }, [open, provider, isCreating])

  const loadSupportedProviders = async () => {
    setLoadingProviders(true)
    try {
      const providers = await signatureService.getSupportedProviders()
      setSupportedProviders(providers)
    } catch (error) {
      console.error('Failed to load supported providers:', error)
    } finally {
      setLoadingProviders(false)
    }
  }

  const resetForm = () => {
    setProviderName('docusign')
    setDisplayName('')
    setIsActive(true)
    setIsDefault(false)
    setDocusignCreds({
      integration_key: '',
      secret_key: '',
      account_id: '',
      base_url: 'https://demo.docusign.net/restapi'
    })
    setYousignCreds({
      api_key: '',
      environment: 'sandbox'
    })
    setSignaturitCreds({
      access_token: '',
      environment: 'sandbox'
    })
  }

  const getCredentials = () => {
    switch (providerName) {
      case 'docusign':
        return docusignCreds
      case 'yousign':
        return yousignCreds
      case 'signaturit':
        return signaturitCreds
      default:
        return {}
    }
  }

  const validateForm = () => {
    if (!displayName.trim()) {
      addNotification({
        type: 'error',
        title: 'Validation Error',
        message: 'Please enter a display name'
      })
      return false
    }

    const creds = getCredentials()
    const requiredFields = getRequiredFields(providerName)
    
    for (const field of requiredFields) {
      if (!creds[field as keyof typeof creds]) {
        addNotification({
          type: 'error',
          title: 'Validation Error',
          message: `Please fill in all required fields`
        })
        return false
      }
    }

    return true
  }

  const getRequiredFields = (provider: string): string[] => {
    const supported = supportedProviders.find(p => p.name === provider)
    return supported?.required_fields || []
  }

  const handleSave = async () => {
    if (!validateForm()) return

    setIsSaving(true)
    try {
      const data: CreateProviderData = {
        provider_name: providerName,
        display_name: displayName,
        credentials: getCredentials(),
        is_active: isActive,
        is_default: isDefault
      }

      if (isCreating) {
        await signatureService.createProvider(data)
        addNotification({
          type: 'success',
          title: 'Provider created',
          message: 'Signature provider has been created successfully'
        })
      } else if (provider) {
        await signatureService.updateProvider(provider.id, data)
        addNotification({
          type: 'success',
          title: 'Provider updated',
          message: 'Signature provider has been updated successfully'
        })
      }

      onSuccess()
      onOpenChange(false)
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: 'Failed to save provider',
        message: error.message || 'An error occurred'
      })
    } finally {
      setIsSaving(false)
    }
  }

  const handleTest = async () => {
    if (!validateForm()) return

    setIsTesting(true)
    try {
      // For new providers, we'll need to create a temporary test
      // This would require a backend endpoint that tests credentials without saving
      addNotification({
        type: 'info',
        title: 'Test connection',
        message: 'Please save the provider first, then test from the providers list'
      })
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: 'Test failed',
        message: error.message || 'Connection test failed'
      })
    } finally {
      setIsTesting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {isCreating ? 'Add Signature Provider' : 'Edit Signature Provider'}
          </DialogTitle>
          <DialogDescription>
            Configure your signature provider integration settings
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Security Notice */}
          <Alert>
            <IconShieldLock className="h-4 w-4" />
            <AlertDescription>
              All credentials are encrypted before storage and transmitted securely.
            </AlertDescription>
          </Alert>

          {/* Provider Type Selection (only for new providers) */}
          {isCreating && (
            <div>
              <Label>Provider Type</Label>
              <Select value={providerName} onValueChange={(value: any) => setProviderName(value)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="docusign">
                    <div className="flex items-center gap-2">
                      <span>📝</span>
                      <span>DocuSign</span>
                    </div>
                  </SelectItem>
                  <SelectItem value="yousign">
                    <div className="flex items-center gap-2">
                      <span>✍️</span>
                      <span>YouSign</span>
                    </div>
                  </SelectItem>
                  <SelectItem value="signaturit">
                    <div className="flex items-center gap-2">
                      <span>🖊️</span>
                      <span>Signaturit</span>
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}

          {/* Display Name */}
          <div>
            <Label htmlFor="displayName">Display Name</Label>
            <Input
              id="displayName"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="e.g., Production DocuSign"
            />
            <p className="text-xs text-muted-foreground mt-1">
              A friendly name to identify this provider configuration
            </p>
          </div>

          {/* Provider-specific Credentials */}
          <Tabs value={providerName} className="w-full">
            <TabsList className="grid w-full grid-cols-3">
              <TabsTrigger value="docusign" disabled={!isCreating && providerName !== 'docusign'}>
                DocuSign
              </TabsTrigger>
              <TabsTrigger value="yousign" disabled={!isCreating && providerName !== 'yousign'}>
                YouSign
              </TabsTrigger>
              <TabsTrigger value="signaturit" disabled={!isCreating && providerName !== 'signaturit'}>
                Signaturit
              </TabsTrigger>
            </TabsList>

            <TabsContent value="docusign" className="space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">DocuSign Credentials</CardTitle>
                  <CardDescription>
                    Find these in your DocuSign admin console under API & Keys
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div>
                    <Label htmlFor="integration_key">Integration Key *</Label>
                    <Input
                      id="integration_key"
                      type="text"
                      value={docusignCreds.integration_key}
                      onChange={(e) => setDocusignCreds({ ...docusignCreds, integration_key: e.target.value })}
                      placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                    />
                  </div>
                  <div>
                    <Label htmlFor="secret_key">Secret Key *</Label>
                    <Input
                      id="secret_key"
                      type="password"
                      value={docusignCreds.secret_key}
                      onChange={(e) => setDocusignCreds({ ...docusignCreds, secret_key: e.target.value })}
                      placeholder="••••••••••••••••"
                    />
                  </div>
                  <div>
                    <Label htmlFor="account_id">Account ID *</Label>
                    <Input
                      id="account_id"
                      type="text"
                      value={docusignCreds.account_id}
                      onChange={(e) => setDocusignCreds({ ...docusignCreds, account_id: e.target.value })}
                      placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                    />
                  </div>
                  <div>
                    <Label htmlFor="base_url">Environment *</Label>
                    <Select 
                      value={docusignCreds.base_url} 
                      onValueChange={(value) => setDocusignCreds({ ...docusignCreds, base_url: value })}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="https://demo.docusign.net/restapi">
                          Sandbox (demo.docusign.net)
                        </SelectItem>
                        <SelectItem value="https://www.docusign.net/restapi">
                          Production (www.docusign.net)
                        </SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="yousign" className="space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">YouSign Credentials</CardTitle>
                  <CardDescription>
                    Find your API key in your YouSign dashboard under API section
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div>
                    <Label htmlFor="yousign_api_key">API Key *</Label>
                    <Input
                      id="yousign_api_key"
                      type="password"
                      value={yousignCreds.api_key}
                      onChange={(e) => setYousignCreds({ ...yousignCreds, api_key: e.target.value })}
                      placeholder="••••••••••••••••"
                    />
                  </div>
                  <div>
                    <Label htmlFor="yousign_env">Environment *</Label>
                    <Select 
                      value={yousignCreds.environment} 
                      onValueChange={(value: 'sandbox' | 'production') => 
                        setYousignCreds({ ...yousignCreds, environment: value })
                      }
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="sandbox">Sandbox</SelectItem>
                        <SelectItem value="production">Production</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="signaturit" className="space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Signaturit Credentials</CardTitle>
                  <CardDescription>
                    Generate an access token in your Signaturit account settings
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div>
                    <Label htmlFor="signaturit_token">Access Token *</Label>
                    <Input
                      id="signaturit_token"
                      type="password"
                      value={signaturitCreds.access_token}
                      onChange={(e) => setSignaturitCreds({ ...signaturitCreds, access_token: e.target.value })}
                      placeholder="••••••••••••••••"
                    />
                  </div>
                  <div>
                    <Label htmlFor="signaturit_env">Environment *</Label>
                    <Select 
                      value={signaturitCreds.environment} 
                      onValueChange={(value: 'sandbox' | 'production') => 
                        setSignaturitCreds({ ...signaturitCreds, environment: value })
                      }
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="sandbox">Sandbox</SelectItem>
                        <SelectItem value="production">Production</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>

          {/* Status Settings */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <Label htmlFor="active">Active</Label>
                <p className="text-xs text-muted-foreground">
                  Enable this provider for signature requests
                </p>
              </div>
              <Switch
                id="active"
                checked={isActive}
                onCheckedChange={setIsActive}
              />
            </div>
            
            <div className="flex items-center justify-between">
              <div>
                <Label htmlFor="default">Set as Default</Label>
                <p className="text-xs text-muted-foreground">
                  Use this provider by default for new requests
                </p>
              </div>
              <Switch
                id="default"
                checked={isDefault}
                onCheckedChange={setIsDefault}
              />
            </div>
          </div>

          {/* Info Alert */}
          <Alert>
            <IconInfoCircle className="h-4 w-4" />
            <AlertDescription>
              {isCreating 
                ? "After creating the provider, you can test the connection from the providers list."
                : "If you're updating credentials, you'll need to re-enter all credential fields."}
            </AlertDescription>
          </Alert>
        </div>

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={isSaving}>
            {isSaving ? (
              <>
                <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <IconKey className="mr-2 h-4 w-4" />
                {isCreating ? 'Create Provider' : 'Update Provider'}
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}