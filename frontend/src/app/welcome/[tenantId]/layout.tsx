import { AuthGuard } from "@/components/auth"
import { NotificationsProvider } from "@/contexts/notifications-context"
import { UploadProvider } from "@/contexts/upload-context"

export default function WelcomeLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <AuthGuard>
      <NotificationsProvider>
        <UploadProvider>
          <div className="h-screen overflow-y-auto">
            {children}
          </div>
        </UploadProvider>
      </NotificationsProvider>
    </AuthGuard>
  )
}