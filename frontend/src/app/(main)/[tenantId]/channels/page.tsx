"use client"

import { useState, useEffect } from "react"
import { useParams, useRouter } from "next/navigation"
import { IconPlus, IconRefresh, IconMail, IconBrandGoogleDrive, IconDatabase } from "@tabler/icons-react"

import { Button } from "@/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useToast } from "@/hooks/use-toast"
import { useChannelsService, Channel, ChannelType } from "@/lib/services/channels.service"
import { ChannelCard } from "@/components/channels/channel-card"
import { CreateChannelDialog } from "@/components/channels/create-channel-dialog"
import { ChannelDetailSheet } from "@/components/channels/channel-detail-sheet"
import { useTranslation } from "@/lib/i18n/hooks"

export default function ChannelsPage() {
  const params = useParams()
  const router = useRouter()
  const { toast } = useToast()
  const { t } = useTranslation()
  const channelsService = useChannelsService()

  // State
  const [channels, setChannels] = useState<Channel[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<"all" | ChannelType>("all")
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const [selectedChannel, setSelectedChannel] = useState<Channel | null>(null)
  const [detailSheetOpen, setDetailSheetOpen] = useState(false)

  // Load channels
  const loadChannels = async () => {
    setIsLoading(true)
    setError(null)

    try {
      const response = await channelsService.listChannels({
        channel_type: activeTab === "all" ? undefined : activeTab,
        page_size: 50,
      })

      if (response.error) {
        setError(response.error)
      } else {
        setChannels(response.data?.items || [])
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load channels")
    } finally {
      setIsLoading(false)
    }
  }

  // Load on mount and tab change
  useEffect(() => {
    loadChannels()
  }, [activeTab])

  // Handle sync
  const handleSync = async (channel: Channel) => {
    try {
      const response = await channelsService.triggerSync(channel.id)
      if (response.error) {
        toast({
          title: t("channels.toast.syncError.title"),
          description: response.error,
          variant: "destructive",
        })
      } else {
        toast({
          title: t("channels.toast.syncStarted.title"),
          description: t("channels.toast.syncStarted.description"),
        })
        // Refresh after short delay
        setTimeout(loadChannels, 2000)
      }
    } catch (err) {
      toast({
        title: t("channels.toast.syncError.title"),
        description: t("channels.toast.syncError.description"),
        variant: "destructive",
      })
    }
  }

  // Handle delete
  const handleDelete = async (channel: Channel) => {
    if (!confirm(t("channels.delete.description"))) {
      return
    }

    try {
      const response = await channelsService.deleteChannel(channel.id)
      if (response.error) {
        toast({
          title: t("channels.toast.deleteError.title"),
          description: response.error,
          variant: "destructive",
        })
      } else {
        toast({
          title: t("channels.toast.deleteSuccess.title"),
          description: t("channels.toast.deleteSuccess.description"),
        })
        loadChannels()
      }
    } catch (err) {
      toast({
        title: t("channels.toast.deleteError.title"),
        description: t("channels.toast.deleteError.description"),
        variant: "destructive",
      })
    }
  }

  // Handle view details
  const handleViewDetails = (channel: Channel) => {
    setSelectedChannel(channel)
    setDetailSheetOpen(true)
  }

  // Handle OAuth callback (check URL params)
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search)
    const channelId = urlParams.get("channel_id")
    const oauthError = urlParams.get("error")

    if (channelId) {
      toast({
        title: t("channels.toast.createSuccess.title"),
        description: t("channels.toast.createSuccess.description"),
      })
      // Clear URL params
      router.replace(`/${params.tenantId}/channels`)
      loadChannels()
    } else if (oauthError) {
      toast({
        title: t("channels.toast.authError.title"),
        description: oauthError,
        variant: "destructive",
      })
      router.replace(`/${params.tenantId}/channels`)
    }
  }, [])

  // Stats
  const totalChannels = channels.length
  const activeChannels = channels.filter((c) => c.is_active).length
  const totalDocuments = channels.reduce((sum, c) => sum + (c.documents_indexed || 0), 0)

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{t("channels.title")}</h1>
          <p className="text-muted-foreground">
            {t("channels.subtitle")}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={loadChannels} disabled={isLoading}>
            <IconRefresh className={`mr-2 h-4 w-4 ${isLoading ? "animate-spin" : ""}`} />
            {t("common.refresh")}
          </Button>
          <Button onClick={() => setCreateDialogOpen(true)}>
            <IconPlus className="mr-2 h-4 w-4" />
            {t("channels.createChannel")}
          </Button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="rounded-lg border bg-card p-4">
          <div className="text-sm text-muted-foreground">{t("channels.title")}</div>
          <div className="text-2xl font-bold">{totalChannels}</div>
        </div>
        <div className="rounded-lg border bg-card p-4">
          <div className="text-sm text-muted-foreground">{t("channels.status.active")}</div>
          <div className="text-2xl font-bold text-green-600">{activeChannels}</div>
        </div>
        <div className="rounded-lg border bg-card p-4">
          <div className="text-sm text-muted-foreground">{t("channels.card.documents")}</div>
          <div className="text-2xl font-bold">{totalDocuments.toLocaleString()}</div>
        </div>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as typeof activeTab)}>
        <TabsList>
          <TabsTrigger value="all">{t("channels.title")}</TabsTrigger>
          <TabsTrigger value="gmail" className="flex items-center gap-1">
            <IconMail className="h-4 w-4" />
            {t("channels.types.gmail")}
          </TabsTrigger>
          <TabsTrigger value="google_drive" className="flex items-center gap-1">
            <IconBrandGoogleDrive className="h-4 w-4" />
            {t("channels.types.google_drive")}
          </TabsTrigger>
          <TabsTrigger value="external_db" className="flex items-center gap-1">
            <IconDatabase className="h-4 w-4" />
            {t("channels.types.external_db")}
          </TabsTrigger>
        </TabsList>

        <TabsContent value={activeTab} className="mt-4">
          {error ? (
            <div className="rounded-lg border border-destructive bg-destructive/10 p-4 text-destructive">
              {error}
            </div>
          ) : isLoading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-48 rounded-lg border bg-muted animate-pulse" />
              ))}
            </div>
          ) : channels.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <div className="rounded-full bg-muted p-4 mb-4">
                <IconDatabase className="h-8 w-8 text-muted-foreground" />
              </div>
              <h3 className="text-lg font-semibold">{t("channels.noChannels.title")}</h3>
              <p className="text-muted-foreground mb-4">
                {t("channels.noChannels.description")}
              </p>
              <Button onClick={() => setCreateDialogOpen(true)}>
                <IconPlus className="mr-2 h-4 w-4" />
                {t("channels.createChannel")}
              </Button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {channels.map((channel) => (
                <ChannelCard
                  key={channel.id}
                  channel={channel}
                  onSync={() => handleSync(channel)}
                  onDelete={() => handleDelete(channel)}
                  onViewDetails={() => handleViewDetails(channel)}
                />
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* Create Dialog */}
      <CreateChannelDialog
        open={createDialogOpen}
        onOpenChange={setCreateDialogOpen}
        onCreated={(channel) => {
          setCreateDialogOpen(false)
          loadChannels()
          // If Google channel, redirect to OAuth
          if (channel.channel_type === "gmail" || channel.channel_type === "google_drive") {
            handleStartOAuth(channel)
          }
        }}
      />

      {/* Detail Sheet */}
      <ChannelDetailSheet
        channel={selectedChannel}
        open={detailSheetOpen}
        onOpenChange={setDetailSheetOpen}
        onSync={() => selectedChannel && handleSync(selectedChannel)}
        onRefresh={loadChannels}
      />
    </div>
  )

  // OAuth helper
  async function handleStartOAuth(channel: Channel) {
    try {
      const response = await channelsService.getOAuthUrl(channel.id)
      if (response.error) {
        toast({
          title: "OAuth Error",
          description: response.error,
          variant: "destructive",
        })
      } else if (response.data?.auth_url) {
        // Redirect to Google OAuth
        window.location.href = response.data.auth_url
      }
    } catch (err) {
      toast({
        title: "Error",
        description: "Failed to start authorization",
        variant: "destructive",
      })
    }
  }
}
