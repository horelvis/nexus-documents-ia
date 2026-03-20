'use client'

/**
 * Official brand icons for connectors
 *
 * SVG paths sourced from:
 * - Simple Icons (cdn.jsdelivr.net/npm/simple-icons) — Google Drive, Dropbox, Box, OneDrive
 * - Vector Logo Zone (vectorlogo.zone) — Alfresco
 *
 * Network Share and Database use custom icons (no brand).
 */

import { cn } from '@/lib/utils'
import { ConnectorType } from '@/lib/services/connector.service'

interface IconProps {
  className?: string
}

// ─── Microsoft OneDrive ─────────────────────────────────────────────────────
// Source: Simple Icons — #0078D4
function OneDriveIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
      <path fill="#0078D4" d="M19.453 9.95q.961.058 1.787.468.826.41 1.442 1.066.615.657.966 1.512.352.856.352 1.816 0 1.008-.387 1.893-.386.885-1.049 1.547-.662.662-1.546 1.049-.885.387-1.893.387H6q-1.242 0-2.332-.475-1.09-.475-1.904-1.29-.815-.814-1.29-1.903Q0 14.93 0 13.688q0-.985.31-1.887.311-.903.862-1.658.55-.756 1.324-1.325.774-.568 1.711-.861.434-.129.85-.187.416-.06.861-.082h.012q.515-.786 1.207-1.413.691-.627 1.5-1.066.808-.44 1.705-.668.896-.229 1.845-.229 1.278 0 2.456.417 1.177.416 2.144 1.16.967.744 1.658 1.78.692 1.038 1.008 2.28zm-7.265-4.137q-1.325 0-2.52.544-1.195.545-2.04 1.565.446.117.85.299.405.181.792.416l4.78 2.86 2.731-1.15q.27-.117.545-.204.276-.088.58-.147-.293-.937-.855-1.705-.563-.768-1.319-1.318-.755-.551-1.658-.856-.902-.304-1.886-.304zM2.414 16.395l9.914-4.184-3.832-2.297q-.586-.351-1.23-.539-.645-.188-1.325-.188-.914 0-1.722.364-.809.363-1.412.978-.604.616-.955 1.436-.352.82-.352 1.723 0 .703.234 1.423.235.721.68 1.284zm16.711 1.793q.563 0 1.078-.176.516-.176.961-.516l-7.23-4.324-10.301 4.336q.527.328 1.13.504.604.175 1.237.175zm3.012-1.852q.363-.727.363-1.523 0-.774-.293-1.407t-.791-1.072q-.498-.44-1.166-.68-.668-.24-1.406-.24-.422 0-.838.1t-.815.252q-.398.152-.785.334-.386.181-.761.345Z" />
    </svg>
  )
}

// ─── Google Drive ───────────────────────────────────────────────────────────
// Source: Simple Icons — #4285F4
function GoogleDriveIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
      <path fill="#4285F4" d="M12.01 1.485c-2.082 0-3.754.02-3.743.047.01.02 1.708 3.001 3.774 6.62l3.76 6.574h3.76c2.081 0 3.753-.02 3.742-.047-.005-.02-1.708-3.001-3.775-6.62l-3.76-6.574zm-4.76 1.73a789.828 789.861 0 0 0-3.63 6.319L0 15.868l1.89 3.298 1.885 3.297 3.62-6.335 3.618-6.33-1.88-3.287C8.1 4.704 7.255 3.22 7.25 3.214zm2.259 12.653-.203.348c-.114.198-.96 1.672-1.88 3.287a423.93 423.948 0 0 1-1.698 2.97c-.01.026 3.24.042 7.222.042h7.244l1.796-3.157c.992-1.734 1.85-3.23 1.906-3.323l.104-.167h-7.249z" />
    </svg>
  )
}

// ─── Dropbox ────────────────────────────────────────────────────────────────
// Source: Simple Icons — #0061FF
function DropboxIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
      <path fill="#0061FF" d="M6 1.807L0 5.629l6 3.822 6.001-3.822L6 1.807zM18 1.807l-6 3.822 6 3.822 6-3.822-6-3.822zM0 13.274l6 3.822 6.001-3.822L6 9.452l-6 3.822zM18 9.452l-6 3.822 6 3.822 6-3.822-6-3.822zM6 18.371l6.001 3.822 6-3.822-6-3.822L6 18.371z" />
    </svg>
  )
}

