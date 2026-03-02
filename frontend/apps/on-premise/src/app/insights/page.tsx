'use client'

/**
 * Proactive Insights Page
 *
 * Displays heartbeat-generated insights (contract expirations, compliance alerts,
 * risk alerts, etc.) in a card layout with urgency color-coding and actions.
 * Users can dismiss insights or mark them as acted upon.
 */

import { useState, useEffect } from 'react'
import Link from 'next/link'
import {
  IconBell,
  IconLoader2,
  IconRefresh,
  IconFileText,
  IconShieldCheck,
  IconAlertTriangle,
  IconBug,
  IconChecklist,
  IconCalendarDue,
  IconFileDescription,
  IconChartBar,
  IconX,
  IconCheck,
  IconInbox,
  IconFilter,
} from '@tabler/icons-react'
import {
  SidebarProvider,
  SidebarInset,
  Button,
  Badge,
  Card,
  CardContent,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@nexus/shared/ui'
import { useAuth } from '@/contexts/auth-context'
import { AppSidebar } from '@/components/layout/app-sidebar'
import { PageHeader } from '@/components/layout/page-header'
import {
  heartbeatService,
  ProactiveInsight,
  InsightUrgency,
  InsightStatus,
} from '@/lib/services/heartbeat.service'

// ─── Urgency Configuration ────────────────────────────────────────────────────

const urgencyConfig: Record<InsightUrgency, {
  label: string
  variant: 'destructive' | 'default' | 'secondary' | 'outline'
  border: string
}> = {
  critical: { label: 'Crítico', variant: 'destructive', border: 'border-l-red-500' },
  high:     { label: 'Alto', variant: 'default', border: 'border-l-orange-500' },
  medium:   { label: 'Medio', variant: 'secondary', border: 'border-l-amber-500' },
  low:      { label: 'Bajo', variant: 'outline', border: 'border-l-blue-400' },
}

// ─── Status Configuration ─────────────────────────────────────────────────────

const statusConfig: Record<string, { label: string; variant: 'default' | 'secondary' | 'outline' }> = {
  pending:   { label: 'Pendiente', variant: 'outline' },
  delivered: { label: 'Entregado', variant: 'default' },
  dismissed: { label: 'Descartado', variant: 'secondary' },
  acted_on:  { label: 'Resuelto', variant: 'secondary' },
  expired:   { label: 'Expirado', variant: 'secondary' },
}

// ─── Insight Type Icons ───────────────────────────────────────────────────────

function getInsightIcon(type: string) {
  const iconClass = 'h-5 w-5'
  switch (type) {
    case 'contract_expiration':
    case 'deadline_approaching':
      return <IconCalendarDue className={`${iconClass} text-orange-500`} />
    case 'compliance_alert':
      return <IconShieldCheck className={`${iconClass} text-blue-500`} />
    case 'risk_alert':
      return <IconAlertTriangle className={`${iconClass} text-red-500`} />
    case 'anomaly_detected':
      return <IconBug className={`${iconClass} text-purple-500`} />
    case 'task_reminder':
      return <IconChecklist className={`${iconClass} text-green-500`} />
    case 'document_update':
      return <IconFileDescription className={`${iconClass} text-cyan-500`} />
    case 'activity_summary':
      return <IconChartBar className={`${iconClass} text-indigo-500`} />
    default:
      return <IconBell className={`${iconClass} text-gray-500`} />
  }
}

const insightTypeLabels: Record<string, string> = {
  contract_expiration: 'Vencimiento de contrato',
  compliance_alert: 'Alerta de cumplimiento',
  risk_alert: 'Alerta de riesgo',
  anomaly_detected: 'Anomalía detectada',
  task_reminder: 'Recordatorio',
  deadline_approaching: 'Fecha límite próxima',
  document_update: 'Actualización de documento',
  activity_summary: 'Resumen de actividad',
}

function getInsightTypeLabel(type: string): string {
  return insightTypeLabels[type] || type.replace(/_/g, ' ')
}

function formatDateTime(dateString: string | null): string {
  if (!dateString) return '—'
  const date = new Date(dateString)
  if (isNaN(date.getTime())) return '—'
  return date.toLocaleDateString('es-ES', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString)
  if (isNaN(date.getTime())) return ''
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMin / 60)
  const diffDays = Math.floor(diffHours / 24)

  if (diffMin < 1) return 'ahora'
  if (diffMin < 60) return `hace ${diffMin}min`
  if (diffHours < 24) return `hace ${diffHours}h`
  if (diffDays < 7) return `hace ${diffDays}d`
  return formatDateTime(dateString)
}

