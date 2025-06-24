"use client"

import { useState, useEffect } from "react"
import { useForm, Controller } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
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
import { Switch } from "@/components/ui/switch"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import { 
  IconLoader2, 
  IconAlertCircle, 
  IconCheck,
  IconKey,
  IconLink,
  IconWebhook,
  IconShieldCheck,
  IconInfoCircle
} from "@tabler/icons-react"
import { SignatureProvider } from "@/lib/services/signature-service"
import { useSignatureService } from "@/lib/services/signature-service.hooks"
import { useNotifications } from "@/contexts/app-state-context"
import { 
  signatureProviderSchema, 
  SignatureProviderFormData,
  ProviderType,
  providerTypeEnum,
  providerValidationMessages
} from "@/lib/schemas/signature-provider"

interface ProviderConfigDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  provider?: SignatureProvider | null
  onSuccess?: () => void
}

const providerInfo = {
  docusign: {
    name: "DocuSign",
    description: "Industry leader in e-signatures with advanced features",
    icon: "🏆",
    features: ["Advanced workflows", "Mobile support", "API integrations", "Compliance certifications"],
    setupUrl: "https://developers.docusign.com/",
  },
  yousign: {
    name: "YouSign",
    description: "European e-signature solution with GDPR compliance",
    icon: "🇪🇺",
    features: ["GDPR compliant", "Simple API", "Affordable pricing", "EU data hosting"],
    setupUrl: "https://developers.yousign.com/",
  },
  signaturit: {
    name: "Signaturit",
    description: "Simple and secure e-signature platform",
    icon: "✍️",
    features: ["Easy integration", "Multi-language", "Certified delivery", "Bulk sending"],
    setupUrl: "https://docs.signaturit.com/",
  },
}

