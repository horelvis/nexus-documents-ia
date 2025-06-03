import { ClerkProvider } from '@clerk/nextjs';
import { SITE_CONFIG } from "@/config";
import { cn } from "@/lib/utils";
import "@/styles/globals.css";
import { Inter } from "next/font/google";
import { Toaster } from "sonner";
import { OnboardingProvider } from "@/contexts/onboarding-context";
import { ApiAuthProvider } from "@/components/providers/api-auth-provider";

const font = Inter({ subsets: ["latin"] });

export const metadata = SITE_CONFIG;

export default function RootLayout({
    children,
}: Readonly<{
    children: React.ReactNode;
}>) {
    return (
        <ClerkProvider>
            <html lang="en" suppressHydrationWarning>
                <body
                    className={cn(
                        "antialiased bg-background text-foreground transition min-h-screen overflow-x-hidden !scrollbar-hide",
                        font.className
                    )}
                >
                    <ApiAuthProvider>
                        <OnboardingProvider>
                            {children}
                            <Toaster position="top-right" richColors />
                        </OnboardingProvider>
                    </ApiAuthProvider>
                </body>
            </html>
        </ClerkProvider>
    );
};