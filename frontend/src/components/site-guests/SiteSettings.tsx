"use client"

import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useSiteGuestService, SiteSiteSettings } from '@/lib/services/site-guest.service'
import { Loader2, Save, ExternalLink, Copy, Check } from 'lucide-react'
import { API_CONFIG } from '@/lib/config'
import { useTranslation } from '@/lib/i18n/hooks'

interface SiteSettingsProps {
  onSettingsChange?: (settings: SiteSiteSettings) => void
}

export function SiteSettings({ onSettingsChange }: SiteSettingsProps) {
  const { t } = useTranslation()
  const [settings, setSettings] = useState<SiteSiteSettings | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  // Form state
  const [siteEnabled, setSiteEnabled] = useState(false)
  const [slug, setSlug] = useState('')
  const [logoUrl, setLogoUrl] = useState('')
  const [welcomeMessage, setWelcomeMessage] = useState('')

  const siteGuestService = useSiteGuestService()

  const loadSettings = async () => {
    setIsLoading(true)
    setError(null)

    try {
      const response = await siteGuestService.getSiteSettings()
      if (response.error) {
        setError(response.error)
      } else if (response.data) {
        setSettings(response.data)
        setSiteEnabled(response.data.site_enabled)
        setSlug(response.data.slug || '')
        setLogoUrl(response.data.site_logo_url || '')
        setWelcomeMessage(response.data.site_welcome_message || '')
        onSettingsChange?.(response.data)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error loading settings')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadSettings()
  }, [])

  const handleSave = async () => {
    setIsSaving(true)
    setError(null)

    try {
      const response = await siteGuestService.updateSiteSettings({
        site_enabled: siteEnabled,
        slug: slug || undefined,
        site_logo_url: logoUrl || undefined,
        site_welcome_message: welcomeMessage || undefined
      })

      if (response.error) {
        setError(response.error)
      } else if (response.data) {
        setSettings(response.data)
        onSettingsChange?.(response.data)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error saving settings')
    } finally {
      setIsSaving(false)
    }
  }

  const getPortalUrl = () => {
    const portalKey = slug
    if (!portalKey) return null
    // Use window.location.origin for the frontend URL
    const origin = typeof window !== 'undefined' ? window.location.origin : ''
    return `${origin}/portal/${portalKey}`
  }

  const copyPortalUrl = () => {
    const url = getPortalUrl()
    if (url) {
      navigator.clipboard.writeText(url)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  if (isLoading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin mr-2" />
          <span>{t('common.loading')}</span>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('siteGuest.settings.title')}</CardTitle>
        <CardDescription>
          {t('siteGuest.settings.description')}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {error && (
          <div className="p-3 bg-destructive/10 text-destructive text-sm rounded-md">
            {error}
          </div>
        )}

        <div className="flex items-center justify-between">
          <div>
            <Label>{t('siteGuest.title')}</Label>
            <p className="text-sm text-muted-foreground">
              {t('siteGuest.description')}
            </p>
          </div>
          <Switch checked={siteEnabled} onCheckedChange={setSiteEnabled} />
        </div>

        <div className="space-y-2">
          <Label htmlFor="slug">{t('siteGuest.settings.slug')}</Label>
          <div className="flex gap-2">
            <Input
              id="slug"
              value={slug}
              onChange={(e) => setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''))}
              placeholder={t('siteGuest.settings.slugPlaceholder')}
              className="flex-1"
            />
          </div>
          <p className="text-xs text-muted-foreground">
            {t('siteGuest.settings.slugDescription')}
          </p>
        </div>

        {slug && (
          <div className="p-3 bg-muted rounded-md">
            <Label className="text-xs">{t('siteGuest.settings.portalUrl')}</Label>
            <div className="flex items-center gap-2 mt-1">
              <code className="flex-1 text-sm break-all">
                {getPortalUrl()}
              </code>
              <Button variant="ghost" size="sm" onClick={copyPortalUrl} title={t('siteGuest.settings.copyUrl')}>
                {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
              </Button>
              {siteEnabled ? (
                <Button variant="ghost" size="sm" asChild>
                  <a href={getPortalUrl() || '#'} target="_blank" rel="noopener noreferrer">
                    <ExternalLink className="h-4 w-4" />
                  </a>
                </Button>
              ) : (
                <Button variant="ghost" size="sm" disabled title="Habilita el Site para previsualizar">
                  <ExternalLink className="h-4 w-4" />
                </Button>
              )}
            </div>
          </div>
        )}

        <div className="space-y-2">
          <Label htmlFor="logo">{t('siteGuest.settings.logoUrl')}</Label>
          <Input
            id="logo"
            value={logoUrl}
            onChange={(e) => setLogoUrl(e.target.value)}
            placeholder={t('siteGuest.settings.logoUrlPlaceholder')}
          />
          <p className="text-xs text-muted-foreground">
            {t('siteGuest.settings.logoUrlDescription')}
          </p>
        </div>

        <div className="space-y-2">
          <Label htmlFor="welcome">{t('siteGuest.settings.welcomeMessage')}</Label>
          <Textarea
            id="welcome"
            value={welcomeMessage}
            onChange={(e) => setWelcomeMessage(e.target.value)}
            placeholder={t('siteGuest.settings.welcomeMessagePlaceholder')}
            rows={3}
          />
          <p className="text-xs text-muted-foreground">
            {t('siteGuest.settings.welcomeMessageDescription')}
          </p>
        </div>

        {settings && (
          <div className="pt-4 border-t">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-muted-foreground">{t('siteGuest.guests.title')}:</span>
                <span className="ml-2 font-medium">{settings.guest_count}</span>
              </div>
              <div>
                <span className="text-muted-foreground">{t('siteGuest.guests.status.active')}:</span>
                <span className="ml-2 font-medium">{settings.active_guest_count}</span>
              </div>
            </div>
          </div>
        )}

        <div className="flex justify-end pt-4">
          <Button onClick={handleSave} disabled={isSaving}>
            {isSaving ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Save className="h-4 w-4 mr-2" />
            )}
            {isSaving ? t('siteGuest.settings.saving') : t('siteGuest.settings.saveChanges')}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
