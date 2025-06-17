import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { ClerkProvider } from '@clerk/nextjs'
import { ThemeProvider } from "@/components/providers/theme-provider";
import { UserProvider } from "@/contexts/user-context";
import { PageLoaderProvider } from "@/components/providers/page-loader";
import { TopLoader } from "@/components/providers/top-loader";
import { Toaster } from "@/components/ui/toaster";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
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
    <ClerkProvider>
      <html lang="en" suppressHydrationWarning>
        <body
          className={`${geistSans.variable} ${geistMono.variable} antialiased`}
        >
           <ThemeProvider
            attribute="class"
            defaultTheme="dark"
            enableSystem
            storageKey="nexus-theme"
          >
            <PageLoaderProvider>
              <TopLoader />
              <UserProvider>
                {children}
                <Toaster />
              </UserProvider>
            </PageLoaderProvider>
          </ThemeProvider>
        </body>
        
      </html>
    </ClerkProvider>
  );
}
