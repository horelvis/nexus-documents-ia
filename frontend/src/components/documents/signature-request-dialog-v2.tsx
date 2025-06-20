"use client"

import { useState, useEffect } from "react"
import { useParams } from "next/navigation"
import { useForm, useFieldArray } from "react-hook-form"
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
import { Textarea } from "@/components/ui/textarea"
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Slider } from "@/components/ui/slider"
import { 
  IconLoader2, 
  IconPlus, 
  IconTrash, 
  IconAlertCircle,
  IconRobot,
  IconUser,
  IconMail,
  IconHash,
  IconCalendar,
  IconFileText
} from "@tabler/icons-react"
import { Document as ApiDocument } from "@/lib/types"
import { SignatureProvider } from "@/lib/services/signature-service"
import { useSignatureService } from "@/lib/services/signature-service.hooks"
import { useNotifications } from "@/contexts/notifications-context"
import { useAgentService } from "@/lib/services/agent.service"
import { 
  signatureRequestSchema, 
  SignatureRequestFormData,
  SignerFormData 
} from "@/lib/schemas/signature-request"

interface SignatureRequestDialogProps {
  document: ApiDocument | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function SignatureRequestDialogV2({
  document,
  open,
  onOpenChange,
}: SignatureRequestDialogProps) {
  const params = useParams()
  const tenantId = params.tenantId as string
  const { addNotification } = useNotifications()
  const agentService = useAgentService()
  const signatureService = useSignatureService()
  
  // Provider state
  const [providers, setProviders] = useState<SignatureProvider[]>([])
  const [loadingProviders, setLoadingProviders] = useState(true)
  
  // AI state
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [aiSuggestions, setAiSuggestions] = useState<any>(null)
  const [activeTab, setActiveTab] = useState("manual")
  
  // Request state
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitAction, setSubmitAction] = useState<"send" | "draft">("send")

  // Initialize React Hook Form with Zod validation
  const form = useForm<SignatureRequestFormData>({
    resolver: zodResolver(signatureRequestSchema),
    defaultValues: {
      title: "",
      message: "",
      signers: [{ email: "", name: "", role: "signer", order: 1 }],
      expires_in_days: 30,
      provider_id: "",
      document_id: document?.id || "",
    },
  })

  // Field array for dynamic signers
  const { fields, append, remove, update } = useFieldArray({
    control: form.control,
    name: "signers",
  })

  // Load providers on mount
  useEffect(() => {
    if (open) {
      loadProviders()
      resetForm()
    }
  }, [open])

  // Set default values when document changes
  useEffect(() => {
    if (document && open) {
      form.setValue("title", `Signature Request for ${document.title || document.filename}`)
      form.setValue("document_id", document.id)
    }
  }, [document, open])

  const loadProviders = async () => {
    setLoadingProviders(true)
    try {
      const providerList = await signatureService.getProviders()
      setProviders(providerList)
      
      // Select default provider
      const defaultProvider = providerList.find(p => p.is_default) || providerList.find(p => p.is_active)
      if (defaultProvider) {
        form.setValue("provider_id", defaultProvider.id)
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
      title: document ? `Signature Request for ${document.title || document.filename}` : "",
      message: "",
      signers: [{ email: "", name: "", role: "signer", order: 1 }],
      expires_in_days: 30,
      provider_id: "",
      document_id: document?.id || "",
    })
    setActiveTab("manual")
    setAiSuggestions(null)
  }

  const analyzeWithAI = async () => {
    if (!document) return

    setIsAnalyzing(true)
    try {
      // Call the digital signature agent to analyze the document
      const agent = await agentService.getAgentByType('digital_signature')
      if (!agent) {
        throw new Error('Digital signature agent not available')
      }

      const response = await agentService.executeAgent(agent.id, {
        action: 'analyze_for_signature',
        document_id: document.id,
        document_title: document.title || document.filename,
        document_content: 'Document content analysis requested'
      })

      // Parse AI suggestions
      if (response.result) {
        const suggestions = {
          message: response.result.suggested_message || generateDefaultMessage(),
          signers: response.result.suggested_signers || [],
          expires_in_days: response.result.suggested_expiry || 30,
          requirements: response.result.requirements || []
        }
        
        setAiSuggestions(suggestions)
        
        // Apply suggestions to form
        if (suggestions.message) {
          form.setValue("message", suggestions.message)
        }
        if (suggestions.signers.length > 0) {
          // Replace all signers with AI suggestions
          form.setValue("signers", suggestions.signers.map((s: any, i: number) => ({
            email: s.email || "",
            name: s.name || "",
            role: s.role || "signer",
            order: i + 1
          })))
        }
        if (suggestions.expires_in_days) {
          form.setValue("expires_in_days", suggestions.expires_in_days)
        }
        
        setActiveTab("ai")
        
        addNotification({
          type: 'success',
          title: 'AI Analysis Complete',
          message: 'Document analyzed successfully'
        })
      }
    } catch (error) {
      // Fallback to local analysis
      const fallbackMessage = generateDefaultMessage()
      form.setValue("message", fallbackMessage)
      
      setAiSuggestions({
        message: fallbackMessage,
        signers: [{ email: "", name: "", role: "signer", order: 1 }],
        expires_in_days: 30,
        requirements: ["Please review and sign the attached document"]
      })
      
      addNotification({
        type: 'warning',
        title: 'AI Analysis Unavailable',
        message: 'Using default suggestions'
      })
    } finally {
      setIsAnalyzing(false)
    }
  }

