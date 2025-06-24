"use client"

import { useState, useEffect } from "react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
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
import { Textarea } from "@/components/ui/textarea"
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { 
  IconLoader2, 
  IconPlus, 
  IconTrash, 
  IconAlertCircle,
  IconUser,
  IconMail,
  IconChevronLeft,
  IconChevronRight,
  IconCheck,
  IconFileText,
  IconSignature
} from "@tabler/icons-react"
import { Document as ApiDocument } from "@/lib/types"
import { SignatureProvider } from "@/lib/services/signature-service"
import { useSignatureService } from "@/lib/services/signature-service.hooks"
import { useNotifications } from "@/contexts/app-state-context"
import { SignaturePlacementEditor } from "./signature-placement-editor"
import { cn } from "@/lib/utils"
import { useSignatureAI } from "@/lib/services/signature-ai-service"

// Zod schemas
const signerSchema = z.object({
  email: z.string().email("Invalid email address"),
  name: z.string().min(1, "Name is required"),
  color: z.string(),
})

const signatureRequestSchema = z.object({
  title: z.string().min(1, "Title is required").max(200, "Title too long"),
  message: z.string().max(1000, "Message too long").optional(),
  signers: z.array(signerSchema)
    .min(1, "At least one signer is required")
    .max(10, "Maximum 10 signers allowed"),
  provider_id: z.string().uuid("Please select a valid provider"),
  expires_in_days: z.number()
    .min(1, "Minimum 1 day")
    .max(365, "Maximum 365 days")
    .default(30),
  document_id: z.string().uuid(),
})

type SignatureRequestFormData = z.infer<typeof signatureRequestSchema>

