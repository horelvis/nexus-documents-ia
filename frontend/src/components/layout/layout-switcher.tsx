"use client"

/**
 * Layout Switcher Component
 *
 * Conditionally renders either the traditional sidebar layout or
 * Emma fullscreen layout based on the EMMA_FULLSCREEN_MODE feature flag.
 *
 * This is a client component because it needs to check feature flags
 * which may require API calls or hook usage.
 */

import { ReactNode, useState, useEffect } from "react"
import { AppSidebar } from "@/components/layout/app-sidebar"
import { SiteHeader } from "@/components/layout/site-header"
import { EmmaFullscreenLayout } from "@/components/layout/emma-fullscreen-layout"
import { GlobalUploadDialog } from "@/components/dashboard/global-upload-dialog"
import { NavigationProgress } from "@/components/layout/navigation-progress"
import { VirtualAssistant } from "@/components/virtual-assistant/virtual-assistant"
import { TourGuide } from "@/components/tour/TourGuide"
import { AnalysisQueueWidget } from "@/components/analysis/queue-widget"
import {
  SidebarInset,
  SidebarProvider,
} from "@/components/ui/sidebar"
import { useEmmaFullscreenMode, useFeature, Feature } from "@/lib/features"
import { Loader2 } from "lucide-react"

interface LayoutSwitcherProps {
  children: ReactNode
}

/**
 * LayoutSwitcher decides between sidebar and fullscreen modes.
 *
 * In Emma fullscreen mode (default for on-premise):
 * - Minimal header with logo and user menu
 * - Emma chat occupies full screen
 * - No sidebar navigation
 *
 * In traditional mode (SaaS):
 * - Full sidebar with navigation
 * - Standard header with breadcrumbs
 * - Document library and all features visible
 */
export function LayoutSwitcher({ children }: LayoutSwitcherProps) {
  const isEmmaFullscreen = useEmmaFullscreenMode()
  const showDocumentLibrary = useFeature(Feature.DOCUMENT_LIBRARY_UI)
  const [isHydrated, setIsHydrated] = useState(false)

  // Prevent hydration mismatch by waiting for client-side render
  useEffect(() => {
    setIsHydrated(true)
  }, [])

  // Show loading state during hydration to prevent flash
  if (!isHydrated) {
    return (
      <div className="flex items-center justify-center h-screen bg-background">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  // Emma fullscreen mode: minimal UI, chat-centric
  if (isEmmaFullscreen) {
    return (
      <EmmaFullscreenLayout>
        {children}
      </EmmaFullscreenLayout>
    )
  }

  // Traditional sidebar mode: full navigation
  return (
    <SidebarProvider
      style={
        {
          "--sidebar-width": "calc(var(--spacing) * 72)",
          "--header-height": "calc(var(--spacing) * 12)",
        } as React.CSSProperties
      }
    >
      <TourGuide>
        <AppSidebar variant="inset" />
        <SidebarInset>
          <NavigationProgress />
          <SiteHeader />
          <div className="flex flex-1 flex-col min-h-0">
            <div className="@container/main flex flex-1 flex-col min-h-0">
              {children}
            </div>
          </div>
        </SidebarInset>

        {/* Global Upload Dialog - only in sidebar mode */}
        <GlobalUploadDialog />

        {/* Virtual Assistant */}
        <VirtualAssistant />

        {/* Analysis Queue Widget */}
        <AnalysisQueueWidget />
      </TourGuide>
    </SidebarProvider>
  )
}
