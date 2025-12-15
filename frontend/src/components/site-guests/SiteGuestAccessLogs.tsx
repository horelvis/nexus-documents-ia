"use client"

import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle
} from '@/components/ui/dialog'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow
} from '@/components/ui/table'
import {
  useSiteGuestService, SiteGuest, SiteGuestAccessLog
} from '@/lib/services/site-guest.service'
import { Loader2, RefreshCw, LogIn, Eye, Download, Upload, LogOut, Key, AlertCircle } from 'lucide-react'
import { formatDistanceToNow, format } from 'date-fns'
import { es, enUS, fr } from 'date-fns/locale'
import { useTranslation } from '@/lib/i18n/hooks'

interface SiteGuestAccessLogsProps {
  guest: SiteGuest
  open: boolean
  onClose: () => void
}

export function SiteGuestAccessLogs({ guest, open, onClose }: SiteGuestAccessLogsProps) {
  const { t, language } = useTranslation()
  const [logs, setLogs] = useState<SiteGuestAccessLog[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const siteGuestService = useSiteGuestService()

  // Get date-fns locale based on current language
  const getDateLocale = () => {
    switch (language) {
      case 'es': return es
      case 'fr': return fr
      default: return enUS
    }
  }

  const loadLogs = async () => {
    setIsLoading(true)
    setError(null)

    try {
      const response = await siteGuestService.getGuestAccessLogs(guest.id, {
        page,
        per_page: 20
      })

      if (response.error) {
        setError(response.error)
      } else if (response.data) {
        setLogs(response.data.logs)
        setTotal(response.data.total)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error loading access logs')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    if (open && guest) {
      loadLogs()
    }
  }, [open, guest, page])

  const getActionIcon = (action: string) => {
    switch (action) {
      case 'login': return <LogIn className="h-4 w-4 text-green-600" />
      case 'logout': return <LogOut className="h-4 w-4 text-gray-600" />
      case 'otp_request': return <Key className="h-4 w-4 text-blue-600" />
      case 'otp_verify_failed': return <AlertCircle className="h-4 w-4 text-red-600" />
      case 'view_document':
      case 'view_document_content':
        return <Eye className="h-4 w-4 text-blue-600" />
      case 'download_document': return <Download className="h-4 w-4 text-green-600" />
      case 'upload_document': return <Upload className="h-4 w-4 text-purple-600" />
      default: return null
    }
  }

  const getActionLabel = (action: string) => {
    const actionKey = action.replace(/_/g, '_') // Keep underscore format for translation keys
    return t(`siteGuest.accessLogs.actions.${actionKey}`) || action
  }

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent className="sm:max-w-[800px] max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t('siteGuest.accessLogs.title').replace('{name}', guest.name || guest.email)}</DialogTitle>
          <DialogDescription>
            {t('siteGuest.accessLogs.description')}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {error && (
            <div className="p-3 bg-destructive/10 text-destructive text-sm rounded-md">
              {error}
            </div>
          )}

          <div className="flex justify-between items-center">
            <p className="text-sm text-muted-foreground">
              {logs.length} / {total}
            </p>
            <Button variant="outline" size="sm" onClick={loadLogs}>
              <RefreshCw className="h-4 w-4 mr-2" />
              {t('siteGuest.accessLogs.refresh')}
            </Button>
          </div>

          {isLoading ? (
            <div className="text-center py-8">
              <Loader2 className="h-6 w-6 animate-spin mx-auto mb-2" />
              <p className="text-muted-foreground">{t('common.loading')}</p>
            </div>
          ) : logs.length === 0 ? (
            <div className="text-center py-8 border rounded-lg">
              <p className="text-muted-foreground">{t('siteGuest.accessLogs.noLogs.description')}</p>
            </div>
          ) : (
            <div className="border rounded-lg">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t('siteGuest.accessLogs.table.action')}</TableHead>
                    <TableHead>{t('siteGuest.guests.table.status')}</TableHead>
                    <TableHead>{t('siteGuest.accessLogs.table.resource')}</TableHead>
                    <TableHead>{t('siteGuest.accessLogs.table.ip')}</TableHead>
                    <TableHead>{t('siteGuest.accessLogs.table.timestamp')}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {logs.map((log) => (
                    <TableRow key={log.id}>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          {getActionIcon(log.action)}
                          <span>{getActionLabel(log.action)}</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        {log.success ? (
                          <Badge variant="outline" className="text-green-600 border-green-600">
                            {t('common.success') || 'Success'}
                          </Badge>
                        ) : (
                          <Badge variant="destructive">
                            {t('common.error') || 'Failed'}
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell className="max-w-[200px] truncate">
                        {log.document_title || log.document_id || log.folder_path || '-'}
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        {log.ip_address || '-'}
                      </TableCell>
                      <TableCell className="text-sm">
                        <span title={format(new Date(log.created_at), 'PPpp', { locale: getDateLocale() })}>
                          {formatDistanceToNow(new Date(log.created_at), { addSuffix: true, locale: getDateLocale() })}
                        </span>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}

          {total > 20 && (
            <div className="flex justify-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page === 1}
                onClick={() => setPage(p => p - 1)}
              >
                {t('common.previous')}
              </Button>
              <span className="py-2 px-4 text-sm text-muted-foreground">
                {page} / {Math.ceil(total / 20)}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page * 20 >= total}
                onClick={() => setPage(p => p + 1)}
              >
                {t('common.next')}
              </Button>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t('common.close')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