interface SignatureRequestDialogV2Props {
  document: ApiDocument | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

const STEPS = ['Signers', 'Placement', 'Settings', 'Review']
const SIGNER_COLORS = [
  '#3B82F6', // blue
  '#10B981', // green
  '#F59E0B', // amber
  '#EF4444', // red
  '#8B5CF6', // purple
  '#EC4899', // pink
  '#14B8A6', // teal
  '#F97316', // orange
]

export function SignatureRequestDialogV2({
  document,
  open,
  onOpenChange,
}: SignatureRequestDialogV2Props) {
  const { addNotification } = useNotifications()
  const signatureService = useSignatureService()
  const { analyzeDocument, suggestPlacements, learnFromPlacement, isAnalyzing, analysis, signatureAIService } = useSignatureAI()
  
  const [currentStep, setCurrentStep] = useState(0)
  const [providers, setProviders] = useState<SignatureProvider[]>([])
  const [loadingProviders, setLoadingProviders] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [signatureFields, setSignatureFields] = useState<any[]>([])
  const [isLoadingAISuggestions, setIsLoadingAISuggestions] = useState(false)
  
  const form = useForm<SignatureRequestFormData>({
    resolver: zodResolver(signatureRequestSchema),
    defaultValues: {
      title: "",
      message: "",
      signers: [{ email: "", name: "", color: SIGNER_COLORS[0] }],
      expires_in_days: 30,
      provider_id: "",
      document_id: document?.id || "",
    },
  })

  // Load providers on mount
  useEffect(() => {
    if (open) {
      loadProviders()
      resetForm()
    }
  }, [open])

  // Set default title when document changes
  useEffect(() => {
    if (document && open) {
      form.setValue('title', `Signature Request for ${document.title || document.filename}`)
      form.setValue('document_id', document.id)
    }
  }, [document, open])

  const loadProviders = async () => {
    setLoadingProviders(true)
    try {
      const providerList = await signatureService.getProviders()
      setProviders(providerList)
      
      // Select default provider
      const defaultProvider = providerList.find(p => p.is_active && p.is_default)
      const activeProvider = defaultProvider || providerList.find(p => p.is_active)
      if (activeProvider) {
        form.setValue('provider_id', activeProvider.id)
      }
    } catch (error) {
      addNotification({
        type: 'error',
        title: 'Failed to load providers',
        message: 'Could not load signature providers'
      })
    } finally {
      setLoadingProviders(false)
    }
  }

  const resetForm = () => {
    form.reset({
      title: "",
      message: "",
      signers: [{ email: "", name: "", color: SIGNER_COLORS[0] }],
      expires_in_days: 30,
      provider_id: "",
      document_id: document?.id || "",
    })
    setCurrentStep(0)
    setSignatureFields([])
  }

  const handleNext = async () => {
    // Validate current step
    let fieldsToValidate: (keyof SignatureRequestFormData)[] = []
    
    switch (currentStep) {
      case 0: // Signers
        fieldsToValidate = ['signers']
        break
      case 1: // Placement
        // Check if signature fields are placed
        if (signatureFields.length === 0) {
          addNotification({
            type: 'error',
            title: 'No signature fields',
            message: 'Please place at least one signature field on the document'
          })
          return
        }
        
        // Validate that each signer has at least one required field
        const signers = form.getValues('signers')
        const signersWithFields = new Set(signatureFields.filter(f => f.required).map(f => f.signer))
        const signersWithoutFields = signers.filter((_, index) => !signersWithFields.has(`signer-${index}`))
        
        if (signersWithoutFields.length > 0) {
          addNotification({
            type: 'error',
            title: 'Missing required fields',
            message: `The following signers need at least one required field: ${signersWithoutFields.map(s => s.name || s.email).join(', ')}`
          })
          return
        }
        break
      case 2: // Settings
        fieldsToValidate = ['title', 'provider_id', 'expires_in_days']
        break
    }
    
    if (fieldsToValidate.length > 0) {
      const isValid = await form.trigger(fieldsToValidate)
      if (!isValid) return
    }
    
    // Load AI suggestions when moving to placement step
    if (currentStep === 0 && document) {
      await loadAISuggestions()
    }
    
    setCurrentStep(prev => Math.min(STEPS.length - 1, prev + 1))
  }

  const handleBack = () => {
    setCurrentStep(prev => Math.max(0, prev - 1))
  }

  const handleAddSigner = () => {
    const currentSigners = form.getValues('signers')
    if (currentSigners.length >= 10) {
      addNotification({
        type: 'error',
        title: 'Maximum signers reached',
        message: 'You can add up to 10 signers'
      })
      return
    }
    
    const nextColor = SIGNER_COLORS[currentSigners.length % SIGNER_COLORS.length]
    form.setValue('signers', [...currentSigners, { email: "", name: "", color: nextColor }])
  }

  const handleRemoveSigner = (index: number) => {
    const currentSigners = form.getValues('signers')
    form.setValue('signers', currentSigners.filter((_, i) => i !== index))
  }

  const loadAISuggestions = async () => {
    if (!document || signatureFields.length > 0) return // Don't override existing fields
    
    setIsLoadingAISuggestions(true)
    try {
      // Analyze document if not already done
      let documentAnalysis = analysis
      if (!documentAnalysis) {
        documentAnalysis = await analyzeDocument(document.id, {
          filename: document.filename,
          category: document.category
        })
      }
      
      // Get signers with formatted data
      const signers = form.getValues('signers').map((s, i) => ({
        id: `signer-${i}`,
        email: s.email,
        name: s.name,
        role: `party_${i + 1}`
      }))
      
      // Get AI suggestions
      const suggestions = await suggestPlacements(document.id, signers, documentAnalysis)
      
      // Convert suggestions to placement editor format
      const aiFields = signatureAIService.convertSuggestionsToFields(
        suggestions.suggested_fields,
        signers.map((s, i) => ({
          ...s,
          color: form.getValues('signers')[i].color
        }))
      )
      
      setSignatureFields(aiFields)
      
      // Notify user about AI suggestions
      if (aiFields.length > 0) {
        addNotification({
          type: 'success',
          title: 'AI Suggestions Ready',
          message: `Placed ${aiFields.length} suggested signature fields. You can adjust them as needed.`
        })
      }
    } catch (error) {
      console.error('Failed to load AI suggestions:', error)
      // Don't show error to user - AI suggestions are optional
    } finally {
      setIsLoadingAISuggestions(false)
    }
  }

  const onSubmit = async (data: SignatureRequestFormData) => {
    if (!document) return

    setIsSubmitting(true)
    try {
      // Create signature request with field placements
      const request = await signatureService.createRequest({
        ...data,
        document_name: document.filename,
        metadata: {
          signature_fields: signatureFields
        }
      })

      // Send immediately
      await signatureService.sendRequest(request.id)

      addNotification({
        type: 'success',
        title: 'Signature Request Sent',
        message: `Request sent to ${data.signers.length} signer(s)`
      })

      // Submit placement data for AI learning (async, don't wait)
      if (signatureFields.length > 0 && analysis) {
        learnFromPlacement({
          document_id: document.id,
          document_type: analysis.document_type,
          placed_fields: signatureFields
        })
      }

      onOpenChange(false)
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: 'Failed to send request',
        message: error.message || 'An error occurred'
      })
    } finally {
      setIsSubmitting(false)
    }
  }

  const renderStepContent = () => {
    switch (currentStep) {
      case 0: // Signers
        return (
          <div className="space-y-4">
            <FormField
              control={form.control}
              name="signers"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Signers</FormLabel>
                  <FormDescription>
                    Add the people who need to sign this document
                  </FormDescription>
                  <div className="space-y-3">
                    {field.value.map((signer, index) => (
                      <Card key={index}>
                        <CardContent className="pt-4">
                          <div className="flex items-start gap-3">
                            <div 
                              className="w-10 h-10 rounded-full flex items-center justify-center text-white font-semibold"
                              style={{ backgroundColor: signer.color }}
                            >
                              {index + 1}
                            </div>
                            <div className="flex-1 space-y-3">
                              <div className="grid grid-cols-2 gap-3">
                                <div>
                                  <Input
                                    placeholder="Name"
                                    value={signer.name}
                                    onChange={(e) => {
                                      const updated = [...field.value]
                                      updated[index].name = e.target.value
                                      field.onChange(updated)
                                    }}
                                  />
                                  {form.formState.errors.signers?.[index]?.name && (
                                    <p className="text-xs text-destructive mt-1">
                                      {form.formState.errors.signers[index].name?.message}
                                    </p>
                                  )}
                                </div>
                                <div>
                                  <Input
                                    type="email"
                                    placeholder="Email"
                                    value={signer.email}
                                    onChange={(e) => {
                                      const updated = [...field.value]
                                      updated[index].email = e.target.value
                                      field.onChange(updated)
                                    }}
                                  />
                                  {form.formState.errors.signers?.[index]?.email && (
                                    <p className="text-xs text-destructive mt-1">
                                      {form.formState.errors.signers[index].email?.message}
                                    </p>
                                  )}
                                </div>
                              </div>
                            </div>
                            {field.value.length > 1 && (
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                onClick={() => handleRemoveSigner(index)}
                              >
                                <IconTrash className="h-4 w-4" />
                              </Button>
                            )}
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={handleAddSigner}
                    className="w-full"
                  >
                    <IconPlus className="h-4 w-4 mr-2" />
                    Add Signer
                  </Button>
                  <FormMessage />
                </FormItem>
              )}
            />
          </div>
        )
        
      case 1: // Placement
        const signers = form.getValues('signers').map((s, i) => ({
          id: `signer-${i}`,
          ...s
        }))
        
        return (
          <div className="space-y-4">
            <div>
              <h3 className="text-sm font-medium mb-2">Place Signature Fields</h3>
              <p className="text-sm text-muted-foreground">
                Drag and drop fields onto the document where signers need to sign
              </p>
              {isLoadingAISuggestions && (
                <div className="flex items-center gap-2 mt-2 text-sm text-muted-foreground">
                  <IconLoader2 className="h-4 w-4 animate-spin" />
                  Loading AI suggestions...
                </div>
              )}
              {signatureFields.some(f => f.aiSuggested) && (
                <div className="flex items-center gap-2 mt-2">
                  <Badge variant="secondary" className="text-xs">
                    AI Suggested
                  </Badge>
                  <span className="text-xs text-muted-foreground">
                    Fields have been placed based on document analysis. You can adjust as needed.
                  </span>
                </div>
              )}
            </div>
            <SignaturePlacementEditor
              documentUrl={`/api/v1/documents/${document?.id}/preview`}
              signers={signers}
              onFieldsChange={setSignatureFields}
              initialFields={signatureFields}
            />
          </div>
        )
        
      case 2: // Settings
        return (
          <div className="space-y-4">
            <FormField
              control={form.control}
              name="title"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Request Title</FormLabel>
                  <FormControl>
                    <Input {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="message"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Message to Signers (Optional)</FormLabel>
                  <FormControl>
                    <Textarea 
                      {...field} 
                      rows={4}
                      placeholder="Add a personal message to your signers..."
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="provider_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Signature Provider</FormLabel>
                  {loadingProviders ? (
                    <div className="flex items-center justify-center p-4">
                      <IconLoader2 className="h-4 w-4 animate-spin" />
                    </div>
                  ) : providers.length === 0 ? (
                    <Alert>
                      <IconAlertCircle className="h-4 w-4" />
                      <AlertDescription>
                        No signature providers configured. Please contact your administrator.
                      </AlertDescription>
                    </Alert>
                  ) : (
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select a provider" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {providers
                          .sort((a, b) => {
                            if (a.is_default && !b.is_default) return -1
                            if (!a.is_default && b.is_default) return 1
                            return a.display_name.localeCompare(b.display_name)
                          })
                          .map((provider) => (
                            <SelectItem key={provider.id} value={provider.id}>
                              <div className="flex items-center justify-between gap-2 w-full">
                                <span>{provider.display_name}</span>
                                <div className="flex items-center gap-1">
                                  {provider.is_default && (
                                    <Badge variant="default" className="text-xs">
                                      Default
                                    </Badge>
                                  )}
                                  <Badge variant="outline" className="text-xs">
                                    {provider.provider_name}
                                  </Badge>
                                </div>
                              </div>
                            </SelectItem>
                          ))}
                      </SelectContent>
                    </Select>
                  )}
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="expires_in_days"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Expires In (Days)</FormLabel>
                  <FormControl>
                    <Input 
                      type="number" 
                      {...field} 
                      onChange={e => field.onChange(parseInt(e.target.value))}
                    />
                  </FormControl>
                  <FormDescription>
                    How many days until this signature request expires
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
          </div>
        )
        
      case 3: // Review
        const formData = form.getValues()
        return (
          <div className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Request Summary</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <p className="text-sm text-muted-foreground">Document</p>
                  <p className="font-medium">{document?.title || document?.filename}</p>
                </div>
                
                <div>
                  <p className="text-sm text-muted-foreground">Title</p>
                  <p className="font-medium">{formData.title}</p>
                </div>
                
                <div>
                  <p className="text-sm text-muted-foreground mb-2">Signers ({formData.signers.length})</p>
                  <div className="space-y-2">
                    {formData.signers.map((signer, i) => (
                      <div key={i} className="flex items-center gap-2">
                        <div 
                          className="w-6 h-6 rounded-full"
                          style={{ backgroundColor: signer.color }}
                        />
                        <span className="text-sm">{signer.name} ({signer.email})</span>
                      </div>
                    ))}
                  </div>
                </div>
                
                <div>
                  <p className="text-sm text-muted-foreground">Signature Fields</p>
                  <p className="font-medium">{signatureFields.length} fields placed</p>
                </div>
                
                <div>
                  <p className="text-sm text-muted-foreground">Provider</p>
                  <p className="font-medium">
                    {providers.find(p => p.id === formData.provider_id)?.display_name}
                  </p>
                </div>
                
                <div>
                  <p className="text-sm text-muted-foreground">Expires In</p>
                  <p className="font-medium">{formData.expires_in_days} days</p>
                </div>
              </CardContent>
            </Card>
          </div>
        )
    }
  }

  if (!document) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-6xl max-h-[90vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle>Request Signature</DialogTitle>
          <DialogDescription>
            Configure and send a signature request for "{document.title || document.filename}"
          </DialogDescription>
        </DialogHeader>

        {/* Progress */}
        <div className="py-4">
          <div className="flex items-center justify-between mb-2">
            {STEPS.map((step, index) => (
              <div
                key={step}
                className={cn(
                  "flex items-center",
                  index < STEPS.length - 1 && "flex-1"
                )}
              >
                <div
                  className={cn(
                    "w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium",
                    index <= currentStep
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted text-muted-foreground"
                  )}
                >
                  {index < currentStep ? (
                    <IconCheck className="h-4 w-4" />
                  ) : (
                    index + 1
                  )}
                </div>
                <span className="ml-2 text-sm font-medium">{step}</span>
                {index < STEPS.length - 1 && (
                  <div
                    className={cn(
                      "flex-1 h-0.5 mx-4",
                      index < currentStep ? "bg-primary" : "bg-muted"
                    )}
                  />
                )}
              </div>
            ))}
          </div>
        </div>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="flex-1 overflow-y-auto">
            <div className="px-1">
              {renderStepContent()}
            </div>
          </form>
        </Form>

        <DialogFooter className="gap-2 mt-4">
          {currentStep > 0 && (
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
          
          {currentStep < STEPS.length - 1 ? (
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
              onClick={form.handleSubmit(onSubmit)}
              className="ml-auto"
            >
              {isSubmitting ? (
                <>
                  <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                  Sending...
                </>
              ) : (
                <>
                  <IconSignature className="mr-2 h-4 w-4" />
                  Send for Signature
                </>
              )}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}