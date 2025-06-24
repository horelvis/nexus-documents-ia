"use client"

import { useState, useEffect } from "react"
import { useParams, useRouter } from "next/navigation"
import { 
  IconPlus, 
  IconEdit, 
  IconTrash, 
  IconCheck,
  IconX,
  IconLoader2,
  IconSettings,
  IconKey,
  IconAlertCircle,
  IconTestPipe,
  IconShieldLock
} from "@tabler/icons-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { Switch } from "@/components/ui/switch"
import { Alert, AlertDescription } from "@/components/ui/alert"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { SignatureProvider } from "@/lib/services/signature-service"
import { useSignatureService } from "@/lib/services/signature-service.hooks"
import { useNotifications } from "@/contexts/app-state-context"
import { useAuth } from "@clerk/nextjs"
import { ProviderConfigWizard } from "@/components/admin/provider-config-wizard"
import { DeleteProviderDialog } from "@/components/admin/signature-providers/delete-provider-dialog"

export default function SignatureProvidersPage() {
  const params = useParams()
  const router = useRouter()
  const tenantId = params.tenantId as string
  const { addNotification } = useNotifications()
  const { userId } = useAuth()
  const signatureService = useSignatureService()
  
  const [providers, setProviders] = useState<SignatureProvider[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  
  // Dialog states
  const [configDialogOpen, setConfigDialogOpen] = useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [selectedProvider, setSelectedProvider] = useState<SignatureProvider | null>(null)
  const [isCreating, setIsCreating] = useState(false)
  
  // Test states
  const [testingProvider, setTestingProvider] = useState<string | null>(null)

  useEffect(() => {
    loadProviders()
  }, [])

  const loadProviders = async () => {
    setIsLoading(true)
    setError(null)
    
    try {
      const data = await signatureService.getProviders()
      setProviders(data)
    } catch (error: any) {
      setError(error.message || 'Failed to load providers')
      addNotification({
        type: 'error',
        title: 'Failed to load providers',
        message: error.message || 'An error occurred'
      })
    } finally {
      setIsLoading(false)
    }
  }

  const handleCreateProvider = () => {
    setSelectedProvider(null)
    setIsCreating(true)
    setConfigDialogOpen(true)
  }

  const handleEditProvider = (provider: SignatureProvider) => {
    setSelectedProvider(provider)
    setIsCreating(false)
    setConfigDialogOpen(true)
  }

  const handleDeleteProvider = (provider: SignatureProvider) => {
    setSelectedProvider(provider)
    setDeleteDialogOpen(true)
  }

  const handleToggleActive = async (provider: SignatureProvider) => {
    try {
      await signatureService.updateProvider(provider.id, {
        is_active: !provider.is_active
      })
      
      addNotification({
        type: 'success',
        title: 'Provider updated',
        message: `${provider.display_name} has been ${!provider.is_active ? 'activated' : 'deactivated'}`
      })
      
      await loadProviders()
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: 'Failed to update provider',
        message: error.message || 'An error occurred'
      })
    }
  }

  const handleSetDefault = async (provider: SignatureProvider) => {
    try {
      await signatureService.setDefaultProvider(provider.id)
      
      addNotification({
        type: 'success',
        title: 'Default provider set',
        message: `${provider.display_name} is now the default provider`
      })
      
      await loadProviders()
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: 'Failed to set default',
        message: error.message || 'An error occurred'
      })
    }
  }

  const handleTestProvider = async (provider: SignatureProvider) => {
    setTestingProvider(provider.id)
    
    try {
      const result = await signatureService.testProvider(provider.id)
      
      addNotification({
        type: result.success ? 'success' : 'error',
        title: result.success ? 'Test successful' : 'Test failed',
        message: result.message
      })
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: 'Test failed',
        message: error.message || 'Could not test provider'
      })
    } finally {
      setTestingProvider(null)
    }
  }

  const getProviderIcon = (providerName: string) => {
    const icons: Record<string, string> = {
      docusign: '📝',
      yousign: '✍️',
      signaturit: '🖊️'
    }
    return icons[providerName] || '📄'
  }

  const getProviderColor = (providerName: string) => {
    const colors: Record<string, string> = {
      docusign: 'yellow',
      yousign: 'blue',
      signaturit: 'green'
    }
    return colors[providerName] || 'gray'
  }

  return (
    <div className="container mx-auto p-6">
      <div className="mb-6">
        <h1 className="text-3xl font-bold">Signature Providers</h1>
        <p className="text-muted-foreground">
          Manage signature provider integrations for your organization
        </p>
      </div>

      {/* Security Notice */}
      <Alert className="mb-6">
        <IconShieldLock className="h-4 w-4" />
        <AlertDescription>
          Provider credentials are encrypted and stored securely. Only administrators can manage providers.
        </AlertDescription>
      </Alert>

      {/* Providers List */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Configured Providers</CardTitle>
              <CardDescription>
                Add and manage signature provider integrations
              </CardDescription>
            </div>
            <Button onClick={handleCreateProvider}>
              <IconPlus className="mr-2 h-4 w-4" />
              Add Provider
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <IconLoader2 className="h-6 w-6 animate-spin" />
              <span className="ml-2">Loading providers...</span>
            </div>
          ) : error ? (
            <Alert variant="destructive">
              <IconAlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : providers.length === 0 ? (
            <div className="text-center py-8">
              <IconKey className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
              <p className="text-muted-foreground mb-4">
                No signature providers configured yet
              </p>
              <Button onClick={handleCreateProvider}>
                <IconPlus className="mr-2 h-4 w-4" />
                Add Your First Provider
              </Button>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Provider</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Default</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {providers.map((provider) => (
                  <TableRow key={provider.id}>
                    <TableCell className="font-medium">
                      <div className="flex items-center gap-2">
                        <span className="text-xl">{getProviderIcon(provider.provider_name)}</span>
                        <span>{provider.display_name}</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className={`text-${getProviderColor(provider.provider_name)}-600`}>
                        {provider.provider_name}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <Switch
                          checked={provider.is_active}
                          onCheckedChange={() => handleToggleActive(provider)}
                        />
                        <span className="text-sm text-muted-foreground">
                          {provider.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell>
                      {provider.is_default ? (
                        <Badge variant="default">Default</Badge>
                      ) : provider.is_active ? (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleSetDefault(provider)}
                        >
                          Set as default
                        </Button>
                      ) : (
                        <span className="text-sm text-muted-foreground">-</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <span className="text-sm text-muted-foreground">
                        {new Date(provider.created_at).toLocaleDateString()}
                      </span>
                    </TableCell>
                    <TableCell className="text-right">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon">
                            <IconSettings className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => handleEditProvider(provider)}>
                            <IconEdit className="mr-2 h-4 w-4" />
                            Edit Configuration
                          </DropdownMenuItem>
                          <DropdownMenuItem 
                            onClick={() => handleTestProvider(provider)}
                            disabled={testingProvider === provider.id}
                          >
                            {testingProvider === provider.id ? (
                              <>
                                <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                                Testing...
                              </>
                            ) : (
                              <>
                                <IconTestPipe className="mr-2 h-4 w-4" />
                                Test Connection
                              </>
                            )}
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem 
                            onClick={() => handleDeleteProvider(provider)}
                            className="text-red-600 focus:text-red-600"
                          >
                            <IconTrash className="mr-2 h-4 w-4" />
                            Delete Provider
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Provider Information */}
      <div className="mt-6 grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">DocuSign</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Industry leader with advanced features and global compliance
            </p>
          </CardContent>
        </Card>
        
        <Card>
          <CardHeader>
            <CardTitle className="text-base">YouSign</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              European-focused provider with GDPR compliance and simple API
            </p>
          </CardContent>
        </Card>
        
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Signaturit</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Spanish provider with certified signatures and EU compliance
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Dialogs */}
      <ProviderConfigWizard
        open={configDialogOpen}
        onOpenChange={setConfigDialogOpen}
        provider={isCreating ? null : selectedProvider}
        onSuccess={loadProviders}
      />

      <DeleteProviderDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        provider={selectedProvider}
        onSuccess={loadProviders}
      />
    </div>
  )
}