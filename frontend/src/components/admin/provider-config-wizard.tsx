"use client"

import { useState, useEffect } from "react"
import { useForm } from "react-hook-form"
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
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { 
  IconLoader2, 
  IconCheck,
  IconKey,
  IconSettings,
  IconShieldCheck,
  IconChevronRight,
  IconChevronLeft,
  IconCircleCheck
} from "@tabler/icons-react"
import { SignatureProvider } from "@/lib/services/signature-service"
import { useSignatureService } from "@/lib/services/signature-service.hooks"
import { useNotifications } from "@/contexts/notifications-context"
import { 
  signatureProviderSchema, 
  SignatureProviderFormData,
  ProviderType,
  providerValidationMessages
} from "@/lib/schemas/signature-provider"

interface ProviderConfigWizardProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  provider?: SignatureProvider | null
  onSuccess?: () => void
}

const providerInfo = {
  docusign: {
    name: "DocuSign",
    description: "Industry leader in e-signatures",
    icon: "🏆",
    features: ["Advanced workflows", "Mobile support", "API integrations"],
    setupUrl: "https://developers.docusign.com/",
  },
  yousign: {
    name: "YouSign",
    description: "European e-signature solution",
    icon: "🇪🇺",
    features: ["GDPR compliant", "Simple API", "EU data hosting"],
    setupUrl: "https://developers.yousign.com/",
  },
  signaturit: {
    name: "Signaturit",
    description: "Simple and secure platform",
    icon: "✍️",
    features: ["Easy integration", "Multi-language", "Bulk sending"],
    setupUrl: "https://docs.signaturit.com/",
  },
}

