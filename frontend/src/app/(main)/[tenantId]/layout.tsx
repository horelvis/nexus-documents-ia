import { AppSidebar } from "@/components/layout/app-sidebar"
import { SiteHeader } from "@/components/layout/site-header"
import { AuthGuard } from "@/components/auth/auth-guard"
import { UploadProvider } from "@/contexts/upload-context"
import { NotificationsProvider } from "@/contexts/notifications-context"
import { GlobalUploadDialog } from "@/components/dashboard/global-upload-dialog"
import { NavigationProgress } from "@/components/layout/navigation-progress"
import {
  SidebarInset,
  SidebarProvider,
} from "@/components/ui/sidebar"

export default function TenantLayout({
  children,
  params,
}: {
  children: React.ReactNode
  params: { tenantId: string }
}) {
  return (
    <AuthGuard>
      <NotificationsProvider>
        <UploadProvider>
          <SidebarProvider
            style={
              {
                "--sidebar-width": "calc(var(--spacing) * 72)",
                "--header-height": "calc(var(--spacing) * 12)",
              } as React.CSSProperties
            }
          >
            <AppSidebar variant="inset" tenantId={params.tenantId} />
            <SidebarInset>
              <NavigationProgress />
              <SiteHeader tenantId={params.tenantId} />
              <div className="flex flex-1 flex-col">
                <div className="@container/main flex flex-1 flex-col gap-2">
                  {children}
                </div>
              </div>
            </SidebarInset>
            
            {/* Global Upload Dialog */}
            <GlobalUploadDialog />
          </SidebarProvider>
        </UploadProvider>
      </NotificationsProvider>
    </AuthGuard>
  )
}