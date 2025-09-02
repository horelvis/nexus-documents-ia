import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { ClerkProvider } from '@clerk/nextjs'
import { ThemeProvider } from "@/components/providers/theme-provider";
import { PageLoaderProvider } from "@/components/providers/page-loader";
import { TopLoader } from "@/components/providers/top-loader";
import { Toaster } from "@/components/ui/toaster";
import { AppProviders } from "@/components/providers/app-providers";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Nexus - Gestión Documental con IA",
  description: "Plataforma avanzada de gestión documental potenciada por inteligencia artificial. Organiza, busca y analiza tus documentos de manera inteligente.",
  keywords: ["gestión documental", "inteligencia artificial", "búsqueda semántica", "documentos", "IA"],
  authors: [{ name: "Nexus Team" }],
  creator: "Nexus",
  openGraph: {
    title: "Nexus - Gestión Documental con IA",
    description: "Transforma tu gestión documental con inteligencia artificial",
    type: "website",
    locale: "es_ES",
  },
  twitter: {
    card: "summary_large_image",
    title: "Nexus - Gestión Documental con IA",
    description: "Transforma tu gestión documental con inteligencia artificial",
  },
  robots: {
    index: true,
    follow: true,
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <ClerkProvider
      publishableKey={process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY!}
      signInFallbackRedirectUrl="/dashboard"
      signUpFallbackRedirectUrl="/dashboard"
      afterSignOutUrl="/"
    >
      <html lang="en" suppressHydrationWarning>
        <body
          className={`${inter.variable} antialiased`}
        >
           <ThemeProvider
            attribute="class"
            defaultTheme="dark"
            enableSystem
            storageKey="nexus-theme"
          >
            <AppProviders>
              <PageLoaderProvider>
                <TopLoader />
                {children}
                <Toaster />
              </PageLoaderProvider>
            </AppProviders>
          </ThemeProvider>
        </body>
        
      </html>
    </ClerkProvider>
  );
}
