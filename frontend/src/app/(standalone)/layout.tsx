import { NotificationsProvider } from '@/contexts/notifications-context'

export default function StandaloneLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <NotificationsProvider>
      <div className="min-h-screen bg-background">
        {children}
      </div>
    </NotificationsProvider>
  )
}