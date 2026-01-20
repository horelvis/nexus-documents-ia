"use client"

import { createContext, useContext, useState, useEffect, ReactNode, useCallback } from 'react'
import {
  SitePortalService, TenantSiteInfo, SiteGuest, PortalContentResponse
} from '@/lib/services/site-guest.service'

interface SiteGuestContextType {
  // State
  tenant: TenantSiteInfo | null
  guest: SiteGuest | null
  sessionToken: string | null
  isLoading: boolean
  error: string | null

  // Actions
  setTenant: (tenant: TenantSiteInfo | null) => void
  login: (token: string, guest: SiteGuest) => void
  logout: () => Promise<void>
  refreshGuest: () => Promise<void>

  // Portal Service
  portalService: SitePortalService
}

const SiteGuestContext = createContext<SiteGuestContextType | undefined>(undefined)

const STORAGE_KEY = 'site_guest_session'

interface StoredSession {
  token: string
  tenant_slug: string
  expires_at: string
}

export function SiteGuestProvider({ children }: { children: ReactNode }) {
  const [tenant, setTenant] = useState<TenantSiteInfo | null>(null)
  const [guest, setGuest] = useState<SiteGuest | null>(null)
  const [sessionToken, setSessionToken] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [portalService] = useState(() => new SitePortalService())

  // Load session from localStorage on mount
  useEffect(() => {
    const loadSession = async () => {
      setIsLoading(true)

      try {
        const stored = localStorage.getItem(STORAGE_KEY)
        if (!stored) {
          setIsLoading(false)
          return
        }

        const session: StoredSession = JSON.parse(stored)

        // Check if session is expired
        if (new Date(session.expires_at) < new Date()) {
          localStorage.removeItem(STORAGE_KEY)
          setIsLoading(false)
          return
        }

        // Set token and try to refresh guest info
        portalService.setSessionToken(session.token)
        setSessionToken(session.token)

        const response = await portalService.getMe()
        if (response.data) {
          setGuest(response.data.guest)

          // Also load tenant info
          const tenantResponse = await portalService.getTenantBySlug(session.tenant_slug)
          if (tenantResponse.data) {
            setTenant(tenantResponse.data)
          }
        } else {
          // Invalid session, clear it
          localStorage.removeItem(STORAGE_KEY)
          portalService.setSessionToken(null)
          setSessionToken(null)
        }
      } catch (err) {
        console.error('Error loading session:', err)
        localStorage.removeItem(STORAGE_KEY)
      } finally {
        setIsLoading(false)
      }
    }

    loadSession()
  }, [portalService])

  const login = useCallback((token: string, newGuest: SiteGuest) => {
    setSessionToken(token)
    setGuest(newGuest)
    portalService.setSessionToken(token)

    // Store session
    if (tenant) {
      const session: StoredSession = {
        token,
        tenant_slug: tenant.slug,
        expires_at: new Date(Date.now() + 8 * 60 * 60 * 1000).toISOString() // 8 hours
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(session))
    }
  }, [portalService, tenant])

  const logout = useCallback(async () => {
    try {
      await portalService.logout()
    } catch (err) {
      console.error('Logout error:', err)
    } finally {
      setSessionToken(null)
      setGuest(null)
      portalService.setSessionToken(null)
      localStorage.removeItem(STORAGE_KEY)
    }
  }, [portalService])

  const refreshGuest = useCallback(async () => {
    if (!sessionToken) return

    try {
      const response = await portalService.getMe()
      if (response.data) {
        setGuest(response.data.guest)
      } else {
        // Session invalid
        await logout()
      }
    } catch (err) {
      console.error('Error refreshing guest:', err)
    }
  }, [sessionToken, portalService, logout])

  const value: SiteGuestContextType = {
    tenant,
    guest,
    sessionToken,
    isLoading,
    error,
    setTenant,
    login,
    logout,
    refreshGuest,
    portalService
  }

  return (
    <SiteGuestContext.Provider value={value}>
      {children}
    </SiteGuestContext.Provider>
  )
}

export function useSiteGuest() {
  const context = useContext(SiteGuestContext)
  if (context === undefined) {
    throw new Error('useSiteGuest must be used within a SiteGuestProvider')
  }
  return context
}
