"use client"

import { SiteGuestProvider } from '@/contexts/site-guest-context'

export default function PortalLayout({
  children
}: {
  children: React.ReactNode
}) {
  return (
    <SiteGuestProvider>
      <div className="min-h-screen bg-gray-50">
        {children}
      </div>
    </SiteGuestProvider>
  )
}
