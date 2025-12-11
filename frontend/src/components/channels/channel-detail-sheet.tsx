"use client"

import { useState, useEffect } from "react"
import { formatDistanceToNow, format } from "date-fns"
import { es, enUS } from "date-fns/locale"
import {
  IconMail,
  IconBrandGoogleDrive,
  IconDatabase,
  IconRefresh,
  IconCheck,
  IconAlertTriangle,
  IconX,
  IconLoader2,
  IconExternalLink,
  IconSettings,
  IconHistory,
  IconFile,
} from "@tabler/icons-react"

import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Switch } from "@/components/ui/switch"
import { Label } from "@/components/ui/label"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { useToast } from "@/hooks/use-toast"
import {
  useChannelsService,
  Channel,
  ChannelType,
  SyncLog,
  SyncStatus,
} from "@/lib/services/channels.service"
import { useTranslation } from "@/lib/i18n/hooks"

interface ChannelDetailSheetProps {
  channel: Channel | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onSync: () => void
  onRefresh: () => void
}

const CHANNEL_TYPE_ICONS: Record<ChannelType, { icon: typeof IconMail; color: string }> = {
  gmail: { icon: IconMail, color: "text-red-500" },
  google_drive: { icon: IconBrandGoogleDrive, color: "text-blue-500" },
  external_db: { icon: IconDatabase, color: "text-purple-500" },
}

const SYNC_STATUS_ICONS: Record<SyncStatus, { icon: typeof IconCheck; color: string }> = {
  success: { icon: IconCheck, color: "text-green-500" },
  partial: { icon: IconAlertTriangle, color: "text-yellow-500" },
  failed: { icon: IconX, color: "text-red-500" },
  running: { icon: IconLoader2, color: "text-blue-500" },
}