// ─── Box ────────────────────────────────────────────────────────────────────
// Source: Simple Icons — #0061D5
function BoxIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
      <path fill="#0061D5" d="M.959 5.523c-.54 0-.959.42-.959.899v7.549a4.59 4.59 0 004.613 4.494 4.717 4.717 0 004.135-2.457c.779 1.438 2.337 2.457 4.074 2.457 2.577 0 4.674-2.037 4.674-4.613.06-2.457-2.037-4.495-4.613-4.495-1.738 0-3.295.959-4.074 2.397-.78-1.438-2.338-2.397-4.135-2.397-1.079 0-2.038.36-2.817.899V6.422a.92.92 0 00-.898-.899zM17.602 9.26a.95.95 0 00-.704.158c-.36.3-.479.899-.18 1.318l2.397 3.116-2.396 3.115c-.3.42-.24.96.18 1.26.419.3 1.016.298 1.316-.122l2.039-2.636 2.096 2.697c.3.36.899.419 1.318.12.36-.3.42-.84.121-1.259l-2.338-3.115 2.338-3.057c.3-.419.298-1.018-.121-1.318-.48-.3-1.019-.24-1.318.18l-2.096 2.576-2.04-2.695c-.149-.18-.373-.3-.612-.338zM4.613 11.154c1.558 0 2.817 1.26 2.817 2.758 0 1.558-1.259 2.756-2.817 2.756-1.558 0-2.816-1.198-2.816-2.756 0-1.498 1.258-2.758 2.816-2.758zm8.27 0c1.558 0 2.816 1.26 2.816 2.758-.06 1.558-1.318 2.756-2.816 2.756-1.558 0-2.817-1.198-2.817-2.756 0-1.498 1.259-2.758 2.817-2.758Z" />
    </svg>
  )
}

// ─── Network Share / SMB ────────────────────────────────────────────────────
// Globe-connected-to-server style icon — #6366F1 (Indigo)
function NetworkShareIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      {/* Globe */}
      <circle cx="12" cy="9" r="7" stroke="#6366F1" strokeWidth="1.8" fill="#EEF2FF" />
      <ellipse cx="12" cy="9" rx="3" ry="7" stroke="#6366F1" strokeWidth="1.2" fill="none" />
      <path d="M5 9h14" stroke="#6366F1" strokeWidth="1.2" />
      <path d="M6.5 5.5h11" stroke="#6366F1" strokeWidth="0.8" />
      <path d="M6.5 12.5h11" stroke="#6366F1" strokeWidth="0.8" />
      {/* Connection line */}
      <path d="M12 16v2.5" stroke="#6366F1" strokeWidth="1.8" strokeLinecap="round" />
      {/* Server base */}
      <rect x="6" y="19" width="12" height="3.5" rx="1" fill="#6366F1" />
      <circle cx="9" cy="20.75" r="0.6" fill="white" />
      <circle cx="11" cy="20.75" r="0.6" fill="white" />
      <rect x="14" y="20.25" width="2.5" height="1" rx="0.5" fill="white" />
    </svg>
  )
}