export function ProviderConfigWizard({
  open,
  onOpenChange,
  provider,
  onSuccess,
}: ProviderConfigWizardProps) {
  const { addNotification } = useNotifications()
  const signatureService = useSignatureService()
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [currentStep, setCurrentStep] = useState(1)
  
  const isEditing = !!provider
  const totalSteps = isEditing ? 3 : 4

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

  const watchedProvider = form.watch("providerName")

  useEffect(() => {
    if (provider) {
      form.reset({
        providerName: provider.provider_name as ProviderType,
        displayName: provider.display_name,
        isActive: provider.is_active,
        isDefault: provider.is_default,
        credentials: {},
      })
      setCurrentStep(1)
    } else {
      form.reset({
        providerName: "yousign",
        displayName: "",
        isActive: true,
        isDefault: false,
        credentials: {},
      })
      setCurrentStep(1)
    }
  }, [provider, open])

  const handleNext = async () => {
    let isValid = false
    
    if (currentStep === 1 && !isEditing) {
      isValid = await form.trigger("providerName")
    } else if (currentStep === (isEditing ? 1 : 2)) {
      isValid = await form.trigger("displayName")
    } else if (currentStep === (isEditing ? 2 : 3)) {
      isValid = await form.trigger("credentials")
    }
    
    if (isValid) {
      setCurrentStep(prev => Math.min(totalSteps, prev + 1))
    }
  }

  const handleBack = () => {
    setCurrentStep(prev => Math.max(1, prev - 1))
  }

  const onSubmit = async (data: SignatureProviderFormData) => {
    setIsSubmitting(true)

    try {
      if (provider) {
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
          message: 'Configuration updated successfully'
        })
      } else {
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
          message: 'New provider added successfully'
        })
      }

      onSuccess?.()
      onOpenChange(false)
    } catch (error) {
      addNotification({
        type: 'error',
        title: provider ? 'Update Failed' : 'Creation Failed',
        message: error instanceof Error ? error.message : 'An error occurred'
      })
    } finally {
      setIsSubmitting(false)
    }
  }

  const renderStepContent = () => {
    // Step 1: Provider Selection (only for new providers)
    if (currentStep === 1 && !isEditing) {
      return (
        <div className="space-y-4">
          <div className="text-center mb-4">
            <h3 className="text-lg font-semibold">Choose Your Provider</h3>
            <p className="text-sm text-muted-foreground">Select the e-signature service you want to integrate</p>
          </div>
          
          <FormField
            control={form.control}
            name="providerName"
            render={({ field }) => (
              <FormItem>
                <FormControl>
                  <div className="grid grid-cols-1 gap-3">
                    {Object.entries(providerInfo).map(([key, info]) => (
                      <div
                        key={key}
                        className={`p-4 border-2 rounded-lg cursor-pointer transition-all ${
                          field.value === key 
                            ? 'border-primary bg-primary/5' 
                            : 'border-border hover:border-primary/50'
                        }`}
                        onClick={() => field.onChange(key)}
                      >
                        <div className="flex items-center gap-3">
                          <div className="text-2xl">{info.icon}</div>
                          <div className="flex-1">
                            <h4 className="font-medium">{info.name}</h4>
                            <p className="text-sm text-muted-foreground">{info.description}</p>
                          </div>
                          {field.value === key && (
                            <IconCircleCheck className="h-5 w-5 text-primary" />
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>
      )
    }

    // Step 2: Basic Configuration
    const basicConfigStep = isEditing ? 1 : 2
    if (currentStep === basicConfigStep) {
      return (
        <div className="space-y-4">
          <div className="text-center mb-4">
            <h3 className="text-lg font-semibold">Basic Configuration</h3>
            <p className="text-sm text-muted-foreground">Set up your provider details</p>
          </div>

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
                  A friendly name to identify this configuration
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <div className="grid grid-cols-2 gap-4">
            <FormField
              control={form.control}
              name="isActive"
              render={({ field }) => (
                <FormItem className="flex flex-row items-center justify-between rounded-lg border p-3">
                  <div className="space-y-0.5">
                    <FormLabel className="text-base">Active</FormLabel>
                    <FormDescription className="text-xs">
                      Enable this provider
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
                <FormItem className="flex flex-row items-center justify-between rounded-lg border p-3">
                  <div className="space-y-0.5">
                    <FormLabel className="text-base">Default</FormLabel>
                    <FormDescription className="text-xs">
                      Use as default
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
        </div>
      )
    }

    // Step 3: Credentials
    const credentialsStep = isEditing ? 2 : 3
    if (currentStep === credentialsStep) {
      const selectedProvider = isEditing ? provider.provider_name : watchedProvider
      const info = providerInfo[selectedProvider as ProviderType]
      const messages = providerValidationMessages[selectedProvider as ProviderType]

      return (
        <div className="space-y-4">
          <div className="text-center mb-4">
            <h3 className="text-lg font-semibold">API Credentials</h3>
            <p className="text-sm text-muted-foreground">
              Enter your {info?.name} credentials
            </p>
          </div>

          {selectedProvider === "docusign" && (
            <>
              <FormField
                control={form.control}
                name="credentials.integration_key"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Integration Key</FormLabel>
                    <FormControl>
                      <Input type="password" placeholder="Enter integration key" {...field} />
                    </FormControl>
                    <FormDescription className="text-xs">
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
                      <Input type="password" placeholder="Enter secret key" {...field} />
                    </FormControl>
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
                      <Input placeholder="Enter account ID" {...field} />
                    </FormControl>
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
                        <SelectItem value="sandbox">Sandbox</SelectItem>
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
                      <Input type="password" placeholder="Enter API key" {...field} />
                    </FormControl>
                    <FormDescription className="text-xs">
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
                        <SelectItem value="sandbox">Sandbox</SelectItem>
                        <SelectItem value="production">Production</SelectItem>
                      </SelectContent>
                    </Select>
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
                      <Input type="password" placeholder="Enter access token" {...field} />
                    </FormControl>
                    <FormDescription className="text-xs">
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
                        <SelectItem value="sandbox">Sandbox</SelectItem>
                        <SelectItem value="production">Production</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </>
          )}

          <Alert>
            <IconShieldCheck className="h-4 w-4" />
            <AlertDescription className="text-xs">
              Credentials are encrypted and stored securely
            </AlertDescription>
          </Alert>
        </div>
      )
    }

    // Step 4: Review (only for new providers)
    if (currentStep === 4 && !isEditing) {
      const formData = form.getValues()
      const info = providerInfo[formData.providerName]

      return (
        <div className="space-y-4">
          <div className="text-center mb-4">
            <h3 className="text-lg font-semibold">Review Configuration</h3>
            <p className="text-sm text-muted-foreground">Confirm your settings before saving</p>
          </div>

          <Card>
            <CardContent className="pt-6 space-y-4">
              <div className="flex items-center gap-3">
                <div className="text-2xl">{info.icon}</div>
                <div>
                  <p className="font-medium">{info.name}</p>
                  <p className="text-sm text-muted-foreground">{formData.displayName}</p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4 pt-4 border-t">
                <div>
                  <p className="text-sm text-muted-foreground">Status</p>
                  <Badge variant={formData.isActive ? "default" : "secondary"}>
                    {formData.isActive ? "Active" : "Inactive"}
                  </Badge>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Default Provider</p>
                  <Badge variant={formData.isDefault ? "default" : "secondary"}>
                    {formData.isDefault ? "Yes" : "No"}
                  </Badge>
                </div>
              </div>

              <div className="pt-4 border-t">
                <p className="text-sm text-muted-foreground mb-2">Credentials</p>
                <div className="flex items-center gap-2">
                  <IconKey className="h-4 w-4 text-green-500" />
                  <span className="text-sm">Configured</span>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>
            {provider ? 'Edit Provider' : 'Add Signature Provider'}
          </DialogTitle>
          <DialogDescription>
            Step {currentStep} of {totalSteps}
          </DialogDescription>
        </DialogHeader>

        <Progress value={(currentStep / totalSteps) * 100} className="mb-4" />

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)}>
            <div className="min-h-[350px]">
              {renderStepContent()}
            </div>

            <DialogFooter className="mt-6 gap-2">
              {currentStep > 1 && (
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleBack}
                  disabled={isSubmitting}
                >
                  <IconChevronLeft className="mr-2 h-4 w-4" />
                  Back
                </Button>
              )}
              
              {currentStep < totalSteps ? (
                <Button
                  type="button"
                  onClick={handleNext}
                  disabled={isSubmitting}
                  className="ml-auto"
                >
                  Next
                  <IconChevronRight className="ml-2 h-4 w-4" />
                </Button>
              ) : (
                <Button
                  type="submit"
                  disabled={isSubmitting}
                  className="ml-auto"
                >
                  {isSubmitting ? (
                    <>
                      <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                      {provider ? 'Updating...' : 'Creating...'}
                    </>
                  ) : (
                    <>
                      <IconCheck className="mr-2 h-4 w-4" />
                      {provider ? 'Update' : 'Create'} Provider
                    </>
                  )}
                </Button>
              )}
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}