"use client"

import { SiteGuestProvider } from '@/contexts/site-guest-context'

export default function PortalLayout({
  children
}: {
  children: React.ReactNode
}) {
  return (
    <SiteGuestProvider>
      <div className="min-h-screen bg-background dark">
        {children}
      </div>
    </SiteGuestProvider>
  )
}
