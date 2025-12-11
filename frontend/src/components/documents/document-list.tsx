"use client"

import { useState } from "react"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import {
  IconFile,
  IconFileText,
  IconFileTypePdf,
  IconFileTypeDocx,
  IconFileSpreadsheet,
  IconPhoto,
  IconClock,
  IconEye,
  IconDownload,
  IconTrash,
  IconEdit,
  IconShare2,
  IconSignature,
  IconDotsVertical,
  IconAlertTriangle,
  IconWeight,
  IconMessageCircle,
  IconCheck,
  IconLock,
  IconUsers,
  IconWorld,
  IconShieldCheck,
  IconUserCheck
} from "@tabler/icons-react"
import { Checkbox } from "@/components/ui/checkbox"
import { formatDistanceToNow } from "date-fns"
import { EffectivePermissions } from "@/lib/types"

interface DocumentListProps {
  documents: any[]
  loading?: boolean
  viewMode?: 'grid' | 'table'
  showScore?: boolean
  showHighlights?: boolean
  useDetailedView?: boolean
  onDocumentClick?: (document: any) => void
  onDownload?: (document: any) => void
  onDelete?: (document: any) => void
  onShare?: (document: any) => void
  onEdit?: (document: any) => void
  onSignature?: (document: any) => void
  onAskEmma?: (document: any) => void
  emptyMessage?: string
  // Selection props
  selectable?: boolean
  selectedIds?: Set<string>
  onToggleSelection?: (documentId: string) => void
  // ACL permissions - if provided, actions are filtered based on permissions
  showPermissionBadges?: boolean
}

interface DocumentItemProps {
  document: any
  showScore?: boolean
  showHighlights?: boolean
  useDetailedView?: boolean
  onDocumentClick?: (document: any) => void
  onDownload?: (document: any) => void
  onDelete?: (document: any) => void
  onShare?: (document: any) => void
  onEdit?: (document: any) => void
  onSignature?: (document: any) => void
  onAskEmma?: (document: any) => void
  // Selection props
  selectable?: boolean
  isSelected?: boolean
  onToggleSelection?: () => void
  // ACL permissions
  showPermissionBadges?: boolean
}

// Helper functions
const getFileIcon = (fileType: string, mimeType?: string, filename?: string) => {
  let type = fileType?.toLowerCase()

  // Fallback: extract from mime_type or filename
  if (!type && mimeType) {
    if (mimeType.includes('pdf')) type = 'pdf'
    else if (mimeType.includes('opendocument.text')) type = 'odt'
    else if (mimeType.includes('opendocument.spreadsheet')) type = 'ods'
    else if (mimeType.includes('opendocument.presentation')) type = 'odp'
    else if (mimeType.includes('word') || mimeType.includes('document')) type = 'docx'
    else if (mimeType.includes('sheet') || mimeType.includes('excel')) type = 'xlsx'
    else if (mimeType.includes('image')) type = 'image'
    else if (mimeType.includes('text')) type = 'txt'
  }

  if (!type && filename) {
    const ext = filename.split('.').pop()?.toLowerCase()
    type = ext || 'unknown'
  }

  switch (type) {
    case 'pdf':
      return <IconFileTypePdf className="h-6 w-6 text-red-500" />
    case 'odt':
      return <IconFileTypeDocx className="h-6 w-6 text-cyan-500" />
    case 'ods':
      return <IconFileSpreadsheet className="h-6 w-6 text-teal-500" />
    case 'odp':
      return <IconFileText className="h-6 w-6 text-amber-500" />
    case 'docx':
    case 'doc':
    case 'document':
      return <IconFileTypeDocx className="h-6 w-6 text-blue-500" />
    case 'xlsx':
    case 'xls':
    case 'csv':
    case 'sheet':
      return <IconFileSpreadsheet className="h-6 w-6 text-green-500" />
    case 'jpg':
    case 'jpeg':
    case 'png':
    case 'gif':
    case 'bmp':
    case 'image':
      return <IconPhoto className="h-6 w-6 text-purple-500" />
    case 'txt':
    case 'text':
      return <IconFileText className="h-6 w-6 text-gray-500" />
    default:
      return <IconFile className="h-6 w-6 text-gray-500" />
  }
}