// ============================================================================
// Main Page Component
// ============================================================================

export default function InsightsPage() {
  const { isLoaded, isAuthenticated } = useAuth()

  // Data
  const [insights, setInsights] = useState<ProactiveInsight[]>([])
  const [total, setTotal] = useState(0)

  // Filters
  const [statusFilter, setStatusFilter] = useState<string>('active')
  const [typeFilter, setTypeFilter] = useState<string>('all')

  // Loading
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionLoading, setActionLoading] = useState<string | null>(null)

  // ── Load insights ───────────────────────────────────────────────────────
  useEffect(() => {
    if (isLoaded && isAuthenticated) {
      loadInsights()
    }
  }, [statusFilter, typeFilter, isLoaded, isAuthenticated])

  async function loadInsights() {
    setIsLoading(true)
    setError(null)
    try {
      const params: { status?: string; insight_type?: string; limit: number } = {
        limit: 100,
      }

      // "active" = pending + delivered (not dismissed/expired/acted)
      if (statusFilter !== 'all' && statusFilter !== 'active') {
        params.status = statusFilter
      }
      if (typeFilter !== 'all') {
        params.insight_type = typeFilter
      }

      const response = await heartbeatService.getInsights(params)
      if (response.error) {
        setError(response.error)
      } else if (response.data) {
        let filtered = response.data.insights
        // Client-side filter for "active" (pending + delivered)
        if (statusFilter === 'active') {
          filtered = filtered.filter(i => i.status === 'pending' || i.status === 'delivered')
        }
        setInsights(filtered)
        setTotal(response.data.total)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al cargar alertas')
    } finally {
      setIsLoading(false)
    }
  }

  // ── Actions ─────────────────────────────────────────────────────────────
  async function handleDismiss(insightId: string) {
    setActionLoading(insightId)
    try {
      const result = await heartbeatService.dismissInsight(insightId)
      if (result.error) {
        setError(result.error)
      } else {
        // Update locally
        setInsights(prev => prev.map(i =>
          i.id === insightId ? { ...i, status: 'dismissed' as InsightStatus } : i
        ))
      }
    } finally {
      setActionLoading(null)
    }
  }

  async function handleMarkActed(insightId: string) {
    setActionLoading(insightId)
    try {
      const result = await heartbeatService.markAsActed(insightId)
      if (result.error) {
        setError(result.error)
      } else {
        // Update locally
        setInsights(prev => prev.map(i =>
          i.id === insightId ? { ...i, status: 'acted_on' as InsightStatus } : i
        ))
      }
    } finally {
      setActionLoading(null)
    }
  }

  // ── Derived data ────────────────────────────────────────────────────────
  const activeCount = insights.filter(i => i.status === 'pending' || i.status === 'delivered').length
  const uniqueTypes = [...new Set(insights.map(i => i.insight_type))]

  // ── Auth guard ──────────────────────────────────────────────────────────
  if (!isLoaded) {
    return (
      <div className="flex h-screen items-center justify-center">
        <IconLoader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  if (!isAuthenticated) {
    return null
  }

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <PageHeader>
          <nav className="flex items-center gap-2 text-sm text-muted-foreground">
            <Link href="/" className="hover:text-foreground transition-colors">Inicio</Link>
            <span>/</span>
            <span className="text-foreground font-medium">Alertas</span>
          </nav>
        </PageHeader>

        <main className="flex-1 overflow-auto p-4 md:p-6">
          <div className="space-y-6">
            {/* Title + Refresh */}
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-2xl font-semibold flex items-center gap-2">
                  <IconBell className="h-6 w-6" />
                  Alertas Proactivas
                </h1>
                <p className="text-sm text-muted-foreground mt-1">
                  Insights generados por Emma sobre tus documentos
                </p>
              </div>
              <div className="flex items-center gap-2">
                {!isLoading && activeCount > 0 && (
                  <Badge variant="default">{activeCount} activas</Badge>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => loadInsights()}
                  disabled={isLoading}
                >
                  <IconRefresh className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
                </Button>
              </div>
            </div>

            {/* Filters */}
            <div className="flex flex-col sm:flex-row gap-3">
              <Select
                value={statusFilter}
                onValueChange={setStatusFilter}
              >
                <SelectTrigger size="sm">
                  <IconFilter className="h-3.5 w-3.5 mr-1.5 text-muted-foreground" />
                  <SelectValue placeholder="Estado" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="active">Activas</SelectItem>
                  <SelectItem value="all">Todas</SelectItem>
                  <SelectItem value="pending">Pendientes</SelectItem>
                  <SelectItem value="delivered">Entregadas</SelectItem>
                  <SelectItem value="dismissed">Descartadas</SelectItem>
                  <SelectItem value="acted_on">Resueltas</SelectItem>
                </SelectContent>
              </Select>

              <Select
                value={typeFilter}
                onValueChange={setTypeFilter}
              >
                <SelectTrigger size="sm">
                  <SelectValue placeholder="Tipo" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todos los tipos</SelectItem>
                  {Object.entries(insightTypeLabels).map(([value, label]) => (
                    <SelectItem key={value} value={value}>{label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Error */}
            {error && (
              <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
                {error}
              </div>
            )}

            {/* Content */}
            {isLoading ? (
              <div className="flex items-center justify-center py-12">
                <IconLoader2 className="h-8 w-8 animate-spin text-primary" />
              </div>
            ) : insights.length === 0 ? (
              /* Empty state */
              <div className="text-center py-16">
                <IconInbox className="h-12 w-12 mx-auto mb-4 text-muted-foreground opacity-50" />
                <p className="text-muted-foreground mb-2">
                  {statusFilter === 'active'
                    ? 'No hay alertas activas'
                    : 'No se encontraron alertas'}
                </p>
                <p className="text-sm text-muted-foreground">
                  Emma genera alertas automáticamente al detectar vencimientos,
                  riesgos o cambios relevantes en tus documentos
                </p>
              </div>
            ) : (
              /* Insight cards */
              <div className="space-y-3">
                {insights.map((insight) => {
                  const urgency = urgencyConfig[insight.urgency] || urgencyConfig.medium
                  const status = statusConfig[insight.status] || statusConfig.pending
                  const isActive = insight.status === 'pending' || insight.status === 'delivered'
                  const isActionLoading = actionLoading === insight.id

                  return (
                    <Card
                      key={insight.id}
                      className={`border-l-4 ${urgency.border} ${!isActive ? 'opacity-60' : ''}`}
                    >
                      <CardContent className="p-4">
                        <div className="flex items-start gap-3">
                          {/* Icon */}
                          <div className="mt-0.5 shrink-0">
                            {getInsightIcon(insight.insight_type)}
                          </div>

                          {/* Content */}
                          <div className="flex-1 min-w-0">
                            {/* Header: title + badges */}
                            <div className="flex items-start justify-between gap-2">
                              <div className="min-w-0">
                                <h3 className="font-medium leading-snug">
                                  {insight.title}
                                </h3>
                                <div className="flex items-center gap-2 mt-1">
                                  <Badge variant={urgency.variant} className="text-xs">
                                    {urgency.label}
                                  </Badge>
                                  <span className="text-xs text-muted-foreground">
                                    {getInsightTypeLabel(insight.insight_type)}
                                  </span>
                                  {!isActive && (
                                    <Badge variant={status.variant} className="text-xs">
                                      {status.label}
                                    </Badge>
                                  )}
                                </div>
                              </div>
                              <span className="text-xs text-muted-foreground whitespace-nowrap shrink-0">
                                {formatRelativeTime(insight.created_at)}
                              </span>
                            </div>

                            {/* Summary */}
                            <p className="text-sm text-muted-foreground mt-2 leading-relaxed">
                              {insight.summary}
                            </p>

                            {/* Suggested actions */}
                            {insight.suggested_actions && insight.suggested_actions.length > 0 && (
                              <div className="mt-2 flex flex-wrap gap-1.5">
                                {insight.suggested_actions.map((action, idx) => (
                                  <span
                                    key={idx}
                                    className="text-xs bg-muted px-2 py-0.5 rounded-full text-muted-foreground"
                                  >
                                    {action.action}
                                  </span>
                                ))}
                              </div>
                            )}

                            {/* Actions */}
                            {isActive && (
                              <div className="flex items-center gap-2 mt-3">
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => handleMarkActed(insight.id)}
                                  disabled={isActionLoading}
                                >
                                  {isActionLoading ? (
                                    <IconLoader2 className="h-3.5 w-3.5 animate-spin mr-1" />
                                  ) : (
                                    <IconCheck className="h-3.5 w-3.5 mr-1" />
                                  )}
                                  Resuelto
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleDismiss(insight.id)}
                                  disabled={isActionLoading}
                                  className="text-muted-foreground"
                                >
                                  <IconX className="h-3.5 w-3.5 mr-1" />
                                  Descartar
                                </Button>
                              </div>
                            )}
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  )
                })}
              </div>
            )}
          </div>
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}
