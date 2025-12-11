import { AppSidebar } from "@/components/layout/app-sidebar"
import { SiteHeader } from "@/components/layout/site-header"
import { AuthGuard, ProfileVerificationGuard } from "@/components/auth"
import { GlobalUploadDialog } from "@/components/dashboard/global-upload-dialog"
import { NavigationProgress } from "@/components/layout/navigation-progress"
import { VirtualAssistant } from "@/components/virtual-assistant/virtual-assistant"
import { TourGuide } from "@/components/tour/TourGuide"
import { ChatUIProvider } from "@/contexts/chat-ui-context"
import { DocumentEventsProvider } from "@/contexts/document-events-context"
import { NotificationsProvider } from "@/contexts/notifications-context"
import { AnalysisQueueProvider } from "@/contexts/analysis-queue-context"
import { AnalysisQueueWidget } from "@/components/analysis/queue-widget"
import {
  SidebarInset,
  SidebarProvider,
} from "@/components/ui/sidebar"

export default async function TenantLayout({
  children,
  params,
}: {
  children: React.ReactNode
  params: Promise<{ tenantId: string }>
}) {
  const { tenantId } = await params
  return (
    <AuthGuard>
      <ProfileVerificationGuard>
        <NotificationsProvider>
          <ChatUIProvider>
            <DocumentEventsProvider>
              <AnalysisQueueProvider>
              <SidebarProvider
                style={
                  {
                    "--sidebar-width": "calc(var(--spacing) * 72)",
                    "--header-height": "calc(var(--spacing) * 12)",
                  } as React.CSSProperties
                }
              >
                <TourGuide>
                  <AppSidebar variant="inset" tenantId={tenantId} />
                  <SidebarInset>
                    <NavigationProgress />
                    <SiteHeader tenantId={tenantId} />
                    <div className="flex flex-1 flex-col min-h-0">
                      <div className="@container/main flex flex-1 flex-col min-h-0">
                        {children}
                      </div>
                    </div>
                  </SidebarInset>
                  
                  {/* Global Upload Dialog */}
                  <GlobalUploadDialog />

                  {/* Virtual Assistant */}
                  <VirtualAssistant />

                  {/* Analysis Queue Widget */}
                  <AnalysisQueueWidget />
                </TourGuide>
              </SidebarProvider>
              </AnalysisQueueProvider>
            </DocumentEventsProvider>
          </ChatUIProvider>
        </NotificationsProvider>
      </ProfileVerificationGuard>
    </AuthGuard>
  )
}
