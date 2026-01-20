'use client'

/**
 * Real brand icons for connectors
 * Using inline SVGs for better performance and consistency
 */

import { cn } from '@/lib/utils'
import { ConnectorType } from '@/lib/services/connector.service'

interface IconProps {
  className?: string
}

// Microsoft SharePoint
function SharePointIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="10" cy="8" r="6" fill="#036C70" />
      <circle cx="16" cy="14" r="5" fill="#1A9BA1" />
      <circle cx="9" cy="17" r="4" fill="#37C6D0" />
    </svg>
  )
}

// Microsoft OneDrive
function OneDriveIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M9.5 14.5L14 9L19.5 12.5C20.5 13 21 14 21 15C21 16.5 19.5 18 18 18H6C4 18 2.5 16.5 2.5 14.5C2.5 12.5 4 11 6 11C6 11 6.5 8 9.5 8C12.5 8 14 10 14 10" fill="#0078D4" />
      <path d="M14 10C14 10 15 8 17.5 8C20 8 21.5 10 21.5 12C21.5 12 22 12 22 12" fill="#0364B8" />
    </svg>
  )
}

// Google Drive
function GoogleDriveIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M8.5 3L1 15.5H6L13.5 3H8.5Z" fill="#0066DA" />
      <path d="M15.5 3L8 15.5H13L20.5 3H15.5Z" fill="#00AC47" />
      <path d="M22 15.5L17 7L12 15.5L14.5 20H19.5L22 15.5Z" fill="#EA4335" />
      <path d="M2 15.5L4.5 20H14.5L12 15.5H2Z" fill="#00832D" />
      <path d="M8 15.5L10.5 11L15.5 11L13 15.5H8Z" fill="#2684FC" />
      <path d="M17 7L14.5 11L12 15.5L17 7Z" fill="#FFBA00" />
    </svg>
  )
}

// Google Workspace (G Suite)
function GoogleWorkspaceIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
      <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
      <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
      <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
    </svg>
  )
}

// Dropbox
function DropboxIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M6 2L0 6L6 10L0 14L6 18L12 14L18 18L24 14L18 10L24 6L18 2L12 6L6 2Z" fill="#0061FF"/>
      <path d="M6 2L12 6L6 10L0 6L6 2Z" fill="#0061FF"/>
      <path d="M18 2L12 6L18 10L24 6L18 2Z" fill="#0061FF"/>
      <path d="M0 14L6 10L12 14L6 18L0 14Z" fill="#0061FF"/>
      <path d="M24 14L18 10L12 14L18 18L24 14Z" fill="#0061FF"/>
      <path d="M6 19L12 15L18 19L12 23L6 19Z" fill="#0061FF"/>
    </svg>
  )
}

// Box
function BoxIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M12 2L2 7V17L12 22L22 17V7L12 2Z" fill="#0061D5"/>
      <path d="M12 2L2 7L12 12L22 7L12 2Z" fill="#0061D5"/>
      <path d="M12 12V22L2 17V7L12 12Z" fill="#0061D5" fillOpacity="0.8"/>
      <path d="M12 12V22L22 17V7L12 12Z" fill="#0061D5" fillOpacity="0.6"/>
    </svg>
  )
}

// Amazon S3
function S3Icon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M12 2L3 6V18L12 22L21 18V6L12 2Z" fill="#569A31"/>
      <path d="M12 2L3 6L12 10L21 6L12 2Z" fill="#759C3E"/>
      <path d="M12 10V22L3 18V6L12 10Z" fill="#569A31"/>
      <path d="M12 10V22L21 18V6L12 10Z" fill="#4B612C"/>
      <ellipse cx="12" cy="12" rx="3" ry="1.5" fill="white" fillOpacity="0.3"/>
      <ellipse cx="12" cy="14" rx="3" ry="1.5" fill="white" fillOpacity="0.3"/>
      <ellipse cx="12" cy="16" rx="3" ry="1.5" fill="white" fillOpacity="0.3"/>
    </svg>
  )
}

// Azure Blob Storage
function AzureBlobIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M12 2L2 7L12 12L22 7L12 2Z" fill="#0078D4"/>
      <path d="M2 7V17L12 22V12L2 7Z" fill="#50E6FF"/>
      <path d="M22 7V17L12 22V12L22 7Z" fill="#0078D4"/>
      <circle cx="7" cy="12" r="1.5" fill="white"/>
      <circle cx="12" cy="14" r="1.5" fill="white"/>
      <circle cx="17" cy="12" r="1.5" fill="white"/>
    </svg>
  )
}

// Network Share / SMB
function NetworkShareIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="2" y="4" width="8" height="6" rx="1" fill="#6B7280"/>
      <rect x="14" y="4" width="8" height="6" rx="1" fill="#6B7280"/>
      <rect x="8" y="14" width="8" height="6" rx="1" fill="#6B7280"/>
      <path d="M6 10V12H12V14" stroke="#6B7280" strokeWidth="2"/>
      <path d="M18 10V12H12V14" stroke="#6B7280" strokeWidth="2"/>
    </svg>
  )
}

// Alfresco
function AlfrescoIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="12" cy="12" r="10" fill="#00A3D9"/>
      <path d="M8 8L12 6L16 8V12L12 14L8 12V8Z" fill="white"/>
      <path d="M8 12L12 14L16 12V16L12 18L8 16V12Z" fill="white" fillOpacity="0.7"/>
    </svg>
  )
}

// Map connector types to their icons
export const connectorIconComponents: Record<ConnectorType, React.FC<IconProps>> = {
  sharepoint: SharePointIcon,
  onedrive: OneDriveIcon,
  google_drive: GoogleDriveIcon,
  google_workspace: GoogleWorkspaceIcon,
  dropbox: DropboxIcon,
  box: BoxIcon,
  s3: S3Icon,
  azure_blob: AzureBlobIcon,
  network_share: NetworkShareIcon,
  alfresco: AlfrescoIcon,
}

// Helper component to render connector icon by type
interface ConnectorIconProps {
  type: ConnectorType
  className?: string
  size?: 'sm' | 'md' | 'lg' | 'xl'
}

const sizeClasses = {
  sm: 'h-6 w-6',
  md: 'h-8 w-8',
  lg: 'h-10 w-10',
  xl: 'h-12 w-12',
}

export function ConnectorIcon({ type, className, size = 'md' }: ConnectorIconProps) {
  const IconComponent = connectorIconComponents[type]
  if (!IconComponent) {
    return null
  }
  return <IconComponent className={cn(sizeClasses[size], className)} />
}
