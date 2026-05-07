'use client'

/**
 * Agents Gallery — read-only catalog of admin-curated specialist agents.
 *
 * Open to every authenticated user. Each card shows the agent's identity,
 * scope hints, usage and a "Probar" button. Admins additionally see an
 * "Editar" button on each card and a "+ Crear agente" placeholder.
 *
 * Layout follows the project's canonical AppSidebar pattern. Visual
 * inspiration from the original mockup (modulo features that don't
 * apply to the admin-curated model: no Privados/Compartidos tabs).
 */

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import {
  IconRobot,
  IconRefresh,
  IconSearch,
  IconPlus,
  IconDots,
  IconLock,
} from '@tabler/icons-react'
import {
  SidebarProvider,
  SidebarInset,
  Button,
  Badge,
  Card,
  CardContent,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui'
import { AppSidebar } from '@/components/layout/app-sidebar'
import { PageHeader } from '@/components/layout/page-header'
import { useAuth } from '@/contexts/auth-context'
import { agentsService } from '@/lib/services/agents.service'
import type { Agent } from '@/lib/types/agent'

const COLOR_BG: Record<string, string> = {
  blue: 'bg-blue-500/15 text-blue-400',
  green: 'bg-emerald-500/15 text-emerald-400',
  orange: 'bg-orange-500/15 text-orange-400',
  purple: 'bg-purple-500/15 text-purple-400',
  red: 'bg-red-500/15 text-red-400',
  pink: 'bg-pink-500/15 text-pink-400',
  indigo: 'bg-indigo-500/15 text-indigo-400',
}

export default function AgentsGalleryPage() {
  const { isAdmin } = useAuth()
  const router = useRouter()

  const [agents, setAgents] = useState<Agent[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [orderBy, setOrderBy] = useState<'name' | 'usage_count'>('usage_count')
  const [search, setSearch] = useState('')

  async function loadAgents() {
    setIsLoading(true)
    setError(null)
    const r = await agentsService.list({ active: true, order_by: orderBy })
    if (r.error || !r.data) setError(r.error || 'No data')
    else setAgents(r.data)
    setIsLoading(false)
  }

  useEffect(() => {
    void loadAgents()
  }, [orderBy])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return agents
    return agents.filter(
      (a) =>
        a.name.toLowerCase().includes(q) ||
        a.slug.includes(q) ||
        (a.description ?? '').toLowerCase().includes(q),
    )
  }, [agents, search])

  function openInChat(agent: Agent) {
    router.push(`/?prefill=${encodeURIComponent('@' + agent.slug + ' ')}`)
  }

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <PageHeader>
          <nav className="flex items-center gap-2 text-sm text-muted-foreground">
            <Link href="/" className="hover:text-foreground transition-colors">Inicio</Link>
            <span>/</span>
            <span className="text-foreground font-medium">Mis Agentes</span>
          </nav>
        </PageHeader>

        <main className="flex-1 overflow-auto p-4 md:p-6">
          <div className="space-y-6 max-w-7xl mx-auto">
            {/* Title row */}
            <div className="flex items-center justify-between flex-wrap gap-3">
              <div>
                <h1 className="text-2xl font-semibold tracking-tight">Mis Agentes</h1>
                <p className="text-sm text-muted-foreground">
                  Especialistas curados. Invoca cualquiera con <code className="px-1 py-0.5 bg-muted rounded text-xs">@&lt;slug&gt;</code> en el chat.
                </p>
              </div>
              {isAdmin && (
                <Button asChild>
                  <Link href="/admin/agents/new">
                    <IconPlus className="h-4 w-4 mr-1" />
                    Crear agente
                  </Link>
                </Button>
              )}
            </div>

            {/* Toolbar: search + sort + refresh */}
            <div className="flex items-center gap-2 flex-wrap">
              <div className="relative flex-1 min-w-[16rem] max-w-md">
                <IconSearch className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Buscar agentes…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="pl-9"
                />
              </div>
              <Select value={orderBy} onValueChange={(v) => setOrderBy(v as 'name' | 'usage_count')}>
                <SelectTrigger className="w-44">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="usage_count">Más usados</SelectItem>
                  <SelectItem value="name">Por nombre</SelectItem>
                </SelectContent>
              </Select>
              <Button variant="outline" size="icon" onClick={loadAgents} title="Recargar">
                <IconRefresh className="h-4 w-4" />
              </Button>
            </div>

            {error && (
              <div className="text-sm text-red-700 bg-red-50 border border-red-200 px-3 py-2 rounded">
                {error}
              </div>
            )}

            {/* Grid */}
            {isLoading ? (
              <p className="text-muted-foreground">Cargando…</p>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {filtered.map((agent) => (
                  <AgentCard
                    key={agent.id}
                    agent={agent}
                    isAdmin={!!isAdmin}
                    onOpen={() => openInChat(agent)}
                  />
                ))}

                {/* "+ Crear agente desde cero" placeholder for admins */}
                {isAdmin && !search && (
                  <Link
                    href="/admin/agents/new"
                    className="rounded-lg border border-dashed border-border hover:border-primary hover:bg-muted/50 transition-colors flex flex-col items-center justify-center min-h-[14rem] text-muted-foreground hover:text-foreground"
                  >
                    <div className="rounded-full bg-muted p-4 mb-3">
                      <IconPlus className="h-6 w-6" />
                    </div>
                    <p className="font-medium">Crear agente</p>
                    <p className="text-xs">desde cero</p>
                  </Link>
                )}

                {filtered.length === 0 && !isAdmin && (
                  <Card className="md:col-span-2 lg:col-span-3">
                    <CardContent className="p-8 text-center text-muted-foreground">
                      {search ? 'Sin resultados.' : 'No hay agentes activos en este momento.'}
                    </CardContent>
                  </Card>
                )}
              </div>
            )}
          </div>
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}

