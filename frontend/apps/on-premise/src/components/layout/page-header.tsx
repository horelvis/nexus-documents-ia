'use client'

/**
 * PageHeader — Shared top header bar for all pages.
 *
 * Provides consistent layout: SidebarTrigger + breadcrumb (children) on the left,
 * NotificationBell on the right. Used inside SidebarInset on every page.
 */

import { SidebarTrigger } from '@nexus/shared/ui'
import { NotificationBell } from '@/components/notifications'

interface PageHeaderProps {
  children?: React.ReactNode
}

export function PageHeader({ children }: PageHeaderProps) {
  return (
    <header className="h-14 border-b flex items-center justify-between px-4 shrink-0">
      <div className="flex items-center gap-2">
        <SidebarTrigger className="-ml-1" />
        <div className="h-4 w-px bg-border" />
        {children}
      </div>

      <div className="flex items-center gap-2">
        <NotificationBell />
      </div>
    </header>
  )
}