export function ProviderConfigDialogV2({
  open,
  onOpenChange,
  provider,
  onSuccess,
}: ProviderConfigDialogProps) {
  const { addNotification } = useNotifications()
  const signatureService = useSignatureService()
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isTesting, setIsTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null)
  const [selectedProvider, setSelectedProvider] = useState<ProviderType | null>(null)

  // Initialize form with proper typing
  const form = useForm<SignatureProviderFormData>({
    resolver: zodResolver(signatureProviderSchema),
    defaultValues: {
      providerName: "yousign",
      displayName: "",
      isActive: true,
      isDefault: false,
      credentials: {},
    },
  })

  // Watch provider type changes
  const watchedProvider = form.watch("providerName")

  // Set initial values when editing
  useEffect(() => {
    if (provider) {
      // When editing, set the provider type and values
      const providerData: SignatureProviderFormData = {
        providerName: provider.provider_name as ProviderType,
        displayName: provider.display_name,
        isActive: provider.is_active,
        isDefault: provider.is_default,
        credentials: {}, // Will be empty for security
      }
      form.reset(providerData)
      setSelectedProvider(provider.provider_name as ProviderType)
    } else {
      // When creating new, reset to defaults
      form.reset({
        providerName: "yousign",
        displayName: "",
        isActive: true,
        isDefault: false,
        credentials: {},
      })
      setSelectedProvider("yousign")
    }
  }, [provider, open])

  // Update selected provider when form value changes
  useEffect(() => {
    setSelectedProvider(watchedProvider)
  }, [watchedProvider])

  const handleProviderChange = (value: ProviderType) => {
    // Reset form with new provider type
    form.reset({
      providerName: value,
      displayName: providerInfo[value].name,
      isActive: true,
      isDefault: false,
      credentials: {},
    })
    setTestResult(null)
  }

  const handleTestConnection = async () => {
    const formData = form.getValues()
    
    // Validate credentials before testing
    const result = await form.trigger("credentials")
    if (!result) {
      addNotification({
        type: 'error',
        title: 'Invalid Credentials',
        message: 'Please fill in all required credential fields'
      })
      return
    }

    setIsTesting(true)
    setTestResult(null)

    try {
      let testProviderId = provider?.id

      // If creating new provider, we need to create it first to test
      if (!provider) {
        const newProvider = await signatureService.createProvider({
          provider_name: formData.providerName,
          display_name: formData.displayName || providerInfo[formData.providerName].name,
          credentials: formData.credentials,
          is_active: false, // Create as inactive for testing
          is_default: false,
        })
        testProviderId = newProvider.id
      }

      if (!testProviderId) {
        throw new Error('No provider ID available for testing')
      }

      const result = await signatureService.testConnection(testProviderId)
      setTestResult(result)

      if (result.success) {
        addNotification({
          type: 'success',
          title: 'Connection Successful',
          message: result.message || 'Provider connection test passed'
        })
      } else {
        addNotification({
          type: 'error',
          title: 'Connection Failed',
          message: result.message || 'Could not connect to provider'
        })
      }

      // If we created a temporary provider and test failed, delete it
      if (!provider && !result.success && testProviderId) {
        await signatureService.deleteProvider(testProviderId)
      }
    } catch (error: any) {
      setTestResult({ success: false, message: error.message })
      addNotification({
        type: 'error',
        title: 'Test Failed',
        message: error.message || 'Failed to test connection'
      })
    } finally {
      setIsTesting(false)
    }
  }

  const onSubmit = async (data: SignatureProviderFormData) => {
    setIsSubmitting(true)

    try {
      if (provider) {
        // Update existing provider
        await signatureService.updateProvider(provider.id, {
          provider_name: data.providerName,
          display_name: data.displayName,
          credentials: Object.keys(data.credentials).length > 0 ? data.credentials : undefined,
          is_active: data.isActive,
          is_default: data.isDefault,
        })
        
        addNotification({
          type: 'success',
          title: 'Provider Updated',
          message: 'Signature provider configuration updated successfully'
        })
      } else {
        // Create new provider
        await signatureService.createProvider({
          provider_name: data.providerName,
          display_name: data.displayName,
          credentials: data.credentials,
          is_active: data.isActive,
          is_default: data.isDefault,
        })
        
        addNotification({
          type: 'success',
          title: 'Provider Added',
          message: 'New signature provider added successfully'
        })
      }

      onSuccess?.()
      onOpenChange(false)
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: provider ? 'Update Failed' : 'Creation Failed',
        message: error.message || 'An error occurred'
      })
    } finally {
      setIsSubmitting(false)
    }
  }

  const renderCredentialsFields = () => {
    if (!selectedProvider) return null

    const info = providerInfo[selectedProvider]
    const messages = providerValidationMessages[selectedProvider]

    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <IconKey className="h-5 w-5" />
            API Credentials
          </CardTitle>
          <CardDescription>
            Enter your {info.name} API credentials. 
            <a 
              href={info.setupUrl} 
              target="_blank" 
              rel="noopener noreferrer"
              className="text-primary hover:underline ml-1"
            >
              Get credentials →
            </a>
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {selectedProvider === "docusign" && (
            <>
              <FormField
                control={form.control}
                name="credentials.integration_key"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Integration Key</FormLabel>
                    <FormControl>
                      <Input 
                        type="password"
                        placeholder="Enter integration key" 
                        {...field}
                      />
                    </FormControl>
                    <FormDescription>
                      {messages.integration_key}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="credentials.secret_key"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Secret Key</FormLabel>
                    <FormControl>
                      <Input 
                        type="password"
                        placeholder="Enter secret key" 
                        {...field}
                      />
                    </FormControl>
                    <FormDescription>
                      {messages.secret_key}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="credentials.account_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Account ID</FormLabel>
                    <FormControl>
                      <Input 
                        placeholder="Enter account ID" 
                        {...field}
                      />
                    </FormControl>
                    <FormDescription>
                      {messages.account_id}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="credentials.environment"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Environment</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="sandbox">Sandbox (Testing)</SelectItem>
                        <SelectItem value="production">Production</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </>
          )}

          {selectedProvider === "yousign" && (
            <>
              <FormField
                control={form.control}
                name="credentials.api_key"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>API Key</FormLabel>
                    <FormControl>
                      <Input 
                        type="password"
                        placeholder="Enter API key" 
                        {...field}
                      />
                    </FormControl>
                    <FormDescription>
                      {messages.api_key}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="credentials.environment"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Environment</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="sandbox">Sandbox (Testing)</SelectItem>
                        <SelectItem value="production">Production</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="credentials.webhook_secret"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Webhook Secret (Optional)</FormLabel>
                    <FormControl>
                      <Input 
                        type="password"
                        placeholder="Enter webhook secret" 
                        {...field}
                      />
                    </FormControl>
                    <FormDescription>
                      {messages.webhook_secret}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </>
          )}

          {selectedProvider === "signaturit" && (
            <>
              <FormField
                control={form.control}
                name="credentials.access_token"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Access Token</FormLabel>
                    <FormControl>
                      <Input 
                        type="password"
                        placeholder="Enter access token" 
                        {...field}
                      />
                    </FormControl>
                    <FormDescription>
                      {messages.access_token}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="credentials.environment"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Environment</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="sandbox">Sandbox (Testing)</SelectItem>
                        <SelectItem value="production">Production</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="credentials.webhook_secret"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Webhook Secret (Optional)</FormLabel>
                    <FormControl>
                      <Input 
                        type="password"
                        placeholder="Enter webhook secret" 
                        {...field}
                      />
                    </FormControl>
                    <FormDescription>
                      {messages.webhook_secret}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </>
          )}

          {/* Test Connection Button */}
          <div className="pt-4">
            <Button
              type="button"
              variant="outline"
              onClick={handleTestConnection}
              disabled={isTesting || isSubmitting}
              className="w-full"
            >
              {isTesting ? (
                <>
                  <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                  Testing Connection...
                </>
              ) : (
                <>
                  <IconLink className="mr-2 h-4 w-4" />
                  Test Connection
                </>
              )}
            </Button>

            {testResult && (
              <Alert className={`mt-4 ${testResult.success ? 'border-green-500' : 'border-destructive'}`}>
                {testResult.success ? (
                  <IconCheck className="h-4 w-4 text-green-500" />
                ) : (
                  <IconAlertCircle className="h-4 w-4" />
                )}
                <AlertTitle>{testResult.success ? 'Success' : 'Failed'}</AlertTitle>
                <AlertDescription>{testResult.message}</AlertDescription>
              </Alert>
            )}
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {provider ? 'Edit Provider Configuration' : 'Add Signature Provider'}
          </DialogTitle>
          <DialogDescription>
            Configure a signature provider to enable document signing capabilities
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            {/* Provider Selection (only for new providers) */}
            {!provider && (
              <Card>
                <CardHeader>
                  <CardTitle>Select Provider</CardTitle>
                  <CardDescription>Choose your e-signature provider</CardDescription>
                </CardHeader>
                <CardContent>
                  <FormField
                    control={form.control}
                    name="providerName"
                    render={({ field }) => (
                      <FormItem>
                        <FormControl>
                          <div className="grid grid-cols-1 gap-4">
                            {Object.entries(providerInfo).map(([key, info]) => (
                              <div
                                key={key}
                                className={`p-4 border rounded-lg cursor-pointer transition-all ${
                                  field.value === key 
                                    ? 'border-primary bg-primary/5' 
                                    : 'border-border hover:border-primary/50'
                                }`}
                                onClick={() => handleProviderChange(key as ProviderType)}
                              >
                                <div className="flex items-start gap-3">
                                  <div className="text-2xl">{info.icon}</div>
                                  <div className="flex-1">
                                    <h4 className="font-medium mb-1">{info.name}</h4>
                                    <p className="text-sm text-muted-foreground mb-2">
                                      {info.description}
                                    </p>
                                    <div className="flex flex-wrap gap-2">
                                      {info.features.map((feature, i) => (
                                        <Badge key={i} variant="secondary" className="text-xs">
                                          {feature}
                                        </Badge>
                                      ))}
                                    </div>
                                  </div>
                                  <div className="flex items-center">
                                    <div className={`w-4 h-4 rounded-full border-2 ${
                                      field.value === key 
                                        ? 'border-primary bg-primary' 
                                        : 'border-muted-foreground'
                                    }`} />
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </CardContent>
              </Card>
            )}

            {/* Basic Configuration */}
            <Card>
              <CardHeader>
                <CardTitle>Basic Configuration</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <FormField
                  control={form.control}
                  name="displayName"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Display Name</FormLabel>
                      <FormControl>
                        <Input 
                          placeholder="e.g., Production DocuSign" 
                          {...field}
                        />
                      </FormControl>
                      <FormDescription>
                        A friendly name to identify this provider configuration
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <div className="space-y-4">
                  <FormField
                    control={form.control}
                    name="isActive"
                    render={({ field }) => (
                      <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                        <div className="space-y-0.5">
                          <FormLabel className="text-base">Active</FormLabel>
                          <FormDescription>
                            Enable this provider for signature requests
                          </FormDescription>
                        </div>
                        <FormControl>
                          <Switch
                            checked={field.value}
                            onCheckedChange={field.onChange}
                          />
                        </FormControl>
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="isDefault"
                    render={({ field }) => (
                      <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                        <div className="space-y-0.5">
                          <FormLabel className="text-base">Default Provider</FormLabel>
                          <FormDescription>
                            Use this as the default provider for new requests
                          </FormDescription>
                        </div>
                        <FormControl>
                          <Switch
                            checked={field.value}
                            onCheckedChange={field.onChange}
                          />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                </div>
              </CardContent>
            </Card>

            {/* Credentials */}
            {(selectedProvider || provider) && renderCredentialsFields()}

            {/* Security Notice */}
            <Alert>
              <IconShieldCheck className="h-4 w-4" />
              <AlertTitle>Security Notice</AlertTitle>
              <AlertDescription>
                Your API credentials are encrypted and stored securely. 
                Never share your credentials or commit them to version control.
              </AlertDescription>
            </Alert>

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={isSubmitting}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={isSubmitting}>
                {isSubmitting ? (
                  <>
                    <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                    {provider ? 'Updating...' : 'Creating...'}
                  </>
                ) : (
                  provider ? 'Update Provider' : 'Add Provider'
                )}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}