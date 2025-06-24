'use client'

import { useState, useEffect, useCallback } from 'react'
import { Plus, Minus, FileText, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { useToast } from '@/hooks/use-toast'
import { useSignatureService } from '@/lib/services/signature-service.hooks'
import { useDocumentService } from '@/lib/services/document.service'
import { SignatureProvider, SignatureRequestSigner } from '@/lib/services/signature-service'
import { DocumentSearchCombobox } from '@/components/ui/document-search-combobox'

interface CreateSignatureRequestDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  tenantId: string
  documentId?: string
  onSuccess?: () => void
}

export function CreateSignatureRequestDialog({
  open,
  onOpenChange,
  tenantId,
  documentId: preselectedDocumentId,
  onSuccess,
}: CreateSignatureRequestDialogProps) {
  const { toast } = useToast()
  const signatureService = useSignatureService()
  const documentService = useDocumentService()

  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isLoadingProviders, setIsLoadingProviders] = useState(true)
  const [isLoadingDocuments, setIsLoadingDocuments] = useState(true)
  const [providers, setProviders] = useState<SignatureProvider[]>([])
  const [documents, setDocuments] = useState<any[]>([])
  const [searchTerm, setSearchTerm] = useState('')
  const [formData, setFormData] = useState({
    title: '',
    message: '',
    document_id: preselectedDocumentId || '',
    provider_id: '',
    expires_in_days: 30,
  })
  const [signers, setSigners] = useState<Omit<SignatureRequestSigner, 'status' | 'signed_at'>[]>([
    { email: '', name: '', order: 1, role: 'signer' },
  ])

  const loadProviders = async () => {
    setIsLoadingProviders(true)
    try {
      const data = await signatureService.getProviders()
      const activeProviders = data.filter(p => p.is_active)
      setProviders(activeProviders)
      
      // Set default provider
      const defaultProvider = activeProviders.find(p => p.is_default) || activeProviders[0]
      if (defaultProvider && !formData.provider_id) {
        setFormData(prev => ({ ...prev, provider_id: defaultProvider.id }))
      }
    } catch (err: any) {
      toast({
        title: 'Error',
        description: 'Failed to load signature providers',
        variant: 'destructive',
      })
    } finally {
      setIsLoadingProviders(false)
    }
  }

  const loadDocuments = useCallback(async (search?: string) => {
    setIsLoadingDocuments(true)
    try {
      const params: any = {
        limit: 50,
        mime_type: 'application/pdf'
      }
      
      if (search) {
        params.search = search
      }
      
      const response = await documentService.getDocuments(params)
      const data = response.data?.items || []
      // Filter only PDF documents (in case mime_type filter isn't supported)
      const pdfDocuments = data.filter(doc => 
        doc.mime_type === 'application/pdf' || doc.filename.toLowerCase().endsWith('.pdf')
      )
      setDocuments(pdfDocuments)
    } catch (err: any) {
      toast({
        title: 'Error',
        description: 'Failed to load documents',
        variant: 'destructive',
      })
    } finally {
      setIsLoadingDocuments(false)
    }
  }, [documentService, toast])
  
  // Debounced search handler
  const handleDocumentSearch = useCallback((search: string) => {
    setSearchTerm(search)
    // Load documents with search term after a short delay
    const timer = setTimeout(() => {
      loadDocuments(search)
    }, 300)
    
    return () => clearTimeout(timer)
  }, [loadDocuments])

  // Load providers and documents
  useEffect(() => {
    if (open) {
      loadProviders()
      loadDocuments()
    }
  }, [open, loadDocuments])

  const addSigner = () => {
    setSigners(prev => [
      ...prev,
      { email: '', name: '', order: prev.length + 1, role: 'signer' },
    ])
  }

  const removeSigner = (index: number) => {
    setSigners(prev => {
      const updated = prev.filter((_, i) => i !== index)
      // Update order numbers
      return updated.map((signer, i) => ({ ...signer, order: i + 1 }))
    })
  }

  const updateSigner = (index: number, field: string, value: string) => {
    setSigners(prev => 
      prev.map((signer, i) => 
        i === index ? { ...signer, [field]: value } : signer
      )
    )
  }

  const handleSubmit = async () => {
    // Validate form
    if (!formData.title.trim()) {
      toast({
        title: 'Error',
        description: 'Please enter a title for the signature request',
        variant: 'destructive',
      })
      return
    }

    if (!formData.document_id) {
      toast({
        title: 'Error',
        description: 'Please select a document',
        variant: 'destructive',
      })
      return
    }

    if (!formData.provider_id) {
      toast({
        title: 'Error',
        description: 'Please select a signature provider',
        variant: 'destructive',
      })
      return
    }

    // Validate signers
    const validSigners = signers.filter(s => s.email && s.name)
    if (validSigners.length === 0) {
      toast({
        title: 'Error',
        description: 'Please add at least one signer with email and name',
        variant: 'destructive',
      })
      return
    }

    // Check for duplicate emails
    const emails = validSigners.map(s => s.email.toLowerCase())
    const uniqueEmails = new Set(emails)
    if (emails.length !== uniqueEmails.size) {
      toast({
        title: 'Error',
        description: 'Each signer must have a unique email address',
        variant: 'destructive',
      })
      return
    }

    setIsSubmitting(true)

    try {
      const selectedDocument = documents.find(d => d.id === formData.document_id)
      
      await signatureService.createRequest({
        title: formData.title,
        message: formData.message || undefined,
        document_id: formData.document_id,
        document_name: selectedDocument?.filename || 'document.pdf',
        provider_id: formData.provider_id,
        signers: validSigners,
        expires_in_days: formData.expires_in_days,
      })

      toast({
        title: 'Success',
        description: 'Signature request created successfully',
      })

      // Reset form
      setFormData({
        title: '',
        message: '',
        document_id: preselectedDocumentId || '',
        provider_id: providers.find(p => p.is_default)?.id || '',
        expires_in_days: 30,
      })
      setSigners([{ email: '', name: '', order: 1, role: 'signer' }])

      onSuccess?.()
    } catch (err: any) {
      toast({
        title: 'Error',
        description: err.message || 'Failed to create signature request',
        variant: 'destructive',
      })
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh]">
        <DialogHeader>
          <DialogTitle>Create Signature Request</DialogTitle>
          <DialogDescription>
            Create a new digital signature request for a document
          </DialogDescription>
        </DialogHeader>

        <ScrollArea className="max-h-[60vh] pr-4">
          <div className="space-y-6">
            {/* Provider Selection */}
            {providers.length === 0 && !isLoadingProviders ? (
              <Alert>
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>
                  No active signature providers found. Please configure a provider first.
                </AlertDescription>
              </Alert>
            ) : (
              <div className="space-y-2">
                <Label htmlFor="provider">Signature Provider</Label>
                {isLoadingProviders ? (
                  <Skeleton className="h-10 w-full" />
                ) : (
                  <Select
                    value={formData.provider_id}
                    onValueChange={(value) => setFormData(prev => ({ ...prev, provider_id: value }))}
                  >
                    <SelectTrigger id="provider">
                      <SelectValue placeholder="Select a provider" />
                    </SelectTrigger>
                    <SelectContent>
                      {providers.map((provider) => (
                        <SelectItem key={provider.id} value={provider.id}>
                          {provider.display_name}
                          {provider.is_default && ' (Default)'}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              </div>
            )}

            {/* Document Selection */}
            <div className="space-y-2">
              <Label htmlFor="document">Document</Label>
              {documents.length === 0 && !isLoadingDocuments && !searchTerm ? (
                <Alert>
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription>
                    No PDF documents found. Please upload a PDF document first.
                  </AlertDescription>
                </Alert>
              ) : (
                <DocumentSearchCombobox
                  value={formData.document_id}
                  onValueChange={(value) => setFormData(prev => ({ ...prev, document_id: value }))}
                  placeholder="Search and select a PDF document..."
                  disabled={!!preselectedDocumentId}
                  documents={documents}
                  isLoading={isLoadingDocuments}
                  onSearch={handleDocumentSearch}
                />
              )}
            </div>

            {/* Title */}
            <div className="space-y-2">
              <Label htmlFor="title">Title</Label>
              <Input
                id="title"
                placeholder="e.g., Contract Agreement - Q4 2024"
                value={formData.title}
                onChange={(e) => setFormData(prev => ({ ...prev, title: e.target.value }))}
              />
            </div>

            {/* Message */}
            <div className="space-y-2">
              <Label htmlFor="message">Message (Optional)</Label>
              <Textarea
                id="message"
                placeholder="Add a message for the signers..."
                value={formData.message}
                onChange={(e) => setFormData(prev => ({ ...prev, message: e.target.value }))}
                rows={3}
              />
            </div>

            {/* Expiration */}
            <div className="space-y-2">
              <Label htmlFor="expires">Expires in (days)</Label>
              <Input
                id="expires"
                type="number"
                min="1"
                max="365"
                value={formData.expires_in_days}
                onChange={(e) => setFormData(prev => ({ 
                  ...prev, 
                  expires_in_days: parseInt(e.target.value) || 30 
                }))}
              />
            </div>

            {/* Signers */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <Label>Signers</Label>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={addSigner}
                >
                  <Plus className="h-4 w-4 mr-1" />
                  Add Signer
                </Button>
              </div>
              
              <div className="space-y-3">
                {signers.map((signer, index) => (
                  <div key={index} className="flex gap-2 items-start">
                    <div className="flex-1 space-y-2">
                      <Input
                        placeholder="Signer name"
                        value={signer.name}
                        onChange={(e) => updateSigner(index, 'name', e.target.value)}
                      />
                      <Input
                        type="email"
                        placeholder="Email address"
                        value={signer.email}
                        onChange={(e) => updateSigner(index, 'email', e.target.value)}
                      />
                    </div>
                    <Select
                      value={signer.role}
                      onValueChange={(value) => updateSigner(index, 'role', value)}
                    >
                      <SelectTrigger className="w-[120px]">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="signer">Signer</SelectItem>
                        <SelectItem value="viewer">Viewer</SelectItem>
                        <SelectItem value="approver">Approver</SelectItem>
                      </SelectContent>
                    </Select>
                    {signers.length > 1 && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        onClick={() => removeSigner(index)}
                      >
                        <Minus className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </ScrollArea>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isSubmitting}
          >
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={isSubmitting || isLoadingProviders || isLoadingDocuments || providers.length === 0}
          >
            {isSubmitting ? 'Creating...' : 'Create Request'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}