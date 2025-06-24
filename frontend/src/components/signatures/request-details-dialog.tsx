'use client'

import { useState } from 'react'
import { 
  FileText, 
  User, 
  Calendar, 
  Clock, 
  Send, 
  Download, 
  RefreshCw,
  CheckCircle,
  XCircle,
  AlertCircle,
  Mail,
  Eye
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { useToast } from '@/hooks/use-toast'
import { useSignatureService } from '@/lib/services/signature-service.hooks'
import { SignatureRequest } from '@/lib/services/signature-service'
import { format } from 'date-fns'
import { cn } from '@/lib/utils'

interface SignatureRequestDetailsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  request: SignatureRequest
  onUpdate?: () => void
}

export function SignatureRequestDetailsDialog({
  open,
  onOpenChange,
  request,
  onUpdate,
}: SignatureRequestDetailsDialogProps) {
  const { toast } = useToast()
  const signatureService = useSignatureService()
  const [isLoading, setIsLoading] = useState(false)
  const [localRequest, setLocalRequest] = useState(request)

  // Get status badge variant
  const getStatusBadgeVariant = (status: string) => {
    switch (status) {
      case 'draft': return 'secondary'
      case 'sent': return 'default'
      case 'completed': return 'success'
      case 'declined': return 'destructive'
      case 'expired': return 'warning'
      default: return 'outline'
    }
  }

  // Get signer status icon
  const getSignerStatusIcon = (status?: string) => {
    switch (status) {
      case 'signed':
        return <CheckCircle className="h-4 w-4 text-green-600" />
      case 'declined':
        return <XCircle className="h-4 w-4 text-red-600" />
      case 'sent':
        return <Mail className="h-4 w-4 text-blue-600" />
      case 'viewed':
        return <Eye className="h-4 w-4 text-orange-600" />
      default:
        return <Clock className="h-4 w-4 text-gray-400" />
    }
  }

  // Get signer status label
  const getSignerStatusLabel = (status?: string) => {
    switch (status) {
      case 'signed': return 'Signed'
      case 'declined': return 'Declined'
      case 'sent': return 'Sent'
      case 'viewed': return 'Viewed'
      default: return 'Pending'
    }
  }

  // Handle send request
  const handleSendRequest = async () => {
    setIsLoading(true)
    try {
      await signatureService.sendRequest(localRequest.id)
      // Reload the request to get updated data
      const updatedRequest = await signatureService.getRequest(localRequest.id)
      setLocalRequest(updatedRequest)
      toast({
        title: 'Success',
        description: 'Signature request sent successfully',
      })
      onUpdate?.()
    } catch (err: any) {
      toast({
        title: 'Error',
        description: err.message || 'Failed to send signature request',
        variant: 'destructive',
      })
    } finally {
      setIsLoading(false)
    }
  }

  // Handle refresh status
  const handleRefreshStatus = async () => {
    setIsLoading(true)
    try {
      await signatureService.updateStatus(localRequest.id)
      // Reload the request to get updated data
      const updatedRequest = await signatureService.getRequest(localRequest.id)
      setLocalRequest(updatedRequest)
      toast({
        title: 'Success',
        description: 'Status updated successfully',
      })
      onUpdate?.()
    } catch (err: any) {
      toast({
        title: 'Error',
        description: err.message || 'Failed to update status',
        variant: 'destructive',
      })
    } finally {
      setIsLoading(false)
    }
  }

  // Handle download document
  const handleDownloadDocument = async () => {
    setIsLoading(true)
    try {
      const blob = await signatureService.downloadSignedDocument(localRequest.id)
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${localRequest.title}_signed.pdf`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (err: any) {
      toast({
        title: 'Error',
        description: err.message || 'Failed to download document',
        variant: 'destructive',
      })
    } finally {
      setIsLoading(false)
    }
  }

  // Handle cancel request
  const handleCancelRequest = async () => {
    // TODO: Implement cancel functionality when backend endpoint is available
    toast({
      title: 'Info',
      description: 'Cancel functionality is not yet implemented',
    })
  }

  // Calculate progress
  const signedCount = localRequest.signers.filter(s => s.status === 'signed').length
  const totalSigners = localRequest.signers.length
  const progressPercentage = totalSigners > 0 ? (signedCount / totalSigners) * 100 : 0

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh]">
        <DialogHeader>
          <DialogTitle>Signature Request Details</DialogTitle>
          <DialogDescription>
            View and manage this signature request
          </DialogDescription>
        </DialogHeader>

        <ScrollArea className="max-h-[60vh] pr-4">
          <div className="space-y-6">
            {/* Status and Progress */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">Status:</span>
                  <Badge variant={getStatusBadgeVariant(localRequest.status) as any}>
                    {localRequest.status}
                  </Badge>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-sm text-muted-foreground">
                    {signedCount} of {totalSigners} signed
                  </span>
                </div>
              </div>
              
              {/* Progress bar */}
              <div className="w-full bg-secondary rounded-full h-2">
                <div 
                  className="bg-primary h-2 rounded-full transition-all"
                  style={{ width: `${progressPercentage}%` }}
                />
              </div>
            </div>

            <Separator />

            {/* Request Information */}
            <div className="space-y-4">
              <h3 className="text-sm font-semibold">Request Information</h3>
              
              <div className="grid gap-4 text-sm">
                <div className="flex items-start gap-3">
                  <FileText className="h-4 w-4 mt-0.5 text-muted-foreground" />
                  <div className="flex-1">
                    <p className="font-medium">{localRequest.title}</p>
                    {localRequest.message && (
                      <p className="text-muted-foreground mt-1">{localRequest.message}</p>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <Calendar className="h-4 w-4 text-muted-foreground" />
                  <div>
                    <span className="text-muted-foreground">Created:</span>{' '}
                    {format(new Date(localRequest.created_at), 'PPp')}
                  </div>
                </div>

                {localRequest.sent_at && (
                  <div className="flex items-center gap-3">
                    <Send className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <span className="text-muted-foreground">Sent:</span>{' '}
                      {format(new Date(localRequest.sent_at), 'PPp')}
                    </div>
                  </div>
                )}

                {localRequest.completed_at && (
                  <div className="flex items-center gap-3">
                    <CheckCircle className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <span className="text-muted-foreground">Completed:</span>{' '}
                      {format(new Date(localRequest.completed_at), 'PPp')}
                    </div>
                  </div>
                )}

                {localRequest.expires_at && (
                  <div className="flex items-center gap-3">
                    <Clock className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <span className="text-muted-foreground">Expires:</span>{' '}
                      {format(new Date(localRequest.expires_at), 'PPp')}
                    </div>
                  </div>
                )}
              </div>
            </div>

            <Separator />

            {/* Signers */}
            <div className="space-y-4">
              <h3 className="text-sm font-semibold">Signers</h3>
              
              <div className="space-y-3">
                {localRequest.signers.map((signer, index) => (
                  <div 
                    key={index}
                    className={cn(
                      "flex items-center justify-between p-3 rounded-lg border",
                      signer.status === 'signed' && "bg-green-50 border-green-200",
                      signer.status === 'declined' && "bg-red-50 border-red-200"
                    )}
                  >
                    <div className="flex items-center gap-3">
                      <User className="h-4 w-4 text-muted-foreground" />
                      <div>
                        <p className="font-medium">{signer.name}</p>
                        <p className="text-sm text-muted-foreground">{signer.email}</p>
                      </div>
                    </div>
                    
                    <div className="flex items-center gap-2">
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger>
                            {getSignerStatusIcon(signer.status)}
                          </TooltipTrigger>
                          <TooltipContent>
                            <p>{getSignerStatusLabel(signer.status)}</p>
                            {signer.signed_at && (
                              <p className="text-xs">
                                {format(new Date(signer.signed_at), 'PPp')}
                              </p>
                            )}
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                      <Badge variant="outline" className="text-xs">
                        {signer.role}
                      </Badge>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* External ID */}
            {localRequest.external_id && (
              <>
                <Separator />
                <div className="space-y-2">
                  <h3 className="text-sm font-semibold">Provider Information</h3>
                  <p className="text-sm text-muted-foreground">
                    External ID: {localRequest.external_id}
                  </p>
                </div>
              </>
            )}
          </div>
        </ScrollArea>

        <DialogFooter>
          <div className="flex items-center justify-between w-full">
            <div className="flex gap-2">
              {localRequest.status === 'draft' && (
                <Button
                  variant="outline"
                  onClick={() => onOpenChange(false)}
                  disabled={isLoading}
                >
                  Close
                </Button>
              )}
              {(localRequest.status === 'sent' || localRequest.status === 'expired') && (
                <Button
                  variant="outline"
                  onClick={handleCancelRequest}
                  disabled={isLoading}
                >
                  Cancel Request
                </Button>
              )}
            </div>
            
            <div className="flex gap-2">
              {localRequest.status === 'draft' && (
                <Button
                  onClick={handleSendRequest}
                  disabled={isLoading}
                >
                  <Send className="mr-2 h-4 w-4" />
                  Send Request
                </Button>
              )}
              
              {localRequest.status === 'sent' && (
                <Button
                  variant="outline"
                  onClick={handleRefreshStatus}
                  disabled={isLoading}
                >
                  <RefreshCw className="mr-2 h-4 w-4" />
                  Refresh Status
                </Button>
              )}
              
              {localRequest.status === 'completed' && (
                <Button
                  onClick={handleDownloadDocument}
                  disabled={isLoading}
                >
                  <Download className="mr-2 h-4 w-4" />
                  Download Signed
                </Button>
              )}
            </div>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}