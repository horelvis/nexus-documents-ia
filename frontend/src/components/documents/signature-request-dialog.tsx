"use client"

import { useState, useEffect } from "react"
import { useParams } from "next/navigation"
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
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
import { SignatureProvider, SignatureRequestSigner } from "@/lib/services/signature-service"
import { useSignatureService } from "@/lib/services/signature-service.hooks"
import { useNotifications } from "@/contexts/notifications-context"
import { useAgentService } from "@/lib/services/agent.service"

interface SignatureRequestDialogProps {
  document: ApiDocument | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function SignatureRequestDialog({
  document,
  open,
  onOpenChange,
}: SignatureRequestDialogProps) {
  const params = useParams()
  const tenantId = params.tenantId as string
  const { addNotification } = useNotifications()
  const agentService = useAgentService()
  const signatureService = useSignatureService()
  
  // Form state
  const [title, setTitle] = useState("")
  const [message, setMessage] = useState("")
  const [signers, setSigners] = useState<Omit<SignatureRequestSigner, 'status' | 'signed_at'>[]>([
    { email: "", name: "", role: "signer", order: 1 }
  ])
  const [expiresInDays, setExpiresInDays] = useState(30)
  const [activeTab, setActiveTab] = useState("manual")
  
  // Provider state
  const [providers, setProviders] = useState<SignatureProvider[]>([])
  const [selectedProviderId, setSelectedProviderId] = useState<string>("")
  const [loadingProviders, setLoadingProviders] = useState(true)
  
  // AI state
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [aiSuggestions, setAiSuggestions] = useState<any>(null)
  
  // Request state
  const [isCreating, setIsCreating] = useState(false)
  const [isSending, setIsSending] = useState(false)

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
      setTitle(`Signature Request for ${document.title || document.filename}`)
    }
  }, [document, open])

  const loadProviders = async () => {
    setLoadingProviders(true)
    try {
      const providerList = await signatureService.getProviders()
      setProviders(providerList)
      
      // Select first active provider
      const activeProvider = providerList.find(p => p.is_active)
      if (activeProvider) {
        setSelectedProviderId(activeProvider.id)
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
    setTitle("")
    setMessage("")
    setSigners([{ email: "", name: "", role: "signer", order: 1 }])
    setExpiresInDays(30)
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
        if (suggestions.message) setMessage(suggestions.message)
        if (suggestions.signers.length > 0) setSigners(suggestions.signers)
        if (suggestions.expires_in_days) setExpiresInDays(suggestions.expires_in_days)
        
        setActiveTab("ai")
        
        addNotification({
          type: 'success',
          title: 'AI Analysis Complete',
          message: 'Document analyzed successfully'
        })
      }
    } catch (error) {
      // Fallback to local analysis
      const fallbackSuggestions = {
        message: generateDefaultMessage(),
        signers: [{ email: "", name: "", role: "signer", order: 1 }],
        expires_in_days: 30,
        requirements: ["Please review and sign the attached document"]
      }
      
      setAiSuggestions(fallbackSuggestions)
      setMessage(fallbackSuggestions.message)
      
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

  const addSigner = () => {
    setSigners([
      ...signers,
      { 
        email: "", 
        name: "", 
        role: "signer", 
        order: signers.length + 1 
      }
    ])
  }

  const removeSigner = (index: number) => {
    const newSigners = signers.filter((_, i) => i !== index)
    // Update order numbers
    setSigners(newSigners.map((signer, i) => ({
      ...signer,
      order: i + 1
    })))
  }

  const updateSigner = (index: number, field: string, value: string) => {
    const newSigners = [...signers]
    newSigners[index] = { ...newSigners[index], [field]: value }
    setSigners(newSigners)
  }

  const validateForm = () => {
    if (!title.trim()) {
      addNotification({
        type: 'error',
        title: 'Validation Error',
        message: 'Please enter a title for the signature request'
      })
      return false
    }

    if (!selectedProviderId) {
      addNotification({
        type: 'error',
        title: 'Validation Error',
        message: 'Please select a signature provider'
      })
      return false
    }

    const validSigners = signers.filter(s => s.email && s.name)
    if (validSigners.length === 0) {
      addNotification({
        type: 'error',
        title: 'Validation Error',
        message: 'Please add at least one signer with email and name'
      })
      return false
    }

    return true
  }

  const handleCreateAndSend = async () => {
    if (!document || !validateForm()) return

    setIsCreating(true)
    setIsSending(true)

    try {
      // Filter out empty signers
      const validSigners = signers.filter(s => s.email && s.name)

      // Create signature request
      const request = await signatureService.createRequest({
        title,
        message,
        document_id: document.id,
        provider_id: selectedProviderId,
        signers: validSigners,
        expires_in_days: expiresInDays
      })

      // Send the request immediately
      await signatureService.sendRequest(request.id)

      addNotification({
        type: 'success',
        title: 'Signature Request Sent',
        message: `Request sent to ${validSigners.length} signer(s)`
      })

      onOpenChange(false)
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: 'Failed to send request',
        message: error.message || 'An error occurred'
      })
    } finally {
      setIsCreating(false)
      setIsSending(false)
    }
  }

  const handleSaveDraft = async () => {
    if (!document || !validateForm()) return

    setIsCreating(true)

    try {
      // Filter out empty signers
      const validSigners = signers.filter(s => s.email && s.name)

      // Create signature request as draft
      await signatureService.createRequest({
        title,
        message,
        document_id: document.id,
        provider_id: selectedProviderId,
        signers: validSigners,
        expires_in_days: expiresInDays
      })

      addNotification({
        type: 'success',
        title: 'Draft Saved',
        message: 'Signature request saved as draft'
      })

      onOpenChange(false)
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: 'Failed to save draft',
        message: error.message || 'An error occurred'
      })
    } finally {
      setIsCreating(false)
    }
  }

  if (!document) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Request Signature</DialogTitle>
          <DialogDescription>
            Configure and send a signature request for "{document.title || document.filename}"
          </DialogDescription>
        </DialogHeader>

        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="manual">
              <IconUser className="mr-2 h-4 w-4" />
              Manual Setup
            </TabsTrigger>
            <TabsTrigger value="ai">
              <IconRobot className="mr-2 h-4 w-4" />
              AI Assistant
            </TabsTrigger>
          </TabsList>

          <TabsContent value="manual" className="space-y-4">
            {/* Provider Selection */}
            <div>
              <Label htmlFor="provider">Signature Provider</Label>
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
                <Select value={selectedProviderId} onValueChange={setSelectedProviderId}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select a provider" />
                  </SelectTrigger>
                  <SelectContent>
                    {providers.map((provider) => (
                      <SelectItem key={provider.id} value={provider.id}>
                        <div className="flex items-center gap-2">
                          <span>{provider.name}</span>
                          <Badge variant="outline" className="text-xs">
                            {provider.type}
                          </Badge>
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>

            {/* Title */}
            <div>
              <Label htmlFor="title">Request Title</Label>
              <Input
                id="title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g., Contract Signature Request"
              />
            </div>

            {/* Message */}
            <div>
              <Label htmlFor="message">Message to Signers (Optional)</Label>
              <Textarea
                id="message"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="Add a personal message to the signers..."
                rows={4}
              />
            </div>

            {/* Signers */}
            <div>
              <Label>Signers</Label>
              <div className="space-y-2">
                {signers.map((signer, index) => (
                  <Card key={index}>
                    <CardContent className="pt-4">
                      <div className="grid grid-cols-12 gap-2">
                        <div className="col-span-1 flex items-center justify-center">
                          <Badge variant="outline">
                            <IconHash className="h-3 w-3 mr-1" />
                            {signer.order}
                          </Badge>
                        </div>
                        <div className="col-span-4">
                          <Input
                            placeholder="Email"
                            type="email"
                            value={signer.email}
                            onChange={(e) => updateSigner(index, 'email', e.target.value)}
                          />
                        </div>
                        <div className="col-span-3">
                          <Input
                            placeholder="Name"
                            value={signer.name}
                            onChange={(e) => updateSigner(index, 'name', e.target.value)}
                          />
                        </div>
                        <div className="col-span-3">
                          <Select
                            value={signer.role}
                            onValueChange={(value) => updateSigner(index, 'role', value)}
                          >
                            <SelectTrigger>
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="signer">Signer</SelectItem>
                              <SelectItem value="approver">Approver</SelectItem>
                              <SelectItem value="viewer">Viewer</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                        <div className="col-span-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => removeSigner(index)}
                            disabled={signers.length === 1}
                          >
                            <IconTrash className="h-4 w-4" />
                          </Button>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))}
                <Button variant="outline" onClick={addSigner} className="w-full">
                  <IconPlus className="mr-2 h-4 w-4" />
                  Add Signer
                </Button>
              </div>
            </div>

            {/* Expiration */}
            <div>
              <Label htmlFor="expires">Expires In (Days)</Label>
              <Input
                id="expires"
                type="number"
                min="1"
                max="365"
                value={expiresInDays}
                onChange={(e) => setExpiresInDays(parseInt(e.target.value) || 30)}
              />
            </div>
          </TabsContent>

          <TabsContent value="ai" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <IconRobot className="h-5 w-5" />
                  AI Document Analysis
                </CardTitle>
                <CardDescription>
                  Let AI analyze your document and suggest signature requirements
                </CardDescription>
              </CardHeader>
              <CardContent>
                {!aiSuggestions ? (
                  <div className="text-center py-8">
                    <IconFileText className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
                    <p className="text-sm text-muted-foreground mb-4">
                      AI can analyze your document to extract signer information and suggest appropriate settings
                    </p>
                    <Button onClick={analyzeWithAI} disabled={isAnalyzing}>
                      {isAnalyzing ? (
                        <>
                          <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                          Analyzing...
                        </>
                      ) : (
                        <>
                          <IconRobot className="mr-2 h-4 w-4" />
                          Analyze Document
                        </>
                      )}
                    </Button>
                  </div>
                ) : (
                  <div className="space-y-4">
                    <Alert>
                      <IconRobot className="h-4 w-4" />
                      <AlertDescription>
                        AI has analyzed your document. Review and modify the suggestions below.
                      </AlertDescription>
                    </Alert>

                    {aiSuggestions.requirements && aiSuggestions.requirements.length > 0 && (
                      <div>
                        <Label>Document Requirements</Label>
                        <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
                          {aiSuggestions.requirements.map((req: string, i: number) => (
                            <li key={i}>{req}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    <div className="pt-4">
                      <Button 
                        onClick={() => setActiveTab("manual")} 
                        variant="outline"
                        className="w-full"
                      >
                        Review & Edit Settings
                      </Button>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button 
            variant="outline" 
            onClick={handleSaveDraft}
            disabled={isCreating || !selectedProviderId}
          >
            {isCreating && !isSending ? (
              <>
                <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                Saving...
              </>
            ) : (
              'Save as Draft'
            )}
          </Button>
          <Button 
            onClick={handleCreateAndSend}
            disabled={isCreating || !selectedProviderId}
          >
            {isSending ? (
              <>
                <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                Sending...
              </>
            ) : (
              <>
                <IconMail className="mr-2 h-4 w-4" />
                Send Request
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}