"use client"

import { useState, useEffect } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { FolderOpen, FileText, Eye, Download, Upload, RefreshCw } from 'lucide-react'
import { useSiteGuestService, SiteGuest, SiteGuestShare } from '@/lib/services/site-guest.service'
import { formatDistanceToNow, format } from 'date-fns'
import { es, enUS } from 'date-fns/locale'
import { useTranslation } from '@/lib/i18n/hooks'

interface SiteGuestSharesProps {
  guest: SiteGuest
  open: boolean
  onClose: () => void
}

export function SiteGuestShares({ guest, open, onClose }: SiteGuestSharesProps) {
  const { t, language } = useTranslation()
  const [shares, setShares] = useState<SiteGuestShare[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const siteGuestService = useSiteGuestService()

  const getDateLocale = () => language === 'es' ? es : enUS

  const loadShares = async () => {
    setIsLoading(true)
    setError(null)

    try {
      const response = await siteGuestService.listGuestShares(guest.id)

      if (response.error) {
        setError(response.error)
      } else if (response.data) {
        setShares(response.data.shares)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error loading shares')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    if (open && guest) {
      loadShares()
    }
  }, [open, guest?.id])

  const getPermissionIcon = (permissionType: string) => {
    switch (permissionType) {
      case 'download':
        return <Download className="h-3 w-3 mr-1" />
      case 'upload':
        return <Upload className="h-3 w-3 mr-1" />
      default:
        return <Eye className="h-3 w-3 mr-1" />
    }
  }

  const getPermissionLabel = (permissionType: string) => {
    switch (permissionType) {
      case 'download':
        return 'Ver y descargar'
      case 'upload':
        return 'Ver, descargar y subir'
      default:
        return 'Solo ver'
    }
  }

  const isExpired = (expiresAt: string | null) => {
    if (!expiresAt) return false
    return new Date(expiresAt) < new Date()
  }

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent className="sm:max-w-[800px] max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-100">
              <FolderOpen className="h-4 w-4 text-blue-600" />
            </div>
            Colecciones compartidas
          </DialogTitle>
          <DialogDescription>
            Documentos compartidos con {guest.email}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="flex justify-between items-center">
            <span className="text-sm text-muted-foreground">
              {shares.length} colección(es)
            </span>
            <Button onClick={loadShares} variant="outline" size="sm" disabled={isLoading}>
              <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
              Actualizar
            </Button>
          </div>

          {isLoading ? (
            <div className="text-center py-8">
              <RefreshCw className="h-6 w-6 animate-spin mx-auto mb-2" />
              <p className="text-muted-foreground">Cargando colecciones...</p>
            </div>
          ) : error ? (
            <div className="p-3 bg-destructive/10 text-destructive text-sm rounded-md">
              {error}
              <Button onClick={loadShares} variant="outline" size="sm" className="ml-4">
                Reintentar
              </Button>
            </div>
          ) : shares.length === 0 ? (
            <div className="text-center py-8 border rounded-lg">
              <FolderOpen className="h-10 w-10 mx-auto text-muted-foreground mb-3" />
              <p className="text-muted-foreground">No hay colecciones compartidas</p>
              <p className="text-sm text-muted-foreground mt-1">
                Comparte documentos desde la página de Documents
              </p>
            </div>
          ) : (
            <div className="border rounded-lg">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Colección</TableHead>
                    <TableHead>Docs</TableHead>
                    <TableHead>Permisos</TableHead>
                    <TableHead>Creada</TableHead>
                    <TableHead>Expira</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {shares.map((share) => (
                    <TableRow key={share.id}>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <FolderOpen className="h-4 w-4 text-blue-500 flex-shrink-0" />
                          <div className="min-w-0">
                            <p className="font-medium truncate">{share.name}</p>
                            {share.description && (
                              <p className="text-xs text-muted-foreground truncate">
                                {share.description}
                              </p>
                            )}
                          </div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-1">
                          <FileText className="h-4 w-4 text-muted-foreground" />
                          <span>{share.document_count}</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="secondary" className="gap-1 text-xs">
                          {getPermissionIcon(share.permission_type)}
                          {getPermissionLabel(share.permission_type)}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground whitespace-nowrap">
                        {formatDistanceToNow(new Date(share.created_at), {
                          addSuffix: true,
                          locale: getDateLocale()
                        })}
                      </TableCell>
                      <TableCell>
                        {share.expires_at ? (
                          isExpired(share.expires_at) ? (
                            <Badge variant="destructive" className="text-xs">
                              Expirado
                            </Badge>
                          ) : (
                            <span className="text-sm whitespace-nowrap">
                              {format(new Date(share.expires_at), 'dd/MM/yyyy')}
                            </span>
                          )
                        ) : (
                          <span className="text-sm text-muted-foreground">-</span>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
