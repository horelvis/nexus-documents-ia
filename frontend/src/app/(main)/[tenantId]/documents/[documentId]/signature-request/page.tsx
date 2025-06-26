"use client"

import { useState, useEffect, useRef } from "react"
import { useParams, useRouter } from "next/navigation"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
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
  IconSignature,
  IconArrowLeft
} from "@tabler/icons-react"
import { Document as ApiDocument } from "@/lib/types"
import { SignatureProvider } from "@/lib/services/signature-service"
import { useSignatureService } from "@/lib/services/signature-service.hooks"
import { useDocumentService } from "@/lib/services/document.service"
import { useNotifications } from "@/contexts/app-state-context"
import { SignaturePlacementEditor } from "@/components/documents/signature-placement-editor"
import { cn } from "@/lib/utils"
import { useSignatureAI } from "@/lib/services/signature-ai-service"
import { EntitySearchMenu } from "@/components/documents/entity-search-menu"

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

export default function SignatureRequestPage() {
  const params = useParams()
  const router = useRouter()
  const tenantId = params.tenantId as string
  const documentId = params.documentId as string

  const { addNotification } = useNotifications()
  const signatureService = useSignatureService()
  const documentService = useDocumentService()
  const { analyzeDocument, suggestPlacements, learnFromPlacement, generateMessage, isAnalyzing, analysis, signatureAIService } = useSignatureAI()
  
  const [document, setDocument] = useState<ApiDocument | null>(null)
  const [currentStep, setCurrentStep] = useState(0)
  const [providers, setProviders] = useState<SignatureProvider[]>([])
  const [loadingProviders, setLoadingProviders] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [signatureFields, setSignatureFields] = useState<any[]>([])
  const [isLoadingAISuggestions, setIsLoadingAISuggestions] = useState(false)
  const [isLoadingDocument, setIsLoadingDocument] = useState(true)
  const [entitySearchOpen, setEntitySearchOpen] = useState(false)
  const [entitySearchIndex, setEntitySearchIndex] = useState<number | null>(null)
  const [entitySearchQuery, setEntitySearchQuery] = useState('')
  const nameInputRefs = useRef<(HTMLInputElement | null)[]>([])
  
  const form = useForm<SignatureRequestFormData>({
    resolver: zodResolver(signatureRequestSchema),
    defaultValues: {
      title: "",
      message: "",
      signers: [{ email: "", name: "", color: SIGNER_COLORS[0] }],
      expires_in_days: 30,
      provider_id: "",
      document_id: documentId,
    },
  })

  // Load document
  useEffect(() => {
    loadDocument()
  }, [documentId])

  // Load providers on mount
  useEffect(() => {
    loadProviders()
  }, [])

  // Set default title when document loads
  useEffect(() => {
    if (document) {
      form.setValue('title', `Signature Request for ${document.title || document.filename}`)
      form.setValue('document_id', document.id)
    }
  }, [document])

  const loadDocument = async () => {
    setIsLoadingDocument(true)
    try {
      const response = await documentService.getDocument(documentId)
      console.log('Document response:', response)
      
      if (response.error) {
        console.error('Document load error:', response.error)
        addNotification({
          type: 'error',
          title: 'Failed to load document',
          message: response.error
        })
        router.push(`/${tenantId}/documents`)
        return
      }
      
      if (!response.data) {
        console.error('No document data in response')
        addNotification({
          type: 'error',
          title: 'Document not found',
          message: 'The requested document was not found'
        })
        router.push(`/${tenantId}/documents`)
        return
      }
      
      setDocument(response.data)
    } catch (error) {
      console.error('Document load exception:', error)
      addNotification({
        type: 'error',
        title: 'Failed to load document',
        message: error instanceof Error ? error.message : 'Could not load the document'
      })
      router.push(`/${tenantId}/documents`)
    } finally {
      setIsLoadingDocument(false)
    }
  }

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

  const handleEntitySelect = (entity: any, index: number) => {
    const currentSigners = form.getValues('signers')
    // Replace the @mention with the entity name
    const currentName = currentSigners[index].name
    const atIndex = currentName.lastIndexOf('@')
    if (atIndex !== -1) {
      currentSigners[index].name = currentName.substring(0, atIndex) + entity.name
    } else {
      currentSigners[index].name = entity.name
    }
    currentSigners[index].email = entity.email
    form.setValue('signers', currentSigners)
    setEntitySearchOpen(false)
    setEntitySearchIndex(null)
    setEntitySearchQuery('')
  }

  const handleNameInputChange = (value: string, index: number) => {
    const updated = [...form.getValues('signers')]
    updated[index].name = value
    form.setValue('signers', updated, { shouldValidate: false, shouldDirty: true })
    
    // Check for @ symbol
    if (value.includes('@')) {
      const atIndex = value.lastIndexOf('@')
      const query = value.substring(atIndex + 1)
      
      // Only update search if query actually changed
      if (query !== entitySearchQuery || !entitySearchOpen) {
        setEntitySearchQuery(query)
        setEntitySearchIndex(index)
        setEntitySearchOpen(true)
      }
    } else {
      if (entitySearchOpen) {
        setEntitySearchOpen(false)
        setEntitySearchIndex(null)
        setEntitySearchQuery('')
      }
    }
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

      // Navigate back to documents
      router.push(`/${tenantId}/documents`)
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
          <Card>
            <CardHeader>
              <CardTitle>Add Signers</CardTitle>
              <CardDescription>
                Add the people who need to sign this document
              </CardDescription>
            </CardHeader>
            <CardContent>
              <FormField
                control={form.control}
                name="signers"
                render={({ field }) => (
                  <FormItem>
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
                                  <div className="relative">
                                    <Input
                                      ref={(el) => nameInputRefs.current[index] = el}
                                      placeholder="Name (type @ to search entities)"
                                      value={signer.name}
                                      onChange={(e) => handleNameInputChange(e.target.value, index)}
                                      onKeyDown={(e) => {
                                        if (entitySearchOpen && e.key === 'Escape') {
                                          setEntitySearchOpen(false)
                                          setEntitySearchIndex(null)
                                          setEntitySearchQuery('')
                                        }
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
                      className="w-full mt-4"
                    >
                      <IconPlus className="h-4 w-4 mr-2" />
                      Add Signer
                    </Button>
                    <FormMessage />
                  </FormItem>
                )}
              />
              
              {/* Entity Search Menu */}
              {entitySearchOpen && entitySearchIndex !== null && (
                <EntitySearchMenu
                  open={entitySearchOpen}
                  onSelect={(entity) => handleEntitySelect(entity, entitySearchIndex)}
                  onClose={() => {
                    setEntitySearchOpen(false)
                    setEntitySearchIndex(null)
                    setEntitySearchQuery('')
                  }}
                  searchQuery={entitySearchQuery}
                  anchorRef={nameInputRefs.current[entitySearchIndex]}
                  documentId={document?.id || ''}
                />
              )}
            </CardContent>
          </Card>
        )
        
      case 1: // Placement
        const signers = form.getValues('signers').map((s, i) => ({
          id: `signer-${i}`,
          ...s
        }))
        
        return (
          <Card className="h-full">
            <CardHeader>
              <CardTitle>Place Signature Fields</CardTitle>
              <CardDescription>
                Drag and drop signature fields onto the document where each signer needs to sign
              </CardDescription>
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
            </CardHeader>
            <CardContent className="h-[calc(100%-120px)]">
              <SignaturePlacementEditor
                documentId={document?.id || ''}
                signers={signers}
                onFieldsChange={setSignatureFields}
                initialFields={signatureFields}
              />
            </CardContent>
          </Card>
        )
        
      case 2: // Settings
        return (
          <Card>
            <CardHeader>
              <CardTitle>Request Settings</CardTitle>
              <CardDescription>
                Configure the signature request details
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
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
                    <FormLabel className="flex items-center justify-between">
                      <span>Message to Signers (Optional)</span>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={async () => {
                          const title = form.getValues('title')
                          const signerCount = form.getValues('signers').length
                          const message = await generateMessage(
                            document?.title || document?.filename || 'this document',
                            signerCount,
                            analysis?.document_type
                          )
                          form.setValue('message', message)
                        }}
                        className="text-xs"
                      >
                        <IconSignature className="h-3 w-3 mr-1" />
                        Generate with AI
                      </Button>
                    </FormLabel>
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
            </CardContent>
          </Card>
        )
        
      case 3: // Review
        const formData = form.getValues()
        return (
          <Card>
            <CardHeader>
              <CardTitle>Review Request</CardTitle>
              <CardDescription>
                Review your signature request before sending
              </CardDescription>
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
              
              {formData.message && (
                <div>
                  <p className="text-sm text-muted-foreground">Message</p>
                  <p className="text-sm">{formData.message}</p>
                </div>
              )}
            </CardContent>
          </Card>
        )
    }
  }

  if (isLoadingDocument) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-200px)]">
        <div className="text-center">
          <IconLoader2 className="h-8 w-8 animate-spin mx-auto mb-4" />
          <p>Loading document...</p>
        </div>
      </div>
    )
  }

  if (!document) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-200px)]">
        <div className="text-center">
          <IconAlertCircle className="h-8 w-8 text-destructive mx-auto mb-4" />
          <p>Document not found</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-[calc(100vh-100px)]">
      {/* Header */}
      <div className="px-6 py-4 border-b">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => router.push(`/${tenantId}/documents`)}
            >
              <IconArrowLeft className="h-4 w-4 mr-2" />
              Back to Documents
            </Button>
            <div>
              <h1 className="text-2xl font-bold">Request Signature</h1>
              <p className="text-sm text-muted-foreground">
                {document.title || document.filename}
              </p>
            </div>
          </div>
          
          {/* Progress */}
          <div className="flex items-center gap-8">
            {STEPS.map((step, index) => (
              <div
                key={step}
                className={cn(
                  "flex items-center gap-2"
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
                <span className={cn(
                  "text-sm font-medium",
                  index <= currentStep ? "text-foreground" : "text-muted-foreground"
                )}>
                  {step}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-6">
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="h-full">
            {renderStepContent()}
          </form>
        </Form>
      </div>

      {/* Footer */}
      <div className="px-6 py-4 border-t bg-background">
        <div className="flex justify-between">
          <Button
            type="button"
            variant="outline"
            onClick={handleBack}
            disabled={currentStep === 0 || isSubmitting}
          >
            <IconChevronLeft className="mr-2 h-4 w-4" />
            Back
          </Button>
          
          {currentStep < STEPS.length - 1 ? (
            <Button
              type="button"
              onClick={handleNext}
              disabled={isSubmitting}
            >
              Next
              <IconChevronRight className="ml-2 h-4 w-4" />
            </Button>
          ) : (
            <Button
              type="submit"
              disabled={isSubmitting}
              onClick={form.handleSubmit(onSubmit)}
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
        </div>
      </div>
    </div>
  )
}