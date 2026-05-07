'use client'

import Link from 'next/link'
import { SidebarProvider, SidebarInset } from '@/components/ui'
import { AppSidebar } from '@/components/layout/app-sidebar'
import { PageHeader } from '@/components/layout/page-header'
import { AgentBuilderForm } from '@/components/agents/agent-builder-form'

export default function NewAgentPage() {
  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <PageHeader>
          <nav className="flex items-center gap-2 text-sm text-muted-foreground">
            <Link href="/" className="hover:text-foreground transition-colors">Inicio</Link>
            <span>/</span>
            <Link href="/admin/dashboard" className="hover:text-foreground transition-colors">Administración</Link>
            <span>/</span>
            <Link href="/admin/agents" className="hover:text-foreground transition-colors">Agentes</Link>
            <span>/</span>
            <span className="text-foreground font-medium">Nuevo</span>
          </nav>
        </PageHeader>

        <main className="flex-1 overflow-auto p-4 md:p-6">
          <div className="max-w-3xl mx-auto space-y-6">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">Nuevo agente</h1>
              <p className="text-sm text-muted-foreground">
                Define identidad, persona y scope. Tras guardar podrás activarlo desde el catálogo.
              </p>
            </div>
            <AgentBuilderForm mode="create" />
          </div>
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}
