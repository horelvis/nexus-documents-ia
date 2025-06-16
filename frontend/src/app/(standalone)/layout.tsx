import { NotificationsProvider } from '@/contexts/notifications-context'
import { UserProvider } from '@/contexts/user-context'

export default function StandaloneLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <UserProvider>
      <NotificationsProvider>
        <div className="min-h-screen bg-background">
          {children}
        </div>
      </NotificationsProvider>
    </UserProvider>
  )
}