export function ChannelDetailSheet({
  channel,
  open,
  onOpenChange,
  onSync,
  onRefresh,
}: ChannelDetailSheetProps) {
  const { toast } = useToast()
  const { t, language } = useTranslation()
  const dateLocale = language === "es" ? es : enUS
  const channelsService = useChannelsService()

  const [syncHistory, setSyncHistory] = useState<SyncLog[]>([])
  const [isLoadingHistory, setIsLoadingHistory] = useState(false)
  const [isUpdating, setIsUpdating] = useState(false)
  const [isAuthorizing, setIsAuthorizing] = useState(false)

  // Handle OAuth authorization
  const handleAuthorize = async () => {
    if (!channel) return

    setIsAuthorizing(true)
    try {
      const response = await channelsService.getOAuthUrl(channel.id)
      if (response.error) {
        toast({
          title: t("channels.toast.authError.title"),
          description: response.error,
          variant: "destructive",
        })
      } else if (response.data?.auth_url) {
        // Redirect to Google OAuth
        window.location.href = response.data.auth_url
      }
    } catch (err) {
      toast({
        title: t("channels.toast.authError.title"),
        description: t("channels.toast.authError.description"),
        variant: "destructive",
      })
    } finally {
      setIsAuthorizing(false)
    }
  }

  // Load sync history when sheet opens
  useEffect(() => {
    if (open && channel) {
      loadSyncHistory()
    }
  }, [open, channel?.id])

  const loadSyncHistory = async () => {
    if (!channel) return

    setIsLoadingHistory(true)
    try {
      const response = await channelsService.getSyncHistory(channel.id, 20)
      if (response.data) {
        setSyncHistory(response.data.items)
      }
    } catch (err) {
      console.error("Failed to load sync history:", err)
    } finally {
      setIsLoadingHistory(false)
    }
  }

  const handleToggleActive = async () => {
    if (!channel) return

    setIsUpdating(true)
    try {
      const response = await channelsService.updateChannel(channel.id, {
        is_active: !channel.is_active,
      })

      if (response.error) {
        toast({
          title: t("channels.toast.updateError.title"),
          description: response.error,
          variant: "destructive",
        })
      } else {
        toast({
          title: channel.is_active ? t("channels.toast.channelDisabled.title") : t("channels.toast.channelEnabled.title"),
          description: channel.is_active
            ? t("channels.toast.channelDisabled.description")
            : t("channels.toast.channelEnabled.description"),
        })
        onRefresh()
      }
    } catch (err) {
      toast({
        title: t("channels.toast.updateError.title"),
        description: t("channels.toast.updateError.description"),
        variant: "destructive",
      })
    } finally {
      setIsUpdating(false)
    }
  }

  if (!channel) return null

  const typeIcons = CHANNEL_TYPE_ICONS[channel.channel_type]
  const TypeIcon = typeIcons.icon

  const isGoogleChannel = channel.channel_type === "gmail" || channel.channel_type === "google_drive"
  const needsAuth = isGoogleChannel && !channel.has_credentials

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="sm:max-w-[500px]">
        <SheetHeader>
          <div className="flex items-center gap-3">
            <div className={`rounded-lg p-2 bg-muted ${typeIcons.color}`}>
              <TypeIcon className="h-5 w-5" />
            </div>
            <div>
              <SheetTitle>{channel.name}</SheetTitle>
              <SheetDescription>
                {t(`channels.types.${channel.channel_type}`)}
                {channel.oauth_email && ` • ${channel.oauth_email}`}
              </SheetDescription>
            </div>
          </div>
        </SheetHeader>

        <ScrollArea className="h-[calc(100vh-150px)] mt-6">
          <Tabs defaultValue="overview" className="w-full">
            <TabsList className="grid w-full grid-cols-3">
              <TabsTrigger value="overview">{t("channels.detail.overview")}</TabsTrigger>
              <TabsTrigger value="history">
                <IconHistory className="h-4 w-4 mr-1" />
                {t("channels.detail.history")}
              </TabsTrigger>
              <TabsTrigger value="settings">
                <IconSettings className="h-4 w-4 mr-1" />
                {t("channels.detail.settings")}
              </TabsTrigger>
            </TabsList>

            <TabsContent value="overview" className="space-y-6 mt-4">
              {/* Status */}
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">{t("channels.detail.status")}</span>
                <Badge variant={channel.is_active ? "default" : "secondary"}>
                  {channel.is_active ? t("channels.status.active") : t("channels.status.disabled")}
                </Badge>
              </div>

              {/* Auth warning */}
              {needsAuth && (
                <div className="flex items-center gap-2 p-3 bg-yellow-50 dark:bg-yellow-900/20 rounded-lg text-yellow-700 dark:text-yellow-400 text-sm">
                  <IconAlertTriangle className="h-5 w-5 flex-shrink-0" />
                  <div>
                    <p className="font-medium">{t("channels.detail.authWarning")}</p>
                    <p className="text-xs">{t("channels.detail.authWarningDescription")}</p>
                  </div>
                </div>
              )}

              <Separator />

              {/* Stats */}
              <div className="grid grid-cols-2 gap-4">
                <div className="rounded-lg border p-3">
                  <div className="text-xs text-muted-foreground">{t("channels.card.documents")}</div>
                  <div className="text-2xl font-bold">{channel.documents_indexed}</div>
                </div>
                <div className="rounded-lg border p-3">
                  <div className="text-xs text-muted-foreground">{t("channels.detail.syncInterval")}</div>
                  <div className="text-2xl font-bold">{channel.sync_interval_minutes}m</div>
                </div>
              </div>

              {/* Last sync info */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">{t("channels.card.lastSync")}</span>
                  <span className="text-sm">
                    {channel.last_sync_at
                      ? formatDistanceToNow(new Date(channel.last_sync_at), {
                          addSuffix: true,
                          locale: dateLocale,
                        })
                      : t("channels.card.never")}
                  </span>
                </div>

                {channel.last_sync_status && (
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">{t("channels.detail.lastStatus")}</span>
                    <Badge
                      variant={
                        channel.last_sync_status === "success"
                          ? "default"
                          : channel.last_sync_status === "failed"
                          ? "destructive"
                          : "secondary"
                      }
                    >
                      {t(`channels.syncStatus.${channel.last_sync_status}`)}
                    </Badge>
                  </div>
                )}

                {channel.next_sync_at && (
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">{t("channels.detail.nextSync")}</span>
                    <span className="text-sm">
                      {formatDistanceToNow(new Date(channel.next_sync_at), {
                        addSuffix: true,
                        locale: dateLocale,
                      })}
                    </span>
                  </div>
                )}
              </div>

              {/* Error message */}
              {channel.last_sync_error && (
                <div className="p-3 bg-destructive/10 rounded-lg text-destructive text-sm">
                  <p className="font-medium mb-1">{t("channels.detail.lastSyncError")}</p>
                  <p className="text-xs">{channel.last_sync_error}</p>
                </div>
              )}

              <Separator />

              {/* Actions */}
              <div className="flex gap-2">
                <Button
                  onClick={onSync}
                  disabled={!channel.is_active || needsAuth}
                  className="flex-1"
                >
                  <IconRefresh className="h-4 w-4 mr-2" />
                  {t("channels.card.syncNow")}
                </Button>
                {needsAuth && (
                  <Button
                    variant="outline"
                    className="flex-1"
                    onClick={handleAuthorize}
                    disabled={isAuthorizing}
                  >
                    {isAuthorizing ? (
                      <IconLoader2 className="h-4 w-4 mr-2 animate-spin" />
                    ) : (
                      <IconExternalLink className="h-4 w-4 mr-2" />
                    )}
                    {isAuthorizing ? t("channels.detail.redirecting") : t("channels.detail.authorize")}
                  </Button>
                )}
              </div>
            </TabsContent>

            <TabsContent value="history" className="mt-4">
              {isLoadingHistory ? (
                <div className="flex items-center justify-center py-8">
                  <IconLoader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              ) : syncHistory.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  <IconHistory className="h-8 w-8 mx-auto mb-2 opacity-50" />
                  <p>{t("channels.history.noHistory")}</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {syncHistory.map((log) => {
                    const statusIcons = SYNC_STATUS_ICONS[log.status as SyncStatus]
                    const StatusIcon = statusIcons?.icon || IconCheck

                    return (
                      <div
                        key={log.id}
                        className="rounded-lg border p-3 space-y-2"
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <StatusIcon
                              className={`h-4 w-4 ${statusIcons?.color || ""} ${
                                log.status === "running" ? "animate-spin" : ""
                              }`}
                            />
                            <span className="font-medium text-sm capitalize">
                              {t(`channels.syncStatus.${log.status}`)}
                            </span>
                          </div>
                          <span className="text-xs text-muted-foreground">
                            {format(new Date(log.started_at), "MMM d, HH:mm", {
                              locale: dateLocale,
                            })}
                          </span>
                        </div>

                        <div className="grid grid-cols-4 gap-2 text-xs">
                          <div>
                            <div className="text-muted-foreground">{t("channels.history.found")}</div>
                            <div className="font-medium">{log.items_found}</div>
                          </div>
                          <div>
                            <div className="text-muted-foreground">{t("channels.history.new")}</div>
                            <div className="font-medium text-green-600">
                              +{log.items_new}
                            </div>
                          </div>
                          <div>
                            <div className="text-muted-foreground">{t("channels.history.updated")}</div>
                            <div className="font-medium text-blue-600">
                              {log.items_updated}
                            </div>
                          </div>
                          <div>
                            <div className="text-muted-foreground">{t("channels.history.failed")}</div>
                            <div className="font-medium text-red-600">
                              {log.items_failed}
                            </div>
                          </div>
                        </div>

                        {log.error_message && (
                          <p className="text-xs text-destructive truncate">
                            {log.error_message}
                          </p>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </TabsContent>

            <TabsContent value="settings" className="space-y-6 mt-4">
              {/* Toggle active */}
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label>{t("channels.detail.enableAutoSync")}</Label>
                  <p className="text-xs text-muted-foreground">
                    {t("channels.detail.enableAutoSyncDescription")}
                  </p>
                </div>
                <Switch
                  checked={channel.is_active}
                  onCheckedChange={handleToggleActive}
                  disabled={isUpdating}
                />
              </div>

              <Separator />

              {/* Channel info */}
              <div className="space-y-3 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">{t("channels.detail.created")}</span>
                  <span>
                    {format(new Date(channel.created_at), "MMM d, yyyy", {
                      locale: dateLocale,
                    })}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">{t("channels.visibility.personal")}</span>
                  <Badge variant="outline">
                    {channel.visibility === "tenant" ? t("channels.visibility.tenant") : t("channels.visibility.personal")}
                  </Badge>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">{t("channels.detail.channelId")}</span>
                  <code className="text-xs bg-muted px-2 py-0.5 rounded">
                    {channel.id.slice(0, 8)}...
                  </code>
                </div>
              </div>

              {/* Configuration display */}
              <div className="space-y-2">
                <Label>{t("channels.detail.configuration")}</Label>
                <pre className="text-xs bg-muted p-3 rounded-lg overflow-auto max-h-40">
                  {JSON.stringify(channel.configuration, null, 2)}
                </pre>
              </div>
            </TabsContent>
          </Tabs>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  )
}
