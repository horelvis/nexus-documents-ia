'use client'

import { useState, useEffect } from 'react'
import { useParams } from 'next/navigation'
import { Plus, Search, FileText, Send, Download, Eye, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Skeleton } from '@/components/ui/skeleton'
import { useToast } from '@/hooks/use-toast'
import { useSignatureService } from '@/lib/services/signature-service.hooks'
import { SignatureRequest } from '@/lib/services/signature-service'
import { format } from 'date-fns'
import { CreateSignatureRequestDialog } from '@/components/signatures/create-request-dialog'
import { SignatureRequestDetailsDialog } from '@/components/signatures/request-details-dialog'

export default function SignatureRequestsPage() {
  const params = useParams()
  const tenantId = params.tenantId as string
  const { toast } = useToast()
  const signatureService = useSignatureService()

  const [requests, setRequests] = useState<SignatureRequest[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false)
  const [selectedRequest, setSelectedRequest] = useState<SignatureRequest | null>(null)
  const [isDetailsDialogOpen, setIsDetailsDialogOpen] = useState(false)

  // Load signature requests
  const loadRequests = async () => {
    setIsLoading(true)
    setError(null)
    
    try {
      const filters: any = {}
      if (statusFilter !== 'all') {
        filters.status = statusFilter
      }
      
      const data = await signatureService.getRequests(filters)
      setRequests(data)
    } catch (err: any) {
      setError(err.message || 'Failed to load signature requests')
      toast({
        title: 'Error',
        description: 'Failed to load signature requests',
        variant: 'destructive',
      })
    } finally {
      setIsLoading(false)
    }
  }

  // Load on mount and when filters change
  useEffect(() => {
    loadRequests()
  }, [statusFilter])

  // Filter requests by search term
  const filteredRequests = requests.filter(request => {
    if (!searchTerm) return true
    const searchLower = searchTerm.toLowerCase()
    return (
      request.title.toLowerCase().includes(searchLower) ||
      request.id.toLowerCase().includes(searchLower) ||
      request.signers.some(s => 
        s.email.toLowerCase().includes(searchLower) ||
        s.name.toLowerCase().includes(searchLower)
      )
    )
  })

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

  // Handle send request
  const handleSendRequest = async (requestId: string) => {
    try {
      await signatureService.sendRequest(requestId)
      toast({
        title: 'Success',
        description: 'Signature request sent successfully',
      })
      loadRequests()
    } catch (err: any) {
      toast({
        title: 'Error',
        description: err.message || 'Failed to send signature request',
        variant: 'destructive',
      })
    }
  }

  // Handle refresh status
  const handleRefreshStatus = async (requestId: string) => {
    try {
      await signatureService.updateStatus(requestId)
      toast({
        title: 'Success',
        description: 'Status updated successfully',
      })
      loadRequests()
    } catch (err: any) {
      toast({
        title: 'Error',
        description: err.message || 'Failed to update status',
        variant: 'destructive',
      })
    }
  }

  // Handle download signed document
  const handleDownloadDocument = async (request: SignatureRequest) => {
    try {
      const blob = await signatureService.downloadSignedDocument(request.id)
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${request.title}_signed.pdf`
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
    }
  }

  // Handle view details
  const handleViewDetails = (request: SignatureRequest) => {
    setSelectedRequest(request)
    setIsDetailsDialogOpen(true)
  }

  // Count requests by status
  const statusCounts = {
    all: requests.length,
    draft: requests.filter(r => r.status === 'draft').length,
    sent: requests.filter(r => r.status === 'sent').length,
    completed: requests.filter(r => r.status === 'completed').length,
    declined: requests.filter(r => r.status === 'declined').length,
    expired: requests.filter(r => r.status === 'expired').length,
  }

  return (
    <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6">
      <div className="px-4 lg:px-6">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold mb-2">Signature Requests</h1>
          <p className="text-muted-foreground">
            Manage digital signature requests and track their status
          </p>
        </div>

        {/* Status Cards */}
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4 mb-6">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Total Requests</CardTitle>
              <FileText className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{statusCounts.all}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Sent</CardTitle>
              <Send className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{statusCounts.sent}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Completed</CardTitle>
              <Download className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{statusCounts.completed}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Pending Action</CardTitle>
              <RefreshCw className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{statusCounts.draft}</div>
            </CardContent>
          </Card>
        </div>

        {/* Actions and Filters */}
        <div className="flex flex-col gap-4 mb-6 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-1 gap-2">
            <div className="relative flex-1 max-w-sm">
              <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search requests..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-8"
              />
            </div>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Filter by status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Status</SelectItem>
                <SelectItem value="draft">Draft</SelectItem>
                <SelectItem value="sent">Sent</SelectItem>
                <SelectItem value="completed">Completed</SelectItem>
                <SelectItem value="declined">Declined</SelectItem>
                <SelectItem value="expired">Expired</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <Button onClick={() => setIsCreateDialogOpen(true)}>
            <Plus className="mr-2 h-4 w-4" />
            New Request
          </Button>
        </div>

        {/* Requests Table */}
        <Card>
          <CardContent className="p-0">
            {isLoading ? (
              <div className="p-6 space-y-4">
                {[...Array(5)].map((_, i) => (
                  <Skeleton key={i} className="h-12 w-full" />
                ))}
              </div>
            ) : error ? (
              <div className="p-6 text-center text-muted-foreground">
                <p className="mb-4">{error}</p>
                <Button onClick={loadRequests} variant="outline">
                  <RefreshCw className="mr-2 h-4 w-4" />
                  Retry
                </Button>
              </div>
            ) : filteredRequests.length === 0 ? (
              <div className="p-12 text-center">
                <FileText className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
                <h3 className="text-lg font-semibold mb-2">No signature requests found</h3>
                <p className="text-muted-foreground mb-4">
                  {searchTerm || statusFilter !== 'all'
                    ? 'Try adjusting your filters'
                    : 'Create your first signature request to get started'}
                </p>
                {statusFilter === 'all' && !searchTerm && (
                  <Button onClick={() => setIsCreateDialogOpen(true)}>
                    <Plus className="mr-2 h-4 w-4" />
                    Create Request
                  </Button>
                )}
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Title</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Signers</TableHead>
                    <TableHead>Created</TableHead>
                    <TableHead>Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredRequests.map((request) => (
                    <TableRow key={request.id}>
                      <TableCell className="font-medium">
                        <div>
                          <p>{request.title}</p>
                          <p className="text-sm text-muted-foreground">
                            ID: {request.id.slice(0, 8)}...
                          </p>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant={getStatusBadgeVariant(request.status) as any}>
                          {request.status}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <div className="text-sm">
                          <p>{request.signers.length} signer(s)</p>
                          <p className="text-muted-foreground">
                            {request.signers.filter(s => s.status === 'signed').length} signed
                          </p>
                        </div>
                      </TableCell>
                      <TableCell>
                        {format(new Date(request.created_at), 'MMM d, yyyy')}
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-2">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleViewDetails(request)}
                          >
                            <Eye className="h-4 w-4" />
                          </Button>
                          {request.status === 'draft' && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleSendRequest(request.id)}
                            >
                              <Send className="h-4 w-4" />
                            </Button>
                          )}
                          {request.status === 'sent' && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleRefreshStatus(request.id)}
                            >
                              <RefreshCw className="h-4 w-4" />
                            </Button>
                          )}
                          {request.status === 'completed' && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleDownloadDocument(request)}
                            >
                              <Download className="h-4 w-4" />
                            </Button>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Dialogs */}
      <CreateSignatureRequestDialog
        open={isCreateDialogOpen}
        onOpenChange={setIsCreateDialogOpen}
        tenantId={tenantId}
        onSuccess={() => {
          setIsCreateDialogOpen(false)
          loadRequests()
        }}
      />

      {selectedRequest && (
        <SignatureRequestDetailsDialog
          open={isDetailsDialogOpen}
          onOpenChange={setIsDetailsDialogOpen}
          request={selectedRequest}
          onUpdate={loadRequests}
        />
      )}
    </div>
  )
}