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
          <div className="min-h-screen">
            {children}
          </div>
        </UploadProvider>
      </NotificationsProvider>
    </AuthGuard>
  )
}