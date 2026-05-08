'use client'

/**
 * Admin — Agents catalog list.
 *
 * AdminGuard is applied by app/admin/layout.tsx; no need to wrap again.
 */

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { IconPlus, IconRefresh } from '@tabler/icons-react'
import {
  SidebarProvider,
  SidebarInset,
  Button,
  Badge,
  Table,
  TableHeader,
  TableBody,
  TableHead,
  TableRow,
  TableCell,
} from '@/components/ui'
import { AppSidebar } from '@/components/layout/app-sidebar'
import { PageHeader } from '@/components/layout/page-header'
import { agentsService } from '@/lib/services/agents.service'
import type { Agent } from '@/lib/types/agent'

export default function AgentsAdminPage() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  async function loadAgents() {
    setIsLoading(true)
    setError(null)
    const r = await agentsService.list()
    if (r.error || !r.data) setError(r.error || 'No data')
    else setAgents(r.data)
    setIsLoading(false)
  }

  useEffect(() => {
    void loadAgents()
  }, [])

  async function handleToggleActive(agent: Agent) {
    const r = await agentsService.update(agent.id, { is_active: !agent.is_active })
    if (r.error) {
      alert(`No se pudo cambiar estado: ${r.error}`)
      return
    }
    void loadAgents()
  }

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
            <span className="text-foreground font-medium">Agentes</span>
          </nav>
        </PageHeader>

        <main className="flex-1 overflow-auto p-4 md:p-6">
          <div className="space-y-6 max-w-6xl mx-auto">
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-2xl font-semibold tracking-tight">Catálogo de agentes</h1>
                <p className="text-sm text-muted-foreground">
                  Crea, edita y publica agentes especialistas para los usuarios.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Button variant="outline" size="icon" onClick={loadAgents} title="Recargar">
                  <IconRefresh className="h-4 w-4" />
                </Button>
                <Button asChild>
                  <Link href="/admin/agents/new">
                    <IconPlus className="h-4 w-4 mr-1" />
                    Nuevo agente
                  </Link>
                </Button>
              </div>
            </div>

            {error && (
              <div className="text-sm text-red-700 bg-red-50 border border-red-200 px-3 py-2 rounded">
                {error}
              </div>
            )}

            {isLoading ? (
              <p className="text-muted-foreground">Cargando…</p>
            ) : agents.length === 0 ? (
              <p className="text-muted-foreground">No hay agentes. Crea el primero.</p>
            ) : (
              <div className="border rounded-lg">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Nombre</TableHead>
                      <TableHead>Slug</TableHead>
                      <TableHead>Estado</TableHead>
                      <TableHead className="text-right">Uso</TableHead>
                      <TableHead>Tipo</TableHead>
                      <TableHead className="text-right"></TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {agents.map((a) => (
                      <TableRow key={a.id}>
                        <TableCell className="font-medium">{a.name}</TableCell>
                        <TableCell className="font-mono text-xs">@{a.slug}</TableCell>
                        <TableCell>
                          <button
                            type="button"
                            onClick={() => handleToggleActive(a)}
                            disabled={a.is_seed && a.is_active}
                            title={a.is_seed && a.is_active ? 'Un seed activo no puede desactivarse' : ''}
                          >
                            <Badge variant={a.is_active ? 'default' : 'secondary'}>
                              {a.is_active ? 'Activo' : 'Inactivo'}
                            </Badge>
                          </button>
                        </TableCell>
                        <TableCell className="text-right text-sm">{a.usage_count}</TableCell>
                        <TableCell className="text-xs">
                          {a.is_seed ? (
                            <Badge variant="outline" className="text-purple-700 border-purple-300">SEED</Badge>
                          ) : (
                            <span className="text-muted-foreground">normal</span>
                          )}
                        </TableCell>
                        <TableCell className="text-right">
                          <Button asChild variant="ghost" size="sm">
                            <Link href={`/admin/agents/${a.id}/edit`}>Editar</Link>
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </div>
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}
