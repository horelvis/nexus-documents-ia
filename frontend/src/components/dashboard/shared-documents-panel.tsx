"use client"

import { useEffect, useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { IconShare2, IconMail, IconLink, IconUsers } from "@tabler/icons-react"
import Link from "next/link"
import { formatDistanceToNow } from "date-fns"
import { es, enUS } from "date-fns/locale"
import { useSharedDocumentsService, type ShareStatistics } from "@/lib/services/shared-documents.service"
import { useTranslation } from "@/lib/i18n/hooks"

interface SharedDocumentsPanelProps {
  tenantId: string
}

export function SharedDocumentsPanel({ tenantId }: SharedDocumentsPanelProps) {
  const { t, language } = useTranslation()
  const [shareStats, setShareStats] = useState<ShareStatistics | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const sharedDocumentsService = useSharedDocumentsService()

  useEffect(() => {
    const loadShareStatistics = async () => {
      setIsLoading(true)
      setError(null)

      try {
        const response = await sharedDocumentsService.getShareStatistics()
        if (response.error) {
          setError(response.error)
        } else {
          setShareStats(response.data)
        }
      } catch (err) {
        setError('Failed to load shared documents')
      } finally {
        setIsLoading(false)
      }
    }

    loadShareStatistics()
  }, [])

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <IconShare2 className="h-5 w-5" />
          {t('dashboard.sharedDocuments.title')}
        </CardTitle>
        <CardDescription>{t('dashboard.sharedDocuments.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Summary Stats */}
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1">
            {isLoading ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <p className="text-2xl font-bold">{shareStats?.total_shares || 0}</p>
            )}
            <p className="text-xs text-muted-foreground">{t('dashboard.sharedDocuments.totalShared')}</p>
          </div>
          <div className="space-y-1">
            {isLoading ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <p className="text-2xl font-bold">{shareStats?.active_shares || 0}</p>
            )}
            <p className="text-xs text-muted-foreground">{t('dashboard.sharedDocuments.activeLinks')}</p>
          </div>
        </div>

        {/* Recent Shares */}
        <div className="space-y-3 pt-4 border-t">
          <h4 className="text-sm font-medium">{t('dashboard.sharedDocuments.recentShares')}</h4>

          {isLoading ? (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="space-y-2">
                  <Skeleton className="h-4 w-3/4" />
                  <Skeleton className="h-3 w-1/2" />
                </div>
              ))}
            </div>
          ) : error ? (
            <p className="text-sm text-muted-foreground">{t('dashboard.sharedDocuments.failedToLoad')}</p>
          ) : shareStats?.recent_shares && shareStats.recent_shares.length > 0 ? (
            <div className="space-y-2">
              {shareStats.recent_shares.slice(0, 3).map((share) => {
                const isExpired = share.expires_at && new Date(share.expires_at) < new Date()
                const locale = language === 'es' ? es : enUS
                const expiresIn = share.expires_at ? formatDistanceToNow(new Date(share.expires_at), { addSuffix: true, locale }) : null

                return (
                  <div key={share.id} className="flex items-start justify-between gap-2">
                    <div className="flex-1 space-y-1">
                      <p className="text-sm font-medium leading-none truncate">
                        {share.document_filename || share.document_title || 'Untitled'}
                      </p>
                      <div className="flex items-center gap-2 text-xs text-muted-foreground">
                        {share.recipient_email ? (
                          <>
                            <IconMail className="h-3 w-3" />
                            <span className="truncate">{share.recipient_email}</span>
                          </>
                        ) : share.share_type === 'public' ? (
                          <>
                            <IconLink className="h-3 w-3" />
                            <span>{t('dashboard.sharedDocuments.publicLink')} • {t('dashboard.sharedDocuments.views', { count: share.current_access_count })}</span>
                          </>
                        ) : (
                          <>
                            <IconUsers className="h-3 w-3" />
                            <span>{t('dashboard.sharedDocuments.accesses', { count: share.current_access_count })}</span>
                          </>
                        )}
                      </div>
                    </div>
                    <Badge
                      variant={isExpired ? "destructive" : share.is_active ? "outline" : "secondary"}
                      className="text-xs"
                    >
                      {isExpired ? t('dashboard.sharedDocuments.status.expired') : !share.is_active ? t('dashboard.sharedDocuments.status.revoked') : expiresIn ? t('dashboard.sharedDocuments.status.expiresIn', { time: expiresIn }) : t('dashboard.sharedDocuments.status.active')}
                    </Badge>
                  </div>
                )
              })}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">{t('dashboard.sharedDocuments.noShares')}</p>
          )}
        </div>

        <div className="pt-4 border-t">
          <Button variant="outline" className="w-full" asChild>
            <Link href={`/${tenantId}/shared`}>
              <IconShare2 className="mr-2 h-4 w-4" />
              {t('dashboard.sharedDocuments.manageAll')}
            </Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}