const formatFileSize = (bytes: number) => {
  if (!bytes || bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

// Get effective permissions from document (if available)
const getDocumentPermissions = (document: any): EffectivePermissions | null => {
  return document.current_user_permissions || null
}

// Determine visibility badge based on ACL info
const getVisibilityInfo = (document: any): { type: 'private' | 'shared' | 'public'; label: string; icon: React.ReactNode } => {
  const permissions = getDocumentPermissions(document)

  // If we have explicit visibility
  if (document.visibility) {
    switch (document.visibility) {
      case 'public':
        return { type: 'public', label: 'Público', icon: <IconWorld className="h-3 w-3" /> }
      case 'shared':
        return { type: 'shared', label: 'Compartido', icon: <IconUsers className="h-3 w-3" /> }
      default:
        return { type: 'private', label: 'Privado', icon: <IconLock className="h-3 w-3" /> }
    }
  }

  // Infer from permissions
  if (permissions) {
    if (permissions.from_everyone_acl) {
      return { type: 'public', label: 'Público', icon: <IconWorld className="h-3 w-3" /> }
    }
    if (permissions.from_user_acl || permissions.from_role_acl) {
      return { type: 'shared', label: 'Compartido', icon: <IconUsers className="h-3 w-3" /> }
    }
    if (permissions.is_owner) {
      return { type: 'private', label: 'Propietario', icon: <IconUserCheck className="h-3 w-3" /> }
    }
  }

  // Default (no ACL info available - assume public for backwards compatibility)
  return { type: 'public', label: 'Público', icon: <IconWorld className="h-3 w-3" /> }
}

// Check if user can perform action based on permissions
const canPerformAction = (document: any, action: 'view' | 'edit' | 'delete' | 'share'): boolean => {
  const permissions = getDocumentPermissions(document)

  // If no permissions info, allow all (backwards compatibility)
  if (!permissions) return true

  switch (action) {
    case 'view':
      return permissions.can_view
    case 'edit':
      return permissions.can_edit
    case 'delete':
      return permissions.can_delete
    case 'share':
      return permissions.can_share
    default:
      return false
  }
}

function DocumentItem({
  document,
  showScore,
  showHighlights,
  useDetailedView = false,
  onDocumentClick,
  onDownload,
  onDelete,
  onShare,
  onEdit,
  onSignature,
  onAskEmma,
  selectable = false,
  isSelected = false,
  onToggleSelection,
  showPermissionBadges = false
}: DocumentItemProps) {
  // Get permissions and visibility info
  const permissions = getDocumentPermissions(document)
  const visibilityInfo = getVisibilityInfo(document)

  // Check permissions for each action
  const canView = canPerformAction(document, 'view')
  const canEdit = canPerformAction(document, 'edit')
  const canDelete = canPerformAction(document, 'delete')
  const canShare = canPerformAction(document, 'share')

  const handleAction = (action: string, e: React.MouseEvent) => {
    e.stopPropagation()

    switch (action) {
      case 'download':
        if (canView) onDownload?.(document)
        break
      case 'delete':
        if (canDelete) onDelete?.(document)
        break
      case 'share':
        if (canShare) onShare?.(document)
        break
      case 'edit':
        if (canEdit) onEdit?.(document)
        break
      case 'signature':
        if (canEdit) onSignature?.(document)
        break
      case 'askEmma':
        if (canView) onAskEmma?.(document)
        break
    }
  }

  // Visibility badge component
  const VisibilityBadge = () => {
    if (!showPermissionBadges) return null

    const badgeColors = {
      private: 'bg-gray-100 text-gray-700 border-gray-300',
      shared: 'bg-blue-100 text-blue-700 border-blue-300',
      public: 'bg-green-100 text-green-700 border-green-300'
    }

    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Badge
              variant="outline"
              className={`text-[10px] px-1.5 py-0 h-5 gap-1 ${badgeColors[visibilityInfo.type]}`}
            >
              {visibilityInfo.icon}
              {visibilityInfo.label}
            </Badge>
          </TooltipTrigger>
          <TooltipContent>
            <p className="text-xs">
              {visibilityInfo.type === 'private' && 'Solo tú puedes ver este documento'}
              {visibilityInfo.type === 'shared' && 'Compartido con usuarios específicos'}
              {visibilityInfo.type === 'public' && 'Visible para todos en el tenant'}
            </p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    )
  }

  // Permission indicator for owner/admin
  const PermissionIndicator = () => {
    if (!showPermissionBadges || !permissions) return null

    if (permissions.is_owner) {
      return (
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Badge variant="outline" className="text-[10px] px-1.5 py-0 h-5 gap-1 bg-amber-100 text-amber-700 border-amber-300">
                <IconShieldCheck className="h-3 w-3" />
                Propietario
              </Badge>
            </TooltipTrigger>
            <TooltipContent>
              <p className="text-xs">Tienes control total sobre este documento</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      )
    }

    if (permissions.is_admin) {
      return (
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Badge variant="outline" className="text-[10px] px-1.5 py-0 h-5 gap-1 bg-purple-100 text-purple-700 border-purple-300">
                <IconShieldCheck className="h-3 w-3" />
                Admin
              </Badge>
            </TooltipTrigger>
            <TooltipContent>
              <p className="text-xs">Acceso administrativo completo</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      )
    }

    return null
  }

  if (useDetailedView) {
    // Detailed view matching Document Library design
    return (
      <Card className={`hover:shadow-lg transition-shadow cursor-default group ${isSelected ? 'ring-2 ring-primary bg-primary/5' : ''}`}>
        <CardContent className="p-4">
          <div className="flex items-start gap-3">
            {/* Selection Checkbox */}
            {selectable && (
              <div className="flex-shrink-0 pt-0.5" onClick={(e) => e.stopPropagation()}>
                <Checkbox
                  checked={isSelected}
                  onCheckedChange={() => onToggleSelection?.()}
                  className="h-5 w-5"
                />
              </div>
            )}
            {/* File Icon */}
            <div className="flex-shrink-0">
              {getFileIcon(document.file_type, document.mime_type, document.filename)}
            </div>

            {/* Document Info */}
            <div className="flex-grow min-w-0">
            <div className="flex items-start justify-between gap-2 mb-1">
              <div className="min-w-0 flex-1">
                <h3
                  className="text-base font-medium truncate cursor-pointer hover:text-primary hover:underline"
                  title={document.title || document.filename}
                  onClick={() => onDocumentClick?.(document)}
                >
                  {document.title || document.filename}
                </h3>
                {document.description && (
                  <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">
                    {document.description}
                  </p>
                )}
                {/* Category and Permission badges */}
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  {document.category && (
                    <Badge
                      variant="secondary"
                      className="text-[10px] uppercase tracking-wide bg-primary/10 text-primary border-primary/20"
                    >
                      {document.category}
                    </Badge>
                  )}
                  <VisibilityBadge />
                  <PermissionIndicator />
                </div>
              </div>

            </div>

              {/* Score */}
              {showScore && document.score && (
                <div className="flex items-center gap-2 mb-2">
                  <IconWeight className="h-3 w-3 text-muted-foreground" />
                  <span className="text-xs text-muted-foreground">
                    Match: {Math.round(document.score * 100)}%
                  </span>
                </div>
              )}

              {/* Highlights */}
              {showHighlights && (document.search_matches || document.matches) && (document.search_matches || document.matches).length > 0 && (
                <div className="mb-2">
                  <p className="text-xs text-muted-foreground mb-1">Contenido relevante:</p>
                  <div className="space-y-1">
                    {(document.search_matches || document.matches).slice(0, 2).map((match: any, idx: number) => (
                      <div
                        key={idx}
                        className="text-xs bg-muted/80 text-muted-foreground border border-border p-2 rounded-md shadow-sm dark:bg-slate-900/50 dark:text-slate-100 dark:border-slate-800 line-clamp-2 [&>mark]:bg-primary/20 [&>mark]:text-primary [&>mark]:px-0.5 [&>mark]:rounded-sm"
                        dangerouslySetInnerHTML={{ __html: match.text || match }}
                      />
                    ))}
                    {(document.search_matches || document.matches).length > 2 && (
                      <p className="text-xs text-muted-foreground">
                        +{(document.search_matches || document.matches).length - 2} more matches
                      </p>
                    )}
                  </div>
                </div>
              )}

              {/* Metadata and Actions */}
              <div className="flex items-center justify-between gap-2 mb-1">
                <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <span>Tamaño: {formatFileSize(document.file_size)}</span>
                  <span>•</span>
                  <span>Subido: {new Date(document.created_at).toLocaleDateString()}</span>
                  {document.created_by?.full_name && (
                    <>
                      <span>•</span>
                      <span>Por {document.created_by.full_name}</span>
                    </>
                  )}
                </div>

                {/* Actions */}
                <div className="flex gap-0.5 flex-shrink-0" onClick={(e) => e.stopPropagation()}>
                  {/* 3 Main Actions - conditioned by permissions */}
                  {canView && (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={(e) => {
                        e.stopPropagation()
                        onDocumentClick?.(document)
                      }}
                      title="Ver documento"
                      className="h-7 w-7 p-0 opacity-80 group-hover:opacity-100"
                    >
                      <IconEye className="h-3.5 w-3.5" />
                    </Button>
                  )}
                  {canView && (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={(e) => handleAction('download', e)}
                      title="Descargar"
                      className="h-7 w-7 p-0 opacity-80 group-hover:opacity-100"
                    >
                      <IconDownload className="h-3.5 w-3.5" />
                    </Button>
                  )}
                  {canShare && (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={(e) => handleAction('share', e)}
                      title="Compartir"
                      className="h-7 w-7 p-0 opacity-80 group-hover:opacity-100"
                    >
                      <IconShare2 className="h-3.5 w-3.5" />
                    </Button>
                  )}

                  {/* More Actions Dropdown */}
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={(e) => e.stopPropagation()}
                        title="Más acciones"
                        className="h-7 w-7 p-0 opacity-80 group-hover:opacity-100"
                      >
                        <IconDotsVertical className="h-3.5 w-3.5" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      {canView && (
                        <DropdownMenuItem onClick={(e) => { e.stopPropagation(); onDocumentClick?.(document) }}>
                          <IconEye className="mr-2 h-4 w-4" />
                          Ver documento
                        </DropdownMenuItem>
                      )}
                      {canView && onAskEmma && (
                        <DropdownMenuItem onClick={(e) => handleAction('askEmma', e)}>
                          <IconMessageCircle className="mr-2 h-4 w-4" />
                          Ask Emma
                        </DropdownMenuItem>
                      )}
                      {canView && (
                        <DropdownMenuItem onClick={(e) => handleAction('download', e)}>
                          <IconDownload className="mr-2 h-4 w-4" />
                          Descargar
                        </DropdownMenuItem>
                      )}
                      {canEdit && onEdit && (
                        <DropdownMenuItem onClick={(e) => handleAction('edit', e)}>
                          <IconEdit className="mr-2 h-4 w-4" />
                          Editar
                        </DropdownMenuItem>
                      )}
                      {canEdit && (
                        <DropdownMenuItem onClick={(e) => handleAction('signature', e)}>
                          <IconSignature className="mr-2 h-4 w-4" />
                          Solicitar firma
                        </DropdownMenuItem>
                      )}
                      {canShare && (
                        <DropdownMenuItem onClick={(e) => handleAction('share', e)}>
                          <IconShare2 className="mr-2 h-4 w-4" />
                          Compartir
                        </DropdownMenuItem>
                      )}
                      {canDelete && onDelete && (
                        <>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            onClick={(e) => handleAction('delete', e)}
                            className="text-red-600 focus:text-red-600"
                          >
                            <IconTrash className="mr-2 h-4 w-4" />
                            Eliminar
                          </DropdownMenuItem>
                        </>
                      )}
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              </div>

              {/* Tags */}
              {(document.tags || []).length > 0 && (
                <div className="flex flex-wrap gap-0.5">
                  {(document.tags || []).map((tag: string) => (
                    <Badge key={tag} variant="outline" className="text-xs px-1.5 py-0 h-5">
                      {tag}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          </div>
        </CardContent>
      </Card>
    )
  }

  // Simple view (original design)
  return (
    <Card className={`hover:shadow-lg transition-shadow cursor-default group ${isSelected ? 'ring-2 ring-primary bg-primary/5' : ''}`}>
      <CardContent className="p-4">
        <div className="flex items-start gap-3">
          {/* Selection Checkbox */}
          {selectable && (
            <div className="flex-shrink-0 pt-0.5" onClick={(e) => e.stopPropagation()}>
              <Checkbox
                checked={isSelected}
                onCheckedChange={() => onToggleSelection?.()}
                className="h-5 w-5"
              />
            </div>
          )}
          {/* File Icon */}
          <div className="flex-shrink-0">
            {getFileIcon(document.file_type, document.mime_type, document.filename)}
          </div>

          {/* Document Info */}
          <div className="flex-grow min-w-0">
            <div className="flex items-start justify-between gap-2 mb-1">
              <div className="min-w-0 flex-1">
                <h3
                  className="text-base font-medium truncate cursor-pointer hover:text-primary hover:underline"
                  title={document.title || document.filename}
                  onClick={() => onDocumentClick?.(document)}
                >
                  {document.title || document.filename}
                </h3>
                {document.description && (
                  <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                    {document.description}
                  </p>
                )}
                {/* Category and Permission badges */}
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  {document.category && (
                    <Badge
                      variant="secondary"
                      className="text-[10px] uppercase tracking-wide bg-primary/10 text-primary border-primary/20"
                    >
                      {document.category}
                    </Badge>
                  )}
                  <VisibilityBadge />
                  <PermissionIndicator />
                </div>
              </div>

            </div>

            {/* Score */}
            {showScore && document.score && (
              <div className="flex items-center gap-2 mb-2">
                <IconWeight className="h-3 w-3 text-muted-foreground" />
                <span className="text-xs text-muted-foreground">
                  Match: {Math.round(document.score * 100)}%
                </span>
              </div>
            )}

            {/* Highlights */}
              {showHighlights && (document.search_matches || document.matches) && (document.search_matches || document.matches).length > 0 && (
                <div className="mb-2">
                  <p className="text-xs text-muted-foreground mb-1">Contenido relevante:</p>
                  <div className="space-y-1">
                    {(document.search_matches || document.matches).slice(0, 2).map((match: any, idx: number) => (
                      <div
                        key={idx}
                        className="text-xs bg-muted/80 text-muted-foreground p-2 rounded-md border border-border shadow-sm dark:bg-slate-900/50 dark:text-slate-100 dark:border-slate-800 line-clamp-2 [&>mark]:bg-primary/20 [&>mark]:text-primary [&>mark]:px-0.5 [&>mark]:rounded-sm"
                        dangerouslySetInnerHTML={{ __html: match.text || match }}
                      />
                    ))}
                    {(document.search_matches || document.matches).length > 2 && (
                      <p className="text-xs text-muted-foreground">
                      +{(document.search_matches || document.matches).length - 2} more matches
                    </p>
                  )}
                </div>
              </div>
            )}

            {/* Metadata */}
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <div className="flex items-center gap-3">
                <span className="flex items-center gap-1">
                  <IconClock className="h-3 w-3" />
                  {document.created_at ? formatDistanceToNow(new Date(document.created_at), { addSuffix: true }) : 'Unknown'}
                </span>
                {document.file_size && (
                  <span>{formatFileSize(document.file_size)}</span>
                )}
                {document.tags && document.tags.length > 0 && (
                  <div className="flex gap-1">
                    {document.tags.slice(0, 2).map((tag: string, idx: number) => (
                      <Badge key={idx} variant="outline" className="text-xs h-4 px-1">
                        {tag}
                      </Badge>
                    ))}
                  </div>
                )}
              </div>

              {/* Actions - conditioned by permissions */}
              <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                {canView && (
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6"
                    onClick={(e) => handleAction('download', e)}
                    title="Descargar"
                  >
                    <IconDownload className="h-3 w-3" />
                  </Button>
                )}

                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <IconDotsVertical className="h-3 w-3" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    {canView && onAskEmma && (
                      <DropdownMenuItem onClick={(e) => handleAction('askEmma', e)}>
                        <IconMessageCircle className="h-4 w-4 mr-2" />
                        Ask Emma
                      </DropdownMenuItem>
                    )}
                    {canView && (
                      <DropdownMenuItem onClick={(e) => handleAction('download', e)}>
                        <IconDownload className="h-4 w-4 mr-2" />
                        Descargar
                      </DropdownMenuItem>
                    )}
                    {canEdit && onEdit && (
                      <DropdownMenuItem onClick={(e) => handleAction('edit', e)}>
                        <IconEdit className="h-4 w-4 mr-2" />
                        Editar
                      </DropdownMenuItem>
                    )}
                    {canShare && (
                      <DropdownMenuItem onClick={(e) => handleAction('share', e)}>
                        <IconShare2 className="h-4 w-4 mr-2" />
                        Compartir
                      </DropdownMenuItem>
                    )}
                    {canEdit && (
                      <DropdownMenuItem onClick={(e) => handleAction('signature', e)}>
                        <IconSignature className="h-4 w-4 mr-2" />
                        Solicitar firma
                      </DropdownMenuItem>
                    )}
                    {canDelete && onDelete && (
                      <>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem
                            onClick={(e) => handleAction('delete', e)}
                            className="text-red-600 focus:text-red-600"
                          >
                            <IconTrash className="h-4 w-4 mr-2" />
                            Eliminar
                          </DropdownMenuItem>
                      </>
                    )}
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export function DocumentList({
  documents,
  loading,
  viewMode = 'grid',
  showScore = false,
  showHighlights = false,
  useDetailedView = false,
  onDocumentClick,
  onDownload,
  onDelete,
  onShare,
  onEdit,
  onSignature,
  onAskEmma,
  emptyMessage = "No documents found",
  selectable = false,
  selectedIds,
  onToggleSelection,
  showPermissionBadges = false
}: DocumentListProps) {
  if (loading) {
    return (
      <div className="flex justify-center items-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
        <span className="ml-2 text-muted-foreground">Loading documents...</span>
      </div>
    )
  }

  if (!documents || documents.length === 0) {
    return (
      <Card className="text-center py-12">
        <CardContent>
          <IconAlertTriangle className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
          <p className="text-muted-foreground">{emptyMessage}</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className={viewMode === 'grid'
      ? "grid grid-cols-1 gap-4"
      : "space-y-3"
    }>
      {documents.map((document, index) => (
        <DocumentItem
          key={document.id || index}
          document={document}
          showScore={showScore}
          showHighlights={showHighlights}
          useDetailedView={useDetailedView}
          onDocumentClick={onDocumentClick}
          onDownload={onDownload}
          onDelete={onDelete}
          onShare={onShare}
          onEdit={onEdit}
          onSignature={onSignature}
          onAskEmma={onAskEmma}
          selectable={selectable}
          isSelected={selectedIds?.has(document.id)}
          onToggleSelection={() => onToggleSelection?.(document.id)}
          showPermissionBadges={showPermissionBadges}
        />
      ))}
    </div>
  )
}
