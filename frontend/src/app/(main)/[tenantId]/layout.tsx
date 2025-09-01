import { AppSidebar } from "@/components/layout/app-sidebar"
import { SiteHeader } from "@/components/layout/site-header"
import { AuthGuard, ProfileVerificationGuard } from "@/components/auth"
import { GlobalUploadDialog } from "@/components/dashboard/global-upload-dialog"
import { NavigationProgress } from "@/components/layout/navigation-progress"
import { VirtualAssistant } from "@/components/virtual-assistant/virtual-assistant"
import { ChatUIProvider } from "@/contexts/chat-ui-context"
import { NotificationsProvider } from "@/contexts/notifications-context"
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
            <SidebarProvider
              style={
                {
                  "--sidebar-width": "calc(var(--spacing) * 72)",
                  "--header-height": "calc(var(--spacing) * 12)",
                } as React.CSSProperties
              }
            >
            <AppSidebar variant="inset" tenantId={tenantId} />
            <SidebarInset>
              <NavigationProgress />
              <SiteHeader tenantId={tenantId} />
              <div className="flex flex-1 flex-col">
                <div className="@container/main flex flex-1 flex-col gap-2">
                  {children}
                </div>
              </div>
            </SidebarInset>
            
            {/* Global Upload Dialog */}
            <GlobalUploadDialog />
            
            {/* Virtual Assistant */}
            <VirtualAssistant />
            </SidebarProvider>
          </ChatUIProvider>
        </NotificationsProvider>
      </ProfileVerificationGuard>
    </AuthGuard>
  )
}