interface AgentCardProps {
  agent: Agent
  isAdmin: boolean
  onOpen: () => void
}

function AgentCard({ agent, isAdmin, onOpen }: AgentCardProps) {
  const colorCls = COLOR_BG[agent.color] ?? COLOR_BG.blue
  const tags = (agent.scope?.semantic_types ?? []).slice(0, 3)
  const extraTags = (agent.scope?.semantic_types?.length ?? 0) - tags.length

  return (
    <Card className="flex flex-col">
      <CardContent className="p-4 space-y-3 flex-1 flex flex-col">
        {/* Header: avatar + name + kebab */}
        <div className="flex items-start gap-3">
          <div className={`p-2.5 rounded-lg shrink-0 ${colorCls}`}>
            <IconRobot className="h-5 w-5" />
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="font-semibold leading-tight truncate">{agent.name}</h3>
            <p className="text-xs text-muted-foreground font-mono mt-0.5">@{agent.slug}</p>
          </div>
          {agent.is_seed && (
            <Badge variant="outline" className="text-[10px] uppercase tracking-wide">SEED</Badge>
          )}
          <button
            type="button"
            className="text-muted-foreground hover:text-foreground p-1 -m-1"
            aria-label="Opciones"
            onClick={(e) => e.preventDefault()}
          >
            <IconDots className="h-4 w-4" />
          </button>
        </div>

        {/* Description */}
        <p className="text-sm text-muted-foreground line-clamp-2 min-h-[2.6em]">
          {agent.description ?? '—'}
        </p>

        {/* Scope tags (semantic_types) */}
        {tags.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {tags.map((t) => (
              <Badge key={t} variant="secondary" className="text-xs font-mono font-normal">
                {t}
              </Badge>
            ))}
            {extraTags > 0 && (
              <Badge variant="secondary" className="text-xs font-normal">+{extraTags}</Badge>
            )}
          </div>
        )}

        {/* Footer info */}
        <div className="flex items-center justify-between text-xs text-muted-foreground pt-1 mt-auto">
          <span className="flex items-center gap-1">
            <IconLock className="h-3 w-3" />
            {agent.is_seed ? 'Predefinido' : 'Disponible'}
          </span>
          <span>{agent.usage_count} usos</span>
        </div>

        {/* Actions */}
        <div className="grid grid-cols-2 gap-2">
          {isAdmin ? (
            <Button asChild variant="outline" size="sm">
              <Link href={`/admin/agents/${agent.id}/edit`}>Editar</Link>
            </Button>
          ) : (
            <Button variant="outline" size="sm" disabled className="cursor-default">
              Disponible
            </Button>
          )}
          <Button size="sm" onClick={onOpen}>
            Abrir
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
