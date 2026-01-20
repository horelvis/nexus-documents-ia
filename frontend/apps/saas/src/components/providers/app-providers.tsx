"use client"

import { ReactNode } from 'react'
import { UserProvider } from '@/contexts/user-context'
import { AppStateProvider } from '@/contexts/app-state-context'
import { UploadProvider } from '@/contexts/upload-context'
import { LanguageProvider } from '@/contexts/language-context'
import { ErrorBoundary } from '@/components/errors/error-boundary'

interface AppProvidersProps {
  children: ReactNode
}

/**
 * Main application providers wrapper
 * Combines all global context providers in the correct order
 */
export function AppProviders({ children }: AppProvidersProps) {
  return (
    <ErrorBoundary>
      <LanguageProvider> {/* Handles multi-language support - MUST BE EARLY */}
        <AppStateProvider> {/* Handles connection status and notifications */}
          <UserProvider> {/* Handles user authentication and onboarding */}
            <UploadProvider> {/* Handles file upload dialog state */}
              {children}
            </UploadProvider>
          </UserProvider>
        </AppStateProvider>
      </LanguageProvider>
    </ErrorBoundary>
  )
}