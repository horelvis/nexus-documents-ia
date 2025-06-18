"use client"

import { useState, useEffect } from "react"
import { useParams, useRouter } from "next/navigation"
import { 
  IconLoader2, 
  IconLock, 
  IconDownload,
  IconEye,
  IconFile,
  IconAlertCircle,
  IconCalendar,
  IconUser,
  IconClock,
  IconX
} from "@tabler/icons-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { getFileIcon, formatFileSize } from "@/lib/document-utils"
import { formatDistanceToNow } from "date-fns"
import { API_CONFIG } from "@/lib/config"

interface ShareInfo {
  success: boolean
  document_url?: string
  error?: string
  requires_password: boolean
  document_info?: {
    title: string
    filename: string
    file_type: string
    file_size: number
    description?: string
    share_type: string
  }
}

export default function SharedDocumentPage() {
  const params = useParams()
  const router = useRouter()
  const token = params.token as string

  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [shareInfo, setShareInfo] = useState<ShareInfo | null>(null)
  const [password, setPassword] = useState("")
  const [isUnlocking, setIsUnlocking] = useState(false)
  const [documentUrl, setDocumentUrl] = useState<string | null>(null)

  // Access the shared document
  const accessDocument = async (withPassword?: string) => {
    setIsLoading(true)
    setError(null)
    
    try {
      const queryParams = withPassword ? `?password=${encodeURIComponent(withPassword)}` : ""
      const url = `${API_CONFIG.BASE_URL}${API_CONFIG.API_V1}/shares/access/${token}${queryParams}`
      console.log('Accessing share URL:', url)
      
      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
        mode: 'cors',
      })
      
      console.log('Response status:', response.status)
      
      if (!response.ok) {
        const errorText = await response.text()
        console.error('Error response:', errorText)
        
        if (response.status === 404) {
          setError("This share link is invalid or has expired")
          return
        }
        if (response.status === 403) {
          setError("This share link is no longer valid")
          return
        }
        if (response.status === 422) {
          setError("Invalid request format")
          return
        }
        throw new Error(`Failed to access document: ${response.status} ${errorText}`)
      }

      const data: ShareInfo = await response.json()
      setShareInfo(data)

      if (data.success && data.document_url) {
        // For view-only documents, automatically show the document
        if (data.document_info?.share_type === 'view') {
          const url = data.document_url.startsWith('/') 
            ? `${API_CONFIG.BASE_URL}${data.document_url}`
            : data.document_url
          setDocumentUrl(url)
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to access document")
    } finally {
      setIsLoading(false)
      setIsUnlocking(false)
    }
  }

  // Initial access attempt
  useEffect(() => {
    accessDocument()
  }, [])

  // Handle password submission
  const handlePasswordSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!password.trim()) return
    
    setIsUnlocking(true)
    accessDocument(password)
  }

  // Handle document download
  const handleDownload = async () => {
    if (!shareInfo?.document_url) return

    try {
      // If it's a relative URL, prepend the API base URL
      const url = shareInfo.document_url.startsWith('/') 
        ? `${API_CONFIG.BASE_URL}${shareInfo.document_url}`
        : shareInfo.document_url
      
      window.open(url, '_blank')
    } catch (error) {
      setError("Failed to download document")
    }
  }

  // Handle document view
  const handleView = async () => {
    if (!shareInfo?.document_url) return

    try {
      // If it's a relative URL, prepend the API base URL
      const url = shareInfo.document_url.startsWith('/') 
        ? `${API_CONFIG.BASE_URL}${shareInfo.document_url}`
        : shareInfo.document_url
      
      // For PDFs and images, we can open directly
      // For other files, it will download
      window.open(url, '_blank')
    } catch (error) {
      setError("Failed to view document")
    }
  }

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-center">
          <IconLoader2 className="h-12 w-12 animate-spin mx-auto text-purple-600 dark:text-purple-400" />
          <p className="mt-4 text-lg">Accessing shared document...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background p-4">
        <Card className="max-w-md w-full">
          <CardContent className="pt-6">
            <div className="text-center">
              <IconAlertCircle className="h-12 w-12 mx-auto text-red-500 mb-4" />
              <h2 className="text-xl font-semibold mb-2">Access Error</h2>
              <p className="text-muted-foreground">{error}</p>
              <Button 
                className="mt-6" 
                onClick={() => router.push('/')}
                variant="outline"
              >
                Go to Homepage
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  if (shareInfo?.requires_password && !shareInfo.success) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background p-4">
        <Card className="max-w-md w-full">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <IconLock className="h-5 w-5" />
              Password Required
            </CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handlePasswordSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="password">Enter password to access this document</Label>
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter password"
                  autoFocus
                  disabled={isUnlocking}
                />
              </div>
              {shareInfo.error && (
                <Alert variant="destructive">
                  <AlertDescription>{shareInfo.error}</AlertDescription>
                </Alert>
              )}
              <Button 
                type="submit" 
                className="w-full" 
                disabled={!password.trim() || isUnlocking}
              >
                {isUnlocking ? (
                  <>
                    <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                    Unlocking...
                  </>
                ) : (
                  'Unlock Document'
                )}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    )
  }

  if (shareInfo?.success && shareInfo.document_info) {
    const doc = shareInfo.document_info
    const canDownload = doc.share_type === 'download' || doc.share_type === 'edit'
    const isViewOnly = doc.share_type === 'view'
    
    // If view-only and we have the document URL, show it in an iframe
    if (isViewOnly && documentUrl) {
      return (
        <div className="fixed inset-0 bg-background">
          {/* Header Bar */}
          <div className="absolute top-0 left-0 right-0 bg-background border-b z-10">
            <div className="container mx-auto px-4 py-3 flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-2">
                  {getFileIcon(doc.file_type, undefined, doc.filename, 'h-5 w-5')}
                  <h1 className="text-lg font-semibold">{doc.title || doc.filename}</h1>
                </div>
                <Badge variant="outline" className="text-xs">
                  View Only
                </Badge>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setDocumentUrl(null)}
              >
                <IconX className="h-4 w-4" />
              </Button>
            </div>
          </div>
          
          {/* Document Viewer */}
          <div className="pt-16 h-full">
            <iframe
              src={documentUrl}
              className="w-full h-full border-0"
              title={doc.title || doc.filename}
            />
          </div>
        </div>
      )
    }
    
    // For download/edit permissions, show the info card
    return (
      <div className="min-h-screen bg-background">
        <div className="container mx-auto py-8 px-4 max-w-4xl">
          {/* Header */}
          <div className="mb-8 text-center">
            <h1 className="text-3xl font-bold mb-2">Shared Document</h1>
            <p className="text-muted-foreground">
              This document has been shared with you
            </p>
          </div>

          {/* Document Card */}
          <Card className="mb-6">
            <CardContent className="pt-6">
              <div className="flex items-start gap-6">
                {/* File Icon */}
                <div className="flex-shrink-0">
                  <div className="w-16 h-16 flex items-center justify-center rounded-lg bg-muted">
                    {getFileIcon(doc.file_type, undefined, doc.filename, 'h-10 w-10')}
                  </div>
                </div>

                {/* Document Info */}
                <div className="flex-grow space-y-4">
                  <div>
                    <h2 className="text-2xl font-semibold mb-1">
                      {doc.title || doc.filename}
                    </h2>
                    {doc.description && (
                      <p className="text-muted-foreground">
                        {doc.description}
                      </p>
                    )}
                  </div>

                  {/* Metadata */}
                  <div className="flex flex-wrap gap-4 text-sm">
                    <div className="flex items-center gap-1">
                      <IconFile className="h-4 w-4 text-muted-foreground" />
                      <span>{doc.filename}</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <IconClock className="h-4 w-4 text-muted-foreground" />
                      <span>{formatFileSize(doc.file_size)}</span>
                    </div>
                  </div>

                  {/* Permissions */}
                  <div className="flex items-center gap-2">
                    <Badge variant="outline">
                      {doc.share_type === 'view' && 'View Only'}
                      {doc.share_type === 'download' && 'View & Download'}
                      {doc.share_type === 'edit' && 'Full Access'}
                    </Badge>
                  </div>
                </div>
              </div>

              {/* Actions */}
              <div className="mt-6 flex items-center gap-3">
                <Button 
                  onClick={handleView}
                  size="lg"
                >
                  <IconEye className="mr-2 h-5 w-5" />
                  View Document
                </Button>
                
                {canDownload && (
                  <Button 
                    onClick={handleDownload}
                    variant="outline"
                    size="lg"
                  >
                    <IconDownload className="mr-2 h-5 w-5" />
                    Download
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Info Alert */}
          <Alert>
            <IconAlertCircle className="h-4 w-4" />
            <AlertTitle>Share Information</AlertTitle>
            <AlertDescription>
              This document has been shared with you via a secure link. 
              {doc.share_type === 'view' && ' You can only view this document.'}
              {doc.share_type === 'download' && ' You can view and download this document.'}
              {doc.share_type === 'edit' && ' You have full access to this document.'}
            </AlertDescription>
          </Alert>
        </div>
      </div>
    )
  }

  return null
}