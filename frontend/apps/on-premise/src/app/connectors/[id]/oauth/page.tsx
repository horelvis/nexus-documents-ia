'use client'

import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import {
  IconBrain,
  IconChevronLeft,
  IconLoader2,
  IconPlug,
} from '@tabler/icons-react'
import {
  SidebarProvider,
  SidebarInset,
  SidebarTrigger,
} from '@nexus/shared/ui'
import { useAuth } from '@/contexts/auth-context'
import { AppSidebar } from '@/components/layout/app-sidebar'
import { GoogleDriveOAuthStep } from '@/components/connectors'
import { connectorService, Connector } from '@/lib/services/connector.service'

export default function OAuthReconnectPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const { isLoaded, isAuthenticated } = useAuth()

  const [connector, setConnector] = useState<Connector | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    if (isLoaded && !isAuthenticated) {
      router.push('/auth/sign-in')
    }
  }, [isLoaded, isAuthenticated, router])

  useEffect(() => {
    if (!isLoaded || !isAuthenticated || !id) return

    setIsLoading(true)
    const load = async () => {
      try {
        const result = await connectorService.getConnector(id)
        if (result.data) {
          setConnector(result.data)
        }
      } catch (err) {
        // ignore
      } finally {
        setIsLoading(false)
      }
    }
    load()
  }, [isLoaded, isAuthenticated, id])

  const handleComplete = () => {
    router.push('/connectors')
  }

  if (!isLoaded || !isAuthenticated) {
    return (
      <div className="flex items-center justify-center h-screen bg-background">
        <IconLoader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  return (
    <SidebarProvider>
      <AppSidebar variant="inset" />

      <SidebarInset>
        <header className="h-14 border-b flex items-center gap-2 px-4 shrink-0">
          <SidebarTrigger className="-ml-1" />
          <div className="h-4 w-px bg-border" />
          <Link href="/connectors" className="flex items-center gap-2 text-muted-foreground hover:text-foreground">
            <IconChevronLeft className="h-4 w-4" />
            <IconPlug className="h-4 w-4 text-primary" />
            <span className="font-semibold text-foreground">Conectores</span>
          </Link>
          <div className="h-4 w-px bg-border" />
          <span className="text-muted-foreground">Reconectar</span>
        </header>

        <main className="flex-1 overflow-auto p-6">
          <div className="max-w-xl mx-auto">
            {isLoading ? (
              <div className="flex items-center justify-center py-12">
                <IconLoader2 className="h-8 w-8 animate-spin text-primary" />
              </div>
            ) : connector ? (
              <GoogleDriveOAuthStep
                connectorId={connector.id}
                connectorName={connector.name}
                onComplete={handleComplete}
              />
            ) : (
              <p className="text-center text-muted-foreground">Conector no encontrado</p>
            )}
          </div>
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}
