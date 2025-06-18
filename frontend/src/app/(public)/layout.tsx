export default function PublicLayout({
  children,
}: {
  children: React.ReactNode
}) {
  // This layout doesn't include ClerkProvider or any authentication
  // It's for public pages that don't require authentication
  return (
    <>
      {children}
    </>
  )
}