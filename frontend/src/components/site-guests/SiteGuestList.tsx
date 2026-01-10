"use client"

import { useState, useEffect } from 'react'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow
} from '@/components/ui/table'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuTrigger, DropdownMenuSeparator
} from '@/components/ui/dropdown-menu'
import {
  MoreHorizontal, Mail, Shield, History, UserX, Eye, Download, Upload,
  Plus, RefreshCw, FolderOpen
} from 'lucide-react'
import { useSiteGuestService, SiteGuest } from '@/lib/services/site-guest.service'
import { formatDistanceToNow } from 'date-fns'
import { es, enUS, fr } from 'date-fns/locale'
import { useTranslation } from '@/lib/i18n/hooks'

interface SiteGuestListProps {
  onSelectGuest: (guest: SiteGuest) => void
  onAddGuest: () => void
  onManagePermissions: (guest: SiteGuest) => void
  onViewLogs: (guest: SiteGuest) => void
  onViewShares?: (guest: SiteGuest) => void
}

export function SiteGuestList({
  onSelectGuest,
  onAddGuest,
  onManagePermissions,
  onViewLogs,
  onViewShares
}: SiteGuestListProps) {
  const { t, language } = useTranslation()
  const [guests, setGuests] = useState<SiteGuest[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [includeInactive, setIncludeInactive] = useState(false)

  const siteGuestService = useSiteGuestService()

  // Get date-fns locale based on current language
  const getDateLocale = () => {
    switch (language) {
      case 'es': return es
      case 'fr': return fr
      default: return enUS
    }
  }

  const loadGuests = async () => {
    setIsLoading(true)
    setError(null)

    try {
      const response = await siteGuestService.listGuests({
        page,
        per_page: 20,
        include_inactive: includeInactive
      })

      if (response.error) {
        setError(response.error)
      } else if (response.data) {
        setGuests(response.data.guests)
        setTotal(response.data.total)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error loading guests')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadGuests()
  }, [page, includeInactive])

  const handleResendInvitation = async (guest: SiteGuest) => {
    try {
      const response = await siteGuestService.resendInvitation(guest.id)
      if (response.error) {
        alert(`Error: ${response.error}`)
      } else {
        alert('Invitation sent successfully')
      }
    } catch (err) {
      alert('Failed to send invitation')
    }
  }

  const handleDeactivate = async (guest: SiteGuest) => {
    if (!confirm(`Are you sure you want to deactivate ${guest.email}?`)) return

    try {
      const response = await siteGuestService.deactivateGuest(guest.id)
      if (response.error) {
        alert(`Error: ${response.error}`)
      } else {
        loadGuests()
      }
    } catch (err) {
      alert('Failed to deactivate guest')
    }
  }

  const getPermissionBadges = (guest: SiteGuest) => {
    const badges = []
    if (guest.can_view) badges.push(<Badge key="view" variant="secondary" className="mr-1"><Eye className="h-3 w-3 mr-1" />{t('siteGuest.guests.permissions.view')}</Badge>)
    if (guest.can_download) badges.push(<Badge key="download" variant="secondary" className="mr-1"><Download className="h-3 w-3 mr-1" />{t('siteGuest.guests.permissions.download')}</Badge>)
    if (guest.can_upload) badges.push(<Badge key="upload" variant="secondary" className="mr-1"><Upload className="h-3 w-3 mr-1" />{t('siteGuest.guests.permissions.upload')}</Badge>)
    return badges
  }

  const getStatusBadge = (guest: SiteGuest) => {
    if (!guest.is_active) {
      return <Badge variant="destructive">{t('siteGuest.guests.status.inactive')}</Badge>
    }
    if (guest.is_expired) {
      return <Badge variant="outline" className="text-orange-600 border-orange-600">{t('common.expired') || 'Expired'}</Badge>
    }
    return <Badge variant="default" className="bg-green-600">{t('siteGuest.guests.status.active')}</Badge>
  }

  if (error) {
    return (
      <div className="text-center py-8">
        <p className="text-destructive mb-4">{error}</p>
        <Button onClick={loadGuests} variant="outline">
          <RefreshCw className="h-4 w-4 mr-2" />
          {t('common.refresh')}
        </Button>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <div className="flex items-center gap-4">
          <h3 className="text-lg font-semibold">{t('siteGuest.guests.title')} ({total})</h3>
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            <input
              type="checkbox"
              checked={includeInactive}
              onChange={(e) => setIncludeInactive(e.target.checked)}
              className="rounded"
            />
            {t('siteGuest.guests.status.inactive')}
          </label>
        </div>
        <div className="flex gap-2">
          <Button onClick={loadGuests} variant="outline" size="sm">
            <RefreshCw className="h-4 w-4 mr-2" />
            {t('common.refresh')}
          </Button>
          <Button onClick={onAddGuest} size="sm">
            <Plus className="h-4 w-4 mr-2" />
            {t('siteGuest.guests.addGuest')}
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="text-center py-8">
          <RefreshCw className="h-6 w-6 animate-spin mx-auto mb-2" />
          <p className="text-muted-foreground">{t('common.loading')}</p>
        </div>
      ) : guests.length === 0 ? (
        <div className="text-center py-8 border rounded-lg">
          <p className="text-muted-foreground mb-4">{t('siteGuest.guests.noGuests.title')}</p>
          <Button onClick={onAddGuest}>
            <Plus className="h-4 w-4 mr-2" />
            {t('siteGuest.guests.addGuest')}
          </Button>
        </div>
      ) : (
        <div className="border rounded-lg">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('siteGuest.guests.table.email')}</TableHead>
                <TableHead>{t('siteGuest.guests.table.name')}</TableHead>
                <TableHead>{t('siteGuest.guests.table.status')}</TableHead>
                <TableHead>{t('siteGuest.guests.table.permissions')}</TableHead>
                <TableHead>{t('siteGuest.guests.table.lastAccess')}</TableHead>
                <TableHead>{t('siteGuest.guests.table.accessCount')}</TableHead>
                <TableHead className="w-[50px]"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {guests.map((guest) => (
                <TableRow key={guest.id} className="cursor-pointer" onClick={() => onSelectGuest(guest)}>
                  <TableCell className="font-medium">{guest.email}</TableCell>
                  <TableCell>{guest.name || '-'}</TableCell>
                  <TableCell>{getStatusBadge(guest)}</TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {getPermissionBadges(guest)}
                    </div>
                  </TableCell>
                  <TableCell>
                    {guest.last_access_at
                      ? formatDistanceToNow(new Date(guest.last_access_at), { addSuffix: true, locale: getDateLocale() })
                      : t('siteGuest.guests.table.never')
                    }
                  </TableCell>
                  <TableCell>{guest.access_count}</TableCell>
                  <TableCell>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
                        <Button variant="ghost" size="sm">
                          <MoreHorizontal className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={(e) => { e.stopPropagation(); onSelectGuest(guest); }}>
                          {t('siteGuest.guests.actions.edit')}
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={(e) => { e.stopPropagation(); onManagePermissions(guest); }}>
                          <Shield className="h-4 w-4 mr-2" />
                          {t('siteGuest.guests.actions.viewPermissions')}
                        </DropdownMenuItem>
                        {onViewShares && (
                          <DropdownMenuItem onClick={(e) => { e.stopPropagation(); onViewShares(guest); }}>
                            <FolderOpen className="h-4 w-4 mr-2" />
                            Ver colecciones
                          </DropdownMenuItem>
                        )}
                        <DropdownMenuItem onClick={(e) => { e.stopPropagation(); onViewLogs(guest); }}>
                          <History className="h-4 w-4 mr-2" />
                          {t('siteGuest.guests.actions.viewLogs')}
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem onClick={(e) => { e.stopPropagation(); handleResendInvitation(guest); }}>
                          <Mail className="h-4 w-4 mr-2" />
                          {t('siteGuest.guests.actions.resendInvite')}
                        </DropdownMenuItem>
                        {guest.is_active && (
                          <DropdownMenuItem
                            className="text-destructive"
                            onClick={(e) => { e.stopPropagation(); handleDeactivate(guest); }}
                          >
                            <UserX className="h-4 w-4 mr-2" />
                            {t('siteGuest.guests.actions.deactivate')}
                          </DropdownMenuItem>
                        )}
                      </DropdownMenuContent>
                    </DropdownMenu>
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
  )
}
