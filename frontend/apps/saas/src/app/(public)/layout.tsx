import { LanguageProvider } from '@/contexts/language-context'

export default function PublicLayout({
  children,
}: {
  children: React.ReactNode
}) {
  // This layout doesn't include ClerkProvider or any authentication
  // It's for public pages that don't require authentication
  // But it includes LanguageProvider for i18n support
  return (
    <LanguageProvider>
      {children}
    </LanguageProvider>
  )
}