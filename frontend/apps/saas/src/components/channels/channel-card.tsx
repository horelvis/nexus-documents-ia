"use client"

import { formatDistanceToNow } from "date-fns"
import { es, enUS } from "date-fns/locale"
import {
  IconMail,
  IconBrandGoogleDrive,
  IconDatabase,
  IconRefresh,
  IconTrash,
  IconEye,
  IconCheck,
  IconAlertTriangle,
  IconX,
  IconLoader2,
  IconUsers,
  IconUser,
} from "@tabler/icons-react"

import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Channel, ChannelType, SyncStatus } from "@/lib/services/channels.service"
import { useTranslation } from "@/lib/i18n/hooks"

interface ChannelCardProps {
  channel: Channel
  onSync: () => void
  onDelete: () => void
  onViewDetails: () => void
}

const CHANNEL_TYPE_ICONS: Record<ChannelType, { icon: typeof IconMail; color: string }> = {
  gmail: { icon: IconMail, color: "text-red-500" },
  google_drive: { icon: IconBrandGoogleDrive, color: "text-blue-500" },
  external_db: { icon: IconDatabase, color: "text-purple-500" },
}

const SYNC_STATUS_ICONS: Record<SyncStatus, { icon: typeof IconCheck; variant: "default" | "secondary" | "destructive" | "outline" }> = {
  success: { icon: IconCheck, variant: "default" },
  partial: { icon: IconAlertTriangle, variant: "secondary" },
  failed: { icon: IconX, variant: "destructive" },
  running: { icon: IconLoader2, variant: "outline" },
}

export function ChannelCard({
  channel,
  onSync,
  onDelete,
  onViewDetails,
}: ChannelCardProps) {
  const { t, language } = useTranslation()
  const dateLocale = language === "es" ? es : enUS

  const typeIcons = CHANNEL_TYPE_ICONS[channel.channel_type]
  const TypeIcon = typeIcons.icon

  const syncIcons = channel.last_sync_status
    ? SYNC_STATUS_ICONS[channel.last_sync_status]
    : null
  const SyncIcon = syncIcons?.icon

  const isGoogleChannel =
    channel.channel_type === "gmail" || channel.channel_type === "google_drive"
  const needsAuth = isGoogleChannel && !channel.has_credentials

  return (
    <Card className={`relative ${!channel.is_active ? "opacity-60" : ""}`}>
      {/* Status indicator */}
      <div
        className={`absolute top-3 right-3 h-2 w-2 rounded-full ${
          channel.is_active ? "bg-green-500" : "bg-gray-400"
        }`}
        title={channel.is_active ? t("channels.status.active") : t("channels.status.inactive")}
      />

      <CardHeader className="pb-2">
        <div className="flex items-start gap-3">
          <div className={`rounded-lg p-2 bg-muted ${typeIcons.color}`}>
            <TypeIcon className="h-5 w-5" />
          </div>
          <div className="flex-1 min-w-0">
            <CardTitle className="text-base truncate">{channel.name}</CardTitle>
            <CardDescription className="text-xs mt-0.5">
              {t(`channels.types.${channel.channel_type}`)}
              {channel.oauth_email && (
                <span className="ml-1">• {channel.oauth_email}</span>
              )}
            </CardDescription>
          </div>
        </div>
      </CardHeader>

      <CardContent className="pb-2">
        {/* Visibility badge */}
        <div className="flex items-center gap-2 mb-3">
          {channel.visibility === "tenant" ? (
            <Badge variant="secondary" className="text-xs">
              <IconUsers className="h-3 w-3 mr-1" />
              {t("channels.visibility.tenant")}
            </Badge>
          ) : (
            <Badge variant="outline" className="text-xs">
              <IconUser className="h-3 w-3 mr-1" />
              {t("channels.visibility.personal")}
            </Badge>
          )}

          {!channel.is_active && (
            <Badge variant="secondary" className="text-xs">
              {t("channels.status.disabled")}
            </Badge>
          )}
        </div>

        {/* Auth warning for Google channels */}
        {needsAuth && (
          <div className="flex items-center gap-2 p-2 bg-yellow-50 dark:bg-yellow-900/20 rounded-md text-yellow-700 dark:text-yellow-400 text-xs mb-3">
            <IconAlertTriangle className="h-4 w-4 flex-shrink-0" />
            <span>{t("channels.card.authRequired")}</span>
          </div>
        )}

        {/* Stats */}
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <div className="text-muted-foreground text-xs">{t("channels.card.documents")}</div>
            <div className="font-medium">{channel.documents_indexed}</div>
          </div>
          <div>
            <div className="text-muted-foreground text-xs">{t("channels.card.lastSync")}</div>
            <div className="font-medium text-xs">
              {channel.last_sync_at ? (
                formatDistanceToNow(new Date(channel.last_sync_at), {
                  addSuffix: true,
                  locale: dateLocale,
                })
              ) : (
                <span className="text-muted-foreground">{t("channels.card.never")}</span>
              )}
            </div>
          </div>
        </div>

        {/* Sync status */}
        {syncIcons && SyncIcon && (
          <div className="mt-3">
            <Badge variant={syncIcons.variant} className="text-xs">
              <SyncIcon
                className={`h-3 w-3 mr-1 ${
                  channel.last_sync_status === "running" ? "animate-spin" : ""
                }`}
              />
              {t(`channels.syncStatus.${channel.last_sync_status}`)}
            </Badge>
            {channel.last_sync_error && (
              <p className="text-xs text-destructive mt-1 truncate" title={channel.last_sync_error}>
                {channel.last_sync_error}
              </p>
            )}
          </div>
        )}
      </CardContent>

      <CardFooter className="pt-2 gap-2">
        <Button
          variant="outline"
          size="sm"
          className="flex-1"
          onClick={onViewDetails}
        >
          <IconEye className="h-4 w-4 mr-1" />
          {t("channels.card.details")}
        </Button>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm">
              {t("channels.card.actions")}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem
              onClick={onSync}
              disabled={!channel.is_active || needsAuth}
            >
              <IconRefresh className="h-4 w-4 mr-2" />
              {t("channels.card.syncNow")}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={onDelete}
              className="text-destructive focus:text-destructive"
            >
              <IconTrash className="h-4 w-4 mr-2" />
              {t("channels.card.delete")}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </CardFooter>
    </Card>
  )
}
