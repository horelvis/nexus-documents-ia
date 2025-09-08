"use client"

import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { 
  getStatusLabel, 
  getStatusVariant, 
  getStatusColor, 
  getStatusDescription,
  isDocumentProcessing,
  needsAttention 
} from '@/lib/document-utils'
import { IconLoader2, IconCheck, IconAlertCircle, IconClock } from '@tabler/icons-react'

interface DocumentStatusIndicatorProps {
  status: string | number | null | undefined
  showDescription?: boolean
  showIcon?: boolean
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

export function DocumentStatusIndicator({ 
  status, 
  showDescription = false,
  showIcon = true,
  size = 'md',
  className = ""
}: DocumentStatusIndicatorProps) {
  const getStatusIcon = () => {
    if (!showIcon) return null
    
    if (isDocumentProcessing(status)) {
      return <IconLoader2 className="h-3 w-3 animate-spin" />
    }
    
    if (needsAttention(status)) {
      return <IconAlertCircle className="h-3 w-3" />
    }
    
    if (status === 1 || status === 'INDEXED') {
      return <IconCheck className="h-3 w-3" />
    }
    
    return <IconClock className="h-3 w-3" />
  }

  const sizeClasses = {
    sm: 'text-xs px-2 py-0.5',
    md: 'text-sm px-2.5 py-1',
    lg: 'text-base px-3 py-1.5'
  }

  const statusLabel = getStatusLabel(status)
  const statusDescription = getStatusDescription(status)
  
  const BadgeContent = (
    <Badge 
      variant={getStatusVariant(status)} 
      className={`${getStatusColor(status)} ${sizeClasses[size]} flex items-center gap-1.5 ${className}`}
    >
      {getStatusIcon()}
      {statusLabel}
    </Badge>
  )

  if (showDescription) {
    return (
      <div className="flex flex-col items-end gap-1">
        {BadgeContent}
        <span className="text-xs text-muted-foreground">
          {statusDescription}
        </span>
      </div>
    )
  }

  // Always show tooltip with description for better UX
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          {BadgeContent}
        </TooltipTrigger>
        <TooltipContent>
          <p className="text-sm">{statusDescription}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}