// ─── Alfresco ───────────────────────────────────────────────────────────────
// Source: Vector Logo Zone (vectorlogo.zone/logos/alfresco) — official pinwheel
function AlfrescoIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
      <path d="M46 5.795a12.24 12.24 0 0 0-1.507.092c2.662 5.25 1.798 11.83-2.6 16.22l-8.116 8.116H46c6.745 0 12.213-5.468 12.213-12.213S52.737 5.795 46 5.795z" fill="#f99f38" />
      <path d="M18 58.205a12.22 12.22 0 0 0 1.507-.092c-2.662-5.25-1.798-11.83 2.6-16.22l8.116-8.116H18c-6.745 0-12.213 5.468-12.213 12.213S11.265 58.203 18 58.203z" fill="#8bc037" />
      <path d="M5.795 18a12.22 12.22 0 0 0 .092 1.507c5.25-2.662 11.83-1.798 16.22 2.6l8.116 8.116V18c0-6.745-5.468-12.213-12.213-12.213S5.795 11.263 5.795 18z" fill="#0081c6" />
      <path d="M58.205 46a12.22 12.22 0 0 0-.092-1.507c-5.25 2.662-11.83 1.798-16.22-2.6l-8.116-8.116V46c0 6.745 5.468 12.213 12.213 12.213S58.203 52.735 58.203 46z" fill="#8bc037" />
      <path d="M23.364 3.577a11.1 11.1 0 0 0-1 1.13C27.958 6.54 32 11.802 32 18v11.477l8.636-8.636c4.77-4.77 4.77-12.503 0-17.272s-12.503-4.77-17.272 0z" fill="#0081c6" />
      <path d="M40.636 60.423a11.1 11.1 0 0 0 1-1.13C36.042 57.46 32 52.198 32 46V34.514l-8.636 8.636c-4.77 4.77-4.77 12.503 0 17.272s12.503 4.77 17.272 0z" fill="#8bc037" />
      <path d="M3.577 40.636a11.1 11.1 0 0 0 1.13 1C6.54 36.042 11.802 32 18 32h11.477l-8.636-8.636c-4.77-4.77-12.503-4.77-17.272 0s-4.77 12.503 0 17.272z" fill="#0081c6" />
      <path d="M60.423 23.364a12.33 12.33 0 0 0-1.131-1.001C57.46 27.958 52.198 32 46 32H34.514l8.636 8.636c4.77 4.77 12.503 4.77 17.272 0s4.77-12.503 0-17.272z" fill="#8bc037" />
      <path d="M42.664 6.254a12.22 12.22 0 0 0-8.887 11.754v9.7l6.858-6.86a12.22 12.22 0 0 0 2.028-14.595zm-36.4 15.08a12.22 12.22 0 0 0 11.754 8.887h9.7l-6.86-6.858a12.22 12.22 0 0 0-14.595-2.028z" fill="#0965ad" />
      <path d="M51.787 19.787c-3.126 0-6.25 1.192-8.636 3.577l-6.86 6.858h9.7a12.22 12.22 0 0 0 11.754-8.887 12.21 12.21 0 0 0-5.96-1.55z" fill="#ffdf4f" />
      <path d="M19.786 12.213c0 3.126 1.192 6.25 3.577 8.636l6.858 6.86v-9.7a12.22 12.22 0 0 0-8.887-11.754 12.21 12.21 0 0 0-1.55 5.96z" fill="#0965ad" />
      <path d="M44.213 51.787c0-3.126-1.192-6.25-3.577-8.636l-6.858-6.86v9.7a12.22 12.22 0 0 0 8.887 11.754 12.21 12.21 0 0 0 1.55-5.96zm-32-7.573c3.126 0 6.25-1.192 8.636-3.577l6.86-6.858h-9.7a12.22 12.22 0 0 0-11.754 8.887 12.21 12.21 0 0 0 5.96 1.55z" fill="#48a64a" />
    </svg>
  )
}

// ─── Database (Generic SQL) ─────────────────────────────────────────────────
// Cylinder database icon with gradient fills — #8B5CF6 (Violet)
function DatabaseIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="db_grad" x1="12" y1="2" x2="12" y2="22" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#A78BFA" />
          <stop offset="1" stopColor="#7C3AED" />
        </linearGradient>
      </defs>
      {/* Body */}
      <path d="M4 6v12c0 1.66 3.58 3 8 3s8-1.34 8-3V6" fill="url(#db_grad)" />
      {/* Top ellipse */}
      <ellipse cx="12" cy="6" rx="8" ry="3" fill="#C4B5FD" />
      {/* Middle ring */}
      <path d="M4 12c0 1.66 3.58 3 8 3s8-1.34 8-3" stroke="white" strokeWidth="0.8" strokeOpacity="0.5" fill="none" />
      {/* Lower ring */}
      <path d="M4 17c0 1.66 3.58 3 8 3s8-1.34 8-3" stroke="white" strokeWidth="0.8" strokeOpacity="0.3" fill="none" />
      {/* Highlight */}
      <path d="M6 6.5c0 .6 2.7 1.2 6 1.2s6-.6 6-1.2" stroke="white" strokeWidth="0.6" strokeOpacity="0.6" fill="none" />
    </svg>
  )
}

// ─── Registry ───────────────────────────────────────────────────────────────

export const connectorIconComponents: Record<ConnectorType, React.FC<IconProps>> = {
  onedrive: OneDriveIcon,
  google_drive: GoogleDriveIcon,
  dropbox: DropboxIcon,
  box: BoxIcon,
  network_share: NetworkShareIcon,
  alfresco: AlfrescoIcon,
  database: DatabaseIcon,
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