  const generateDefaultMessage = () => {
    if (!document) return ""
    
    return `Dear [Signer Name],

Please review and sign the attached document: "${document.title || document.filename}".

This document requires your signature for completion. Please take a moment to review the content carefully before signing.

If you have any questions or concerns, please don't hesitate to reach out.

Best regards,
[Your Name]`
  }

  const onSubmit = async (data: SignatureRequestFormData) => {
    if (!document) return

    setIsSubmitting(true)

    try {
      // Create signature request
      const request = await signatureService.createRequest({
        ...data,
        document_id: document.id,
      })

      if (submitAction === "send") {
        // Send the request immediately
        await signatureService.sendRequest(request.id)
        
        addNotification({
          type: 'success',
          title: 'Signature Request Sent',
          message: `Request sent to ${data.signers.length} signer(s)`
        })
      } else {
        addNotification({
          type: 'success',
          title: 'Draft Saved',
          message: 'Signature request saved as draft'
        })
      }

      onOpenChange(false)
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: submitAction === "send" ? 'Failed to send request' : 'Failed to save draft',
        message: error.message || 'An error occurred'
      })
    } finally {
      setIsSubmitting(false)
    }
  }

  if (!document) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Create Signature Request</DialogTitle>
          <DialogDescription>
            Request signatures for "{document.title || document.filename}"
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            <Tabs value={activeTab} onValueChange={setActiveTab}>
              <TabsList className="grid w-full grid-cols-2">
                <TabsTrigger value="manual" className="flex items-center gap-2">
                  <IconUser className="h-4 w-4" />
                  Manual Setup
                </TabsTrigger>
                <TabsTrigger value="ai" className="flex items-center gap-2">
                  <IconRobot className="h-4 w-4" />
                  AI Assistant
                </TabsTrigger>
              </TabsList>

              <TabsContent value="manual" className="space-y-4">
                {/* Basic Information */}
                <Card>
                  <CardHeader>
                    <CardTitle>Request Details</CardTitle>
                    <CardDescription>Basic information about the signature request</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <FormField
                      control={form.control}
                      name="title"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Title</FormLabel>
                          <FormControl>
                            <Input 
                              placeholder="Enter request title" 
                              {...field} 
                              icon={<IconFileText className="h-4 w-4" />}
                            />
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
                          <FormLabel>Message (Optional)</FormLabel>
                          <FormControl>
                            <Textarea
                              placeholder="Add a message for the signers..."
                              className="min-h-[120px]"
                              {...field}
                            />
                          </FormControl>
                          <FormDescription>
                            This message will be included in the signature request email
                          </FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <div className="grid grid-cols-2 gap-4">
                      <FormField
                        control={form.control}
                        name="provider_id"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>Signature Provider</FormLabel>
                            <Select 
                              onValueChange={field.onChange} 
                              value={field.value}
                              disabled={loadingProviders}
                            >
                              <FormControl>
                                <SelectTrigger>
                                  <SelectValue placeholder="Select a provider" />
                                </SelectTrigger>
                              </FormControl>
                              <SelectContent>
                                {providers.map((provider) => (
                                  <SelectItem key={provider.id} value={provider.id}>
                                    <div className="flex items-center justify-between w-full">
                                      <span>{provider.display_name}</span>
                                      {provider.is_default && (
                                        <Badge variant="secondary" className="ml-2">
                                          Default
                                        </Badge>
                                      )}
                                    </div>
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
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
                              <div className="space-y-2">
                                <div className="flex items-center space-x-2">
                                  <Slider
                                    min={1}
                                    max={365}
                                    step={1}
                                    value={[field.value]}
                                    onValueChange={(value) => field.onChange(value[0])}
                                    className="flex-1"
                                  />
                                  <Input
                                    type="number"
                                    {...field}
                                    className="w-20"
                                    onChange={(e) => field.onChange(parseInt(e.target.value) || 1)}
                                  />
                                </div>
                              </div>
                            </FormControl>
                            <FormDescription>
                              Request will expire after {field.value} days
                            </FormDescription>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    </div>
                  </CardContent>
                </Card>

                {/* Signers */}
                <Card>
                  <CardHeader>
                    <CardTitle>Signers</CardTitle>
                    <CardDescription>Add people who need to sign this document</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {fields.map((field, index) => (
                      <div key={field.id} className="space-y-4 p-4 border rounded-lg">
                        <div className="flex items-center justify-between">
                          <Badge variant="outline">
                            Signer {index + 1}
                          </Badge>
                          {fields.length > 1 && (
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              onClick={() => remove(index)}
                            >
                              <IconTrash className="h-4 w-4" />
                            </Button>
                          )}
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                          <FormField
                            control={form.control}
                            name={`signers.${index}.name`}
                            render={({ field }) => (
                              <FormItem>
                                <FormLabel>Name</FormLabel>
                                <FormControl>
                                  <Input 
                                    placeholder="John Doe" 
                                    {...field}
                                    icon={<IconUser className="h-4 w-4" />}
                                  />
                                </FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />

                          <FormField
                            control={form.control}
                            name={`signers.${index}.email`}
                            render={({ field }) => (
                              <FormItem>
                                <FormLabel>Email</FormLabel>
                                <FormControl>
                                  <Input 
                                    type="email"
                                    placeholder="john@example.com" 
                                    {...field}
                                    icon={<IconMail className="h-4 w-4" />}
                                  />
                                </FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                          <FormField
                            control={form.control}
                            name={`signers.${index}.role`}
                            render={({ field }) => (
                              <FormItem>
                                <FormLabel>Role</FormLabel>
                                <Select onValueChange={field.onChange} value={field.value}>
                                  <FormControl>
                                    <SelectTrigger>
                                      <SelectValue />
                                    </SelectTrigger>
                                  </FormControl>
                                  <SelectContent>
                                    <SelectItem value="signer">Signer</SelectItem>
                                    <SelectItem value="approver">Approver</SelectItem>
                                    <SelectItem value="viewer">Viewer</SelectItem>
                                  </SelectContent>
                                </Select>
                                <FormMessage />
                              </FormItem>
                            )}
                          />

                          <FormField
                            control={form.control}
                            name={`signers.${index}.phone`}
                            render={({ field }) => (
                              <FormItem>
                                <FormLabel>Phone (Optional)</FormLabel>
                                <FormControl>
                                  <Input 
                                    placeholder="+1234567890" 
                                    {...field}
                                  />
                                </FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                        </div>
                      </div>
                    ))}

                    {fields.length < 10 && (
                      <Button
                        type="button"
                        variant="outline"
                        onClick={() => append({ 
                          email: "", 
                          name: "", 
                          role: "signer", 
                          order: fields.length + 1 
                        })}
                        className="w-full"
                      >
                        <IconPlus className="h-4 w-4 mr-2" />
                        Add Signer
                      </Button>
                    )}
                  </CardContent>
                </Card>
              </TabsContent>

              <TabsContent value="ai" className="space-y-4">
                {!aiSuggestions ? (
                  <Card>
                    <CardContent className="flex flex-col items-center justify-center py-8">
                      <IconRobot className="h-12 w-12 text-muted-foreground mb-4" />
                      <p className="text-muted-foreground mb-4">
                        Let AI analyze your document and suggest signers
                      </p>
                      <Button
                        type="button"
                        onClick={analyzeWithAI}
                        disabled={isAnalyzing}
                      >
                        {isAnalyzing ? (
                          <>
                            <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                            Analyzing Document...
                          </>
                        ) : (
                          <>
                            <IconRobot className="mr-2 h-4 w-4" />
                            Analyze with AI
                          </>
                        )}
                      </Button>
                    </CardContent>
                  </Card>
                ) : (
                  <>
                    <Alert>
                      <IconAlertCircle className="h-4 w-4" />
                      <AlertDescription>
                        AI has analyzed your document and provided suggestions below. 
                        You can edit them before sending the request.
                      </AlertDescription>
                    </Alert>

                    {aiSuggestions.requirements && aiSuggestions.requirements.length > 0 && (
                      <Card>
                        <CardHeader>
                          <CardTitle>Document Requirements</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <ul className="list-disc list-inside space-y-1">
                            {aiSuggestions.requirements.map((req: string, i: number) => (
                              <li key={i} className="text-sm text-muted-foreground">
                                {req}
                              </li>
                            ))}
                          </ul>
                        </CardContent>
                      </Card>
                    )}

                    <Button
                      type="button"
                      variant="outline"
                      onClick={analyzeWithAI}
                      disabled={isAnalyzing}
                      className="w-full"
                    >
                      <IconRobot className="mr-2 h-4 w-4" />
                      Re-analyze Document
                    </Button>
                  </>
                )}
              </TabsContent>
            </Tabs>

            {/* Form errors summary */}
            {Object.keys(form.formState.errors).length > 0 && (
              <Alert variant="destructive">
                <IconAlertCircle className="h-4 w-4" />
                <AlertDescription>
                  Please fix the errors above before submitting
                </AlertDescription>
              </Alert>
            )}

            <DialogFooter className="gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={isSubmitting}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                variant="outline"
                disabled={isSubmitting}
                onClick={() => setSubmitAction("draft")}
              >
                {isSubmitting && submitAction === "draft" ? (
                  <>
                    <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                    Saving...
                  </>
                ) : (
                  "Save as Draft"
                )}
              </Button>
              <Button
                type="submit"
                disabled={isSubmitting}
                onClick={() => setSubmitAction("send")}
              >
                {isSubmitting && submitAction === "send" ? (
                  <>
                    <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                    Sending...
                  </>
                ) : (
                  "Create & Send"
                )}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}