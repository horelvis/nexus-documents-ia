import type { Metadata } from "next"
import { Suspense } from "react"
import { Inter } from "next/font/google"
import { ThemeProvider } from "next-themes"
import { Toaster } from "@nexus/shared/ui"
import { AuthProvider } from "@/contexts/auth-context"
import { VerifiedGenerationProvider } from "@/contexts/verified-generation-context"
import "./globals.css"

const inter = Inter({ subsets: ["latin"] })

export const metadata: Metadata = {
  title: "NouxCube AI",
  description: "Plataforma de inteligencia empresarial centralizada",
  icons: {
    icon: "/favicon.ico",
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="es" suppressHydrationWarning>
      <body className={inter.className}>
        <ThemeProvider
          attribute="class"
          defaultTheme="dark"
          enableSystem
          disableTransitionOnChange
        >
          <Suspense fallback={null}>
            <AuthProvider>
              <VerifiedGenerationProvider>
                {children}
              </VerifiedGenerationProvider>
            </AuthProvider>
          </Suspense>
          <Toaster />
        </ThemeProvider>
      </body>
    </html>
  )
}
