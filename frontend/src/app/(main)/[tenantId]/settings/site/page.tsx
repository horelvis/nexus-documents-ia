"use client"

import { useState } from 'react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { SiteSettings } from '@/components/site-guests/SiteSettings'
import { SiteGuestList } from '@/components/site-guests/SiteGuestList'
import { SiteGuestForm } from '@/components/site-guests/SiteGuestForm'
import { SiteGuestPermissions } from '@/components/site-guests/SiteGuestPermissions'
import { SiteGuestAccessLogs } from '@/components/site-guests/SiteGuestAccessLogs'
import { SiteGuestShares } from '@/components/site-guests/SiteGuestShares'
import { SiteGuest, SiteSiteSettings } from '@/lib/services/site-guest.service'
import { Settings, Users } from 'lucide-react'
import { useTranslation } from '@/lib/i18n/hooks'

export default function SiteSettingsPage() {
  const { t } = useTranslation()
  const [settings, setSettings] = useState<SiteSiteSettings | null>(null)
  const [selectedGuest, setSelectedGuest] = useState<SiteGuest | null>(null)
  const [showGuestForm, setShowGuestForm] = useState(false)
  const [showPermissions, setShowPermissions] = useState(false)
  const [showAccessLogs, setShowAccessLogs] = useState(false)
  const [showShares, setShowShares] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)

  const handleAddGuest = () => {
    setSelectedGuest(null)
    setShowGuestForm(true)
  }

  const handleSelectGuest = (guest: SiteGuest) => {
    setSelectedGuest(guest)
    setShowGuestForm(true)
  }

  const handleManagePermissions = (guest: SiteGuest) => {
    setSelectedGuest(guest)
    setShowPermissions(true)
  }

  const handleViewLogs = (guest: SiteGuest) => {
    setSelectedGuest(guest)
    setShowAccessLogs(true)
  }

  const handleViewShares = (guest: SiteGuest) => {
    setSelectedGuest(guest)
    setShowShares(true)
  }

  const handleGuestSaved = () => {
    setRefreshKey(k => k + 1)
  }

  return (
    <div className="container py-8 px-6 max-w-6xl mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-bold">{t('siteGuest.title')}</h1>
        <p className="text-muted-foreground">
          {t('siteGuest.subtitle')}
        </p>
      </div>

      <Tabs defaultValue="settings" className="space-y-6">
        <TabsList>
          <TabsTrigger value="settings" className="gap-2">
            <Settings className="h-4 w-4" />
            {t('siteGuest.tabs.settings')}
          </TabsTrigger>
          <TabsTrigger value="guests" className="gap-2">
            <Users className="h-4 w-4" />
            {t('siteGuest.tabs.guests')}
            {settings?.guest_count ? (
              <span className="ml-1 text-xs bg-primary/10 px-1.5 py-0.5 rounded">
                {settings.guest_count}
              </span>
            ) : null}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="settings">
          <SiteSettings onSettingsChange={setSettings} />
        </TabsContent>

        <TabsContent value="guests">
          <SiteGuestList
            key={refreshKey}
            onSelectGuest={handleSelectGuest}
            onAddGuest={handleAddGuest}
            onManagePermissions={handleManagePermissions}
            onViewLogs={handleViewLogs}
            onViewShares={handleViewShares}
          />
        </TabsContent>
      </Tabs>

      {/* Guest Form Dialog */}
      <SiteGuestForm
        guest={selectedGuest}
        open={showGuestForm}
        onClose={() => {
          setShowGuestForm(false)
          setSelectedGuest(null)
        }}
        onSaved={handleGuestSaved}
      />

      {/* Permissions Dialog */}
      {selectedGuest && (
        <SiteGuestPermissions
          guest={selectedGuest}
          open={showPermissions}
          onClose={() => {
            setShowPermissions(false)
            setSelectedGuest(null)
          }}
        />
      )}

      {/* Access Logs Dialog */}
      {selectedGuest && (
        <SiteGuestAccessLogs
          guest={selectedGuest}
          open={showAccessLogs}
          onClose={() => {
            setShowAccessLogs(false)
            setSelectedGuest(null)
          }}
        />
      )}

      {/* Shares Dialog */}
      {selectedGuest && (
        <SiteGuestShares
          guest={selectedGuest}
          open={showShares}
          onClose={() => {
            setShowShares(false)
            setSelectedGuest(null)
          }}
        />
      )}
    </div>
  )
}
