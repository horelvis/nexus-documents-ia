"use client"

import { useState, useEffect } from 'react'
import { useParams } from 'next/navigation'
import { useSiteGuest } from '@/contexts/site-guest-context'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import {
  Loader2, Mail, KeyRound, LogOut, File, Folder, Eye, Download,
  RefreshCw
} from 'lucide-react'
import { PortalDocument, PortalContentResponse } from '@/lib/services/site-guest.service'
import { formatDistanceToNow } from 'date-fns'
import { es, enUS, fr } from 'date-fns/locale'
import { useTranslation } from '@/lib/i18n/hooks'

type ViewState = 'loading' | 'login' | 'otp' | 'content' | 'error'

export default function PortalPage() {
  const params = useParams()
  const slug = params.slug as string
  const { t, language } = useTranslation()

  const {
    tenant, guest, sessionToken, isLoading: contextLoading,
    setTenant, login, logout, portalService
  } = useSiteGuest()

  const [viewState, setViewState] = useState<ViewState>('loading')
  const [error, setError] = useState<string | null>(null)

  // Login form
  const [email, setEmail] = useState('')
  const [isRequestingOTP, setIsRequestingOTP] = useState(false)

  // OTP form
  const [otpCode, setOtpCode] = useState('')
  const [otpExpiry, setOtpExpiry] = useState(0)
  const [isVerifying, setIsVerifying] = useState(false)

  // Content
  const [content, setContent] = useState<PortalContentResponse | null>(null)
  const [isLoadingContent, setIsLoadingContent] = useState(false)

  // Get date-fns locale based on current language
  const getDateLocale = () => {
    switch (language) {
      case 'es': return es
      case 'fr': return fr
      default: return enUS
    }
  }

  // Load tenant info on mount
  useEffect(() => {
    const loadTenant = async () => {
      try {
        const response = await portalService.getTenantBySlug(slug)
        if (response.error) {
          setError(response.error)
          setViewState('error')
        } else if (response.data) {
          setTenant(response.data)
          // If already logged in, show content
          if (sessionToken && guest) {
            setViewState('content')
          } else {
            setViewState('login')
          }
        }
      } catch (err) {
        setError('Failed to load portal')
        setViewState('error')
      }
    }

    if (!contextLoading) {
      if (sessionToken && guest) {
        setViewState('content')
      } else {
        loadTenant()
      }
    }
  }, [slug, contextLoading, sessionToken, guest, portalService, setTenant])

  // Load content when logged in
  useEffect(() => {
    const loadContent = async () => {
      if (viewState !== 'content' || !sessionToken) return

      setIsLoadingContent(true)
      try {
        const response = await portalService.getContent()
        if (response.data) {
          setContent(response.data)
        } else if (response.error) {
          setError(response.error)
        }
      } catch (err) {
        setError('Failed to load content')
      } finally {
        setIsLoadingContent(false)
      }
    }

    loadContent()
  }, [viewState, sessionToken, portalService])

  const handleRequestOTP = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsRequestingOTP(true)
    setError(null)

    try {
      const response = await portalService.requestOTP(slug, email)
      if (response.error) {
        setError(response.error)
      } else if (response.data) {
        if (response.data.success) {
          setOtpExpiry(response.data.expires_in_seconds)
          setViewState('otp')
        } else {
          setError(response.data.message)
        }
      }
    } catch (err) {
      setError('Failed to request access code')
    } finally {
      setIsRequestingOTP(false)
    }
  }

  const handleVerifyOTP = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsVerifying(true)
    setError(null)

    try {
      const response = await portalService.verifyOTP(slug, email, otpCode)
      if (response.error) {
        setError(response.error)
      } else if (response.data) {
        if (response.data.success && response.data.session_token && response.data.guest) {
          login(response.data.session_token, response.data.guest)
          setViewState('content')
        } else {
          setError(response.data.error || 'Invalid code')
        }
      }
    } catch (err) {
      setError('Failed to verify code')
    } finally {
      setIsVerifying(false)
    }
  }

  const handleLogout = async () => {
    await logout()
    setViewState('login')
    setContent(null)
  }

  const handleViewDocument = async (doc: PortalDocument) => {
    try {
      const response = await portalService.getDocumentViewUrl(doc.id)
      if (response.data?.view_url) {
        window.open(response.data.view_url, '_blank')
      } else {
        alert('Could not open document')
      }
    } catch (err) {
      alert('Failed to open document')
    }
  }

  const handleDownloadDocument = (doc: PortalDocument) => {
    const url = portalService.getDocumentDownloadUrl(doc.id)
    // Add auth header via fetch and trigger download
    window.open(url, '_blank')
  }

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  // Loading state
  if (viewState === 'loading' || contextLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4 text-primary" />
          <p className="text-muted-foreground">{t('siteGuest.portal.loading')}</p>
        </div>
      </div>
    )
  }

  // Error state
  if (viewState === 'error') {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <Card className="w-full max-w-md">
          <CardHeader className="text-center">
            <CardTitle className="text-destructive">{t('siteGuest.portal.error.title')}</CardTitle>
            <CardDescription>{error || t('siteGuest.portal.error.description')}</CardDescription>
          </CardHeader>
        </Card>
      </div>
    )
  }

  // Login form
  if (viewState === 'login') {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <Card className="w-full max-w-md">
          <CardHeader className="text-center">
            {tenant?.logo_url && (
              <img
                src={tenant.logo_url}
                alt={tenant.tenant_name}
                className="h-12 mx-auto mb-4 object-contain"
              />
            )}
            <CardTitle>{tenant?.tenant_name || t('siteGuest.portal.title')}</CardTitle>
            <CardDescription>
              {tenant?.welcome_message || t('siteGuest.portal.login.invitedOnly')}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleRequestOTP} className="space-y-4">
              {error && (
                <div className="p-3 bg-destructive/10 text-destructive text-sm rounded-md">
                  {error}
                </div>
              )}

              <div className="space-y-2">
                <Label htmlFor="email">{t('siteGuest.portal.login.emailLabel')}</Label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    id="email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder={t('siteGuest.portal.login.emailPlaceholder')}
                    className="pl-10"
                    required
                  />
                </div>
              </div>

              <Button type="submit" className="w-full" disabled={isRequestingOTP}>
                {isRequestingOTP && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                {isRequestingOTP ? t('siteGuest.portal.login.sending') : t('siteGuest.portal.login.sendCode')}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    )
  }

  // OTP verification
  if (viewState === 'otp') {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <Card className="w-full max-w-md">
          <CardHeader className="text-center">
            <CardTitle>{t('siteGuest.portal.otp.title')}</CardTitle>
            <CardDescription>
              {t('siteGuest.portal.otp.subtitle').replace('{email}', email)}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleVerifyOTP} className="space-y-4">
              {error && (
                <div className="p-3 bg-destructive/10 text-destructive text-sm rounded-md">
                  {error}
                </div>
              )}

              <div className="space-y-2">
                <Label htmlFor="otp">{t('siteGuest.portal.otp.codeLabel')}</Label>
                <div className="relative">
                  <KeyRound className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    id="otp"
                    type="text"
                    inputMode="numeric"
                    pattern="[0-9]{6}"
                    maxLength={6}
                    value={otpCode}
                    onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, ''))}
                    placeholder={t('siteGuest.portal.otp.codePlaceholder')}
                    className="pl-10 text-center text-2xl tracking-[0.5em]"
                    required
                  />
                </div>
                <p className="text-xs text-muted-foreground text-center">
                  {t('siteGuest.portal.otp.expiresIn').replace('{minutes}', String(Math.floor(otpExpiry / 60)))}
                </p>
              </div>

              <Button type="submit" className="w-full" disabled={isVerifying || otpCode.length !== 6}>
                {isVerifying && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                {isVerifying ? t('siteGuest.portal.otp.verifying') : t('siteGuest.portal.otp.verify')}
              </Button>

              <Button
                type="button"
                variant="ghost"
                className="w-full"
                onClick={() => {
                  setViewState('login')
                  setOtpCode('')
                  setError(null)
                }}
              >
                {t('siteGuest.portal.otp.backToLogin')}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    )
  }

  // Content view
  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="bg-white border-b">
        <div className="container mx-auto px-4 py-4 flex justify-between items-center">
          <div className="flex items-center gap-4">
            {tenant?.logo_url && (
              <img src={tenant.logo_url} alt="" className="h-8 object-contain" />
            )}
            <div>
              <h1 className="font-semibold">{tenant?.tenant_name}</h1>
              <p className="text-sm text-muted-foreground">
                {guest?.name || guest?.email}
              </p>
            </div>
          </div>
          <Button variant="outline" onClick={handleLogout}>
            <LogOut className="h-4 w-4 mr-2" />
            {t('siteGuest.portal.content.logout')}
          </Button>
        </div>
      </header>

      {/* Content */}
      <main className="container mx-auto px-4 py-8">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-xl font-semibold">{t('siteGuest.portal.content.title')}</h2>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setIsLoadingContent(true)
              portalService.getContent().then(r => {
                if (r.data) setContent(r.data)
                setIsLoadingContent(false)
              })
            }}
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${isLoadingContent ? 'animate-spin' : ''}`} />
            {t('siteGuest.portal.content.refresh')}
          </Button>
        </div>

        {isLoadingContent ? (
          <div className="text-center py-12">
            <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4" />
            <p className="text-muted-foreground">{t('common.loading')}</p>
          </div>
        ) : !content || (content.total_documents === 0 && content.total_folders === 0) ? (
          <Card>
            <CardContent className="text-center py-12">
              <File className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
              <p className="text-muted-foreground">{t('siteGuest.portal.content.noContent.description')}</p>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-6">
            {/* Folders */}
            {content.folders.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg flex items-center gap-2">
                    <Folder className="h-5 w-5" />
                    {t('siteGuest.portal.content.folders')} ({content.folders.length})
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-3">
                    {content.folders.map((folder) => (
                      <div
                        key={folder.path}
                        className="p-4 border rounded-lg hover:bg-muted/50 cursor-pointer"
                      >
                        <div className="flex items-center gap-3">
                          <Folder className="h-8 w-8 text-blue-500" />
                          <div>
                            <p className="font-medium">{folder.name}</p>
                            <p className="text-sm text-muted-foreground">
                              {t('siteGuest.portal.content.documentsCount').replace('{count}', String(folder.document_count))}
                            </p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Documents */}
            {content.documents.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg flex items-center gap-2">
                    <File className="h-5 w-5" />
                    {t('siteGuest.portal.content.documents')} ({content.documents.length})
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-0">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>{t('siteGuest.portal.content.table.name')}</TableHead>
                        <TableHead>{t('siteGuest.portal.content.table.type')}</TableHead>
                        <TableHead>{t('siteGuest.portal.content.table.size')}</TableHead>
                        <TableHead>{t('siteGuest.portal.content.table.updated')}</TableHead>
                        <TableHead className="w-[100px]">{t('common.actions')}</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {content.documents.map((doc) => (
                        <TableRow key={doc.id}>
                          <TableCell>
                            <div className="flex items-center gap-2">
                              <File className="h-4 w-4 text-muted-foreground" />
                              <span className="font-medium">{doc.title || doc.filename}</span>
                            </div>
                          </TableCell>
                          <TableCell>
                            <Badge variant="secondary">{doc.file_type.toUpperCase()}</Badge>
                          </TableCell>
                          <TableCell className="text-muted-foreground">
                            {formatFileSize(doc.file_size)}
                          </TableCell>
                          <TableCell className="text-muted-foreground">
                            {formatDistanceToNow(new Date(doc.updated_at), { addSuffix: true, locale: getDateLocale() })}
                          </TableCell>
                          <TableCell>
                            <div className="flex gap-1">
                              {doc.can_view && (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleViewDocument(doc)}
                                  title={t('siteGuest.portal.content.actions.view')}
                                >
                                  <Eye className="h-4 w-4" />
                                </Button>
                              )}
                              {doc.can_download && (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleDownloadDocument(doc)}
                                  title={t('siteGuest.portal.content.actions.download')}
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
                </CardContent>
              </Card>
            )}
          </div>
        )}
      </main>
    </div>
  )
}
