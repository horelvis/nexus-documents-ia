import { AuthGuard, ProfileVerificationGuard } from "@/components/auth"
import { LayoutSwitcher } from "@/components/layout/layout-switcher"
import { ChatUIProvider } from "@/contexts/chat-ui-context"
import { DocumentEventsProvider } from "@/contexts/document-events-context"
import { NotificationsProvider } from "@/contexts/notifications-context"
import { AnalysisQueueProvider } from "@/contexts/analysis-queue-context"

/**
 * Tenant Layout
 *
 * Root layout for all tenant-scoped pages. Provides:
 * - Authentication guards (Clerk or SSO depending on deployment mode)
 * - Context providers for app-wide state
 * - Layout switching based on EMMA_FULLSCREEN_MODE feature flag
 *
 * In on-premise mode (default):
 *   → EmmaFullscreenLayout with minimal header and chat-centric UI
 *
 * In SaaS mode:
 *   → Traditional sidebar layout with full navigation
 */
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
                <LayoutSwitcher tenantId={tenantId}>
                  {children}
                </LayoutSwitcher>
              </AnalysisQueueProvider>
            </DocumentEventsProvider>
          </ChatUIProvider>
        </NotificationsProvider>
      </ProfileVerificationGuard>
    </AuthGuard>
  )
}
