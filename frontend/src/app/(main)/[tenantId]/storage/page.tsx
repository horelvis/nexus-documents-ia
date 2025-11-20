"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { formatDistanceToNow } from "date-fns"
import {
  IconAlertTriangle,
  IconArchive,
  IconDatabase,
  IconInfoCircle,
  IconRefresh,
  IconShieldLock,
  IconTrash,
  IconUpload,
  IconUserCircle,
} from "@tabler/icons-react"
import { Area, AreaChart, CartesianGrid, XAxis } from "recharts"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Progress } from "@/components/ui/progress"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Skeleton } from "@/components/ui/skeleton"
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart"

import { formatBytes } from "@/lib/utils"
import { useTenantService } from "@/lib/services/tenant.service"
import { useDashboardService } from "@/lib/services/dashboard.service"
import { useDocumentService } from "@/lib/services/document.service"
import type { TenantInfo, TenantStats } from "@/lib/services/tenant.service"
import type { DashboardStats, AnalyticsTrends } from "@/lib/services/dashboard.service"
import type { Document as ApiDocument } from "@/lib/types"
import { useDocumentEvent } from "@/contexts/document-events-context"

type OwnerUsage = {
  id: string
  label: string
  bytes: number
  email?: string
}

type StorageAlert = {
  title: string
  description: string
  severity: "info" | "warning" | "critical"
}

const MAX_DOCUMENT_SAMPLE = 200
const WARNING_USAGE_PERCENT = 85
const CRITICAL_USAGE_PERCENT = 95
type DocumentOwnerShape = {
  id?: string
  email?: string
  full_name?: string
  name?: string
  username?: string
}

function extractOwnerDetails(doc: ApiDocument) {
  const rawOwner = doc.created_by as unknown

  if (rawOwner && typeof rawOwner === "object") {
    const owner = rawOwner as DocumentOwnerShape
    const label = owner.full_name || owner.name || owner.email || owner.username || "Unknown user"
    const id = owner.id || owner.email || owner.username || label

    return {
      id,
      label,
      email: owner.email,
    }
  }

  if (typeof doc.created_by === "string" && doc.created_by.trim().length > 0) {
    return {
      id: doc.created_by,
      label: doc.created_by,
      email: doc.created_by.includes("@") ? doc.created_by : undefined,
    }
  }

  const fallback = doc.user_id || "unknown"
  return {
    id: fallback,
    label: fallback,
    email: undefined,
  }
}

export default function StoragePage() {
  const tenantService = useTenantService()
  const dashboardService = useDashboardService()
  const documentService = useDocumentService()

  const [tenantInfo, setTenantInfo] = useState<TenantInfo | null>(null)
  const [tenantStats, setTenantStats] = useState<TenantStats | null>(null)
  const [dashboardStats, setDashboardStats] = useState<DashboardStats | null>(null)
  const [analyticsTrends, setAnalyticsTrends] = useState<AnalyticsTrends | null>(null)
  const [documents, setDocuments] = useState<ApiDocument[]>([])

  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const storageLimitBytes =
    tenantStats?.storage_limit_bytes ||
    tenantInfo?.max_storage_bytes ||
    0

  const storageUsedBytes =
    tenantStats?.storage_used_bytes ||
    dashboardStats?.total_storage_bytes ||
    0

  const storageAvailableBytes =
    storageLimitBytes > 0 ? Math.max(storageLimitBytes - storageUsedBytes, 0) : 0

  const usagePercent = storageLimitBytes
    ? Math.min((storageUsedBytes / storageLimitBytes) * 100, 150)
    : null

  const loadStorageData = useCallback(async () => {
    setIsLoading(true)
    setError(null)

    try {
      const [tenantInfoRes, tenantStatsRes, dashboardStatsRes, analyticsRes, documentsRes] = await Promise.all([
        tenantService.getCurrentTenant(),
        tenantService.getTenantStats(),
        dashboardService.getDashboardStats(),
        dashboardService.getAnalyticsTrends("30d"),
        documentService.getDocuments({
          page: 1,
          per_page: MAX_DOCUMENT_SAMPLE,
        }),
      ])

      setTenantInfo(tenantInfoRes.data || null)
      setTenantStats(tenantStatsRes.data || null)
      setDashboardStats(dashboardStatsRes.data || null)
      setAnalyticsTrends(analyticsRes.data || null)
      setDocuments(documentsRes.data?.items || [])
    } catch (err) {
      if (err instanceof Error) {
        setError(err.message)
      } else {
        setError("Unable to load storage information.")
      }
    } finally {
      setIsLoading(false)
    }
  }, [tenantService, dashboardService, documentService])

  useEffect(() => {
    loadStorageData()
  }, [loadStorageData])

  const handleDocumentsUpdated = useCallback(() => {
    loadStorageData()
  }, [loadStorageData])

  useDocumentEvent("documents:updated", handleDocumentsUpdated)

  const averageDocumentSize = useMemo(() => {
    if (!documents.length) return 0
    const totalBytes = documents.reduce((sum, doc) => sum + (doc.file_size || 0), 0)
    return Math.round(totalBytes / documents.length)
  }, [documents])

  const largestDocuments = useMemo(() => {
    if (!documents.length) return []
    return [...documents]
      .filter((doc) => doc.file_size)
      .sort((a, b) => (b.file_size || 0) - (a.file_size || 0))
      .slice(0, 5)
  }, [documents])

  const recentUploads = useMemo(() => {
    if (!documents.length) return []
    return [...documents]
      .filter((doc) => doc.created_at)
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
      .slice(0, 6)
  }, [documents])

  const usageBreakdown = useMemo(() => {
    if (!tenantStats?.documents_by_type) return []
    const entries = Object.entries(tenantStats.documents_by_type)
    const total = entries.reduce((sum, [, count]) => sum + count, 0)
    return entries
      .map(([type, count]) => ({
        type: type.toUpperCase(),
        count,
        percentage: total > 0 ? Math.round((count / total) * 100) : 0,
      }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 5)
  }, [tenantStats])

  const storageTimeline = useMemo(() => {
    if (!analyticsTrends?.storage_by_date) return []
    return Object.entries(analyticsTrends.storage_by_date)
      .map(([date, value]) => ({
        date,
        label: new Date(date).toLocaleDateString(undefined, { month: "short", day: "numeric" }),
        value: Math.max(Math.round(value / (1024 * 1024)), 0),
      }))
      .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime())
  }, [analyticsTrends])

  const ownerUsage = useMemo<OwnerUsage[]>(() => {
    if (!documents.length) return []

    const usageMap = new Map<string, OwnerUsage>()
    documents.forEach((doc) => {
      const ownerDetails = extractOwnerDetails(doc)

      const current = usageMap.get(ownerDetails.id)
      const bytes = doc.file_size || 0

      if (current) {
        current.bytes += bytes
      } else {
        usageMap.set(ownerDetails.id, {
          id: ownerDetails.id,
          label: ownerDetails.label,
          email: ownerDetails.email,
          bytes,
        })
      }
    })

    return Array.from(usageMap.values()).sort((a, b) => b.bytes - a.bytes).slice(0, 4)
  }, [documents])

  const topContributor = ownerUsage[0] || null

  const storageAlerts = useMemo<StorageAlert[]>(() => {
    const alerts: StorageAlert[] = []

    if (usagePercent !== null && usagePercent >= CRITICAL_USAGE_PERCENT) {
      const limitLabel = storageLimitBytes ? formatBytes(storageLimitBytes) : "the configured quota"
      alerts.push({
        title: "Storage quota reached",
        description: `The tenant has consumed ${usagePercent.toFixed(1)}% of its allocated storage (${formatBytes(
          storageUsedBytes
        )} of ${limitLabel}). Uploads will be blocked until space is released or the plan is upgraded.`,
        severity: "critical",
      })
    } else if (usagePercent !== null && usagePercent >= WARNING_USAGE_PERCENT) {
      alerts.push({
        title: "Storage usage above 85%",
        description: `You are nearing the configured quota (${usagePercent.toFixed(
          1
        )}%). Consider cleaning up large files or requesting an upgrade.`,
        severity: "warning",
      })
    }

    const largestDoc = largestDocuments[0]
    if (storageLimitBytes > 0 && largestDoc && largestDoc.file_size > storageLimitBytes * 0.15) {
      alerts.push({
        title: "Large document detected",
        description: `${largestDoc.title || largestDoc.filename} is using ${formatBytes(
          largestDoc.file_size
        )}. Consider archiving it outside Nexus to recover space.`,
        severity: "info",
      })
    }

    if (topContributor && usagePercent !== null && usagePercent >= CRITICAL_USAGE_PERCENT) {
      alerts.push({
        title: `${topContributor.label} notified`,
        description: `${topContributor.label} currently owns ${formatBytes(
          topContributor.bytes
        )}. They were notified because the tenant quota is exhausted.`,
        severity: "info",
      })
    }

    return alerts
  }, [usagePercent, storageUsedBytes, storageLimitBytes, largestDocuments, topContributor])

  const handleOptimizeStorage = () => {
    console.log("Storage optimization workflow coming soon.")
  }

  if (isLoading) {
    return (
      <div className="flex flex-col gap-6 p-6">
        <div className="space-y-4">
          <Skeleton className="h-7 w-64" />
          <Skeleton className="h-4 w-80" />
        </div>
        <StorageSkeleton />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6 p-4 md:p-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-3xl font-bold">Storage Management</h1>
            {usagePercent !== null && usagePercent >= 95 && (
              <Badge variant="destructive">Quota reached</Badge>
            )}
          </div>
          <p className="text-muted-foreground">
            Monitor consumption, investigate large files, and keep your workspace healthy.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={loadStorageData}>
            <IconRefresh className="mr-2 h-4 w-4" />
            Refresh
          </Button>
          <Button onClick={handleOptimizeStorage} variant="secondary">
            <IconTrash className="mr-2 h-4 w-4" />
            Run cleanup
          </Button>
          <Button>
            <IconShieldLock className="mr-2 h-4 w-4" />
            Request upgrade
          </Button>
        </div>
      </div>

      {error && (
        <Alert variant="destructive">
          <IconAlertTriangle className="h-4 w-4" />
          <AlertTitle>Unable to load usage data</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-col gap-1 pb-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <CardTitle>Tenant storage</CardTitle>
              <CardDescription>
                {storageLimitBytes
                  ? `${formatBytes(storageUsedBytes)} of ${formatBytes(storageLimitBytes)} used`
                  : `${formatBytes(storageUsedBytes)} stored`}
              </CardDescription>
            </div>
            {usagePercent !== null && (
              <Badge variant={usagePercent >= 95 ? "destructive" : usagePercent >= 85 ? "secondary" : "outline"}>
                {usagePercent.toFixed(1)}% utilized
              </Badge>
            )}
          </CardHeader>
          <CardContent className="space-y-6">
            <div>
              <div className="mb-2 flex items-center justify-between text-sm font-medium">
                <span>Usage</span>
                <span>
                  {formatBytes(storageUsedBytes)}
                  {storageLimitBytes ? ` / ${formatBytes(storageLimitBytes)}` : ""}
                </span>
              </div>
              <Progress value={Math.min(usagePercent ?? 0, 100)} />
              <div className="mt-2 flex flex-wrap gap-4 text-sm text-muted-foreground">
                <span>Available: {formatBytes(storageAvailableBytes)}</span>
                <span>Documents: {tenantStats?.total_documents ?? dashboardStats?.total_documents ?? 0}</span>
                <span>Avg file size: {formatBytes(averageDocumentSize)}</span>
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-3">
              <div className="rounded-lg border p-4">
                <p className="text-sm text-muted-foreground">Recent uploads</p>
                <p className="text-2xl font-bold">{dashboardStats?.recent_uploads ?? recentUploads.length}</p>
                <p className="text-xs text-muted-foreground">Last 24h</p>
              </div>
              <div className="rounded-lg border p-4">
                <p className="text-sm text-muted-foreground">Active users</p>
                <p className="text-2xl font-bold">{dashboardStats?.active_users ?? tenantStats?.total_users ?? 0}</p>
                <p className="text-xs text-muted-foreground">Contributing this month</p>
              </div>
              <div className="rounded-lg border p-4">
                <p className="text-sm text-muted-foreground">Cleanable space</p>
                <p className="text-2xl font-bold">
                  {storageLimitBytes ? formatBytes(Math.min(storageUsedBytes, storageLimitBytes) * 0.1) : "—"}
                </p>
                <p className="text-xs text-muted-foreground">Estimate via archive rules</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Plan & limits</CardTitle>
            <CardDescription>Current allocation & guardrails</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="rounded-lg border p-4">
              <div className="flex items-center gap-3">
                <IconDatabase className="h-5 w-5 text-primary" />
                <div>
                  <p className="text-sm text-muted-foreground">Total quota</p>
                  <p className="text-lg font-semibold">
                    {storageLimitBytes ? formatBytes(storageLimitBytes) : "Unlimited"}
                  </p>
                </div>
              </div>
            </div>
            <div className="rounded-lg border p-4">
              <div className="flex items-center gap-3">
                <IconUpload className="h-5 w-5 text-primary" />
                <div>
                  <p className="text-sm text-muted-foreground">Uploads allowed</p>
                  <p className="text-lg font-semibold">
                    {usagePercent !== null && usagePercent >= 100 ? "Blocked" : "Enabled"}
                  </p>
                </div>
              </div>
            </div>
            <div className="rounded-lg border p-4">
              <div className="flex items-center gap-3">
                <IconShieldLock className="h-5 w-5 text-primary" />
                <div>
                  <p className="text-sm text-muted-foreground">Data residency</p>
                  <p className="text-lg font-semibold">EU-West</p>
                </div>
              </div>
            </div>
            <Button className="w-full" variant="secondary">
              View upgrade options
            </Button>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-col gap-1 pb-0 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <CardTitle>Usage breakdown</CardTitle>
              <CardDescription>Top file types in your workspace</CardDescription>
            </div>
            <Badge variant="outline">{documents.length} sampled files</Badge>
          </CardHeader>
          <CardContent className="space-y-4 pt-6">
            {usageBreakdown.length === 0 && (
              <p className="text-sm text-muted-foreground">Upload documents to populate this section.</p>
            )}
            {usageBreakdown.map((item) => (
              <div key={item.type} className="space-y-1">
                <div className="flex items-center justify-between text-sm">
                  <span className="font-medium">{item.type}</span>
                  <span className="text-muted-foreground">{item.count} docs · {item.percentage}%</span>
                </div>
                <Progress value={item.percentage} />
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle>Alerts</CardTitle>
              <CardDescription>Quota, anomalies & large files</CardDescription>
            </div>
            <Badge variant={storageAlerts.length ? "secondary" : "outline"}>
              {storageAlerts.length || 0} open
            </Badge>
          </CardHeader>
          <CardContent className="space-y-3">
            {storageAlerts.length === 0 && (
              <div className="rounded-lg border border-dashed p-4 text-center text-sm text-muted-foreground">
                No active alerts. Keep monitoring usage regularly.
              </div>
            )}
            {storageAlerts.map((alert, index) => (
              <div
                key={`${alert.title}-${index}`}
                className="rounded-lg border p-3 text-sm"
                data-severity={alert.severity}
              >
                <div className="flex items-center gap-2 font-medium">
                  {alert.severity === "critical" && <IconAlertTriangle className="h-4 w-4 text-destructive" />}
                  {alert.severity === "warning" && <IconInfoCircle className="h-4 w-4 text-amber-500" />}
                  {alert.severity === "info" && <IconArchive className="h-4 w-4 text-muted-foreground" />}
                  <span>{alert.title}</span>
                </div>
                <p className="mt-1 text-muted-foreground">{alert.description}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <CardTitle>Storage trend (30 days)</CardTitle>
              <CardDescription>Daily growth in megabytes</CardDescription>
            </div>
            <Badge variant="outline">
              +{analyticsTrends?.total_storage_added ? Math.round(analyticsTrends.total_storage_added / (1024 * 1024 * 1024)) : 0} GB
            </Badge>
          </CardHeader>
          <CardContent>
            {storageTimeline.length === 0 ? (
              <div className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
                Storage timeline is unavailable. Upload a few files and check back soon.
              </div>
            ) : (
              <ChartContainer
                className="h-[220px]"
                config={{
                  storage: {
                    label: "Storage added",
                    color: "hsl(var(--chart-2))",
                  },
                }}
              >
                <AreaChart data={storageTimeline}>
                  <defs>
                    <linearGradient id="storageGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="10%" stopColor="var(--color-storage)" stopOpacity={0.5} />
                      <stop offset="90%" stopColor="var(--color-storage)" stopOpacity={0.05} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid vertical={false} strokeDasharray="3 3" />
                  <XAxis dataKey="label" tickLine={false} axisLine={false} />
                  <ChartTooltip
                    cursor={false}
                    content={
                      <ChartTooltipContent
                        formatter={(value) => [`${value} MB`, "Storage added"]}
                        labelFormatter={(label) => label}
                      />
                    }
                  />
                  <Area
                    type="monotone"
                    dataKey="value"
                    stroke="var(--color-storage)"
                    fill="url(#storageGradient)"
                    strokeWidth={2}
                    dot={false}
                    name="storage"
                  />
                </AreaChart>
              </ChartContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <CardTitle>Top contributors</CardTitle>
              <CardDescription>Users consuming the most space</CardDescription>
            </div>
            <Badge variant="outline">Last {documents.length} docs</Badge>
          </CardHeader>
          <CardContent>
            {ownerUsage.length === 0 ? (
              <p className="text-sm text-muted-foreground">No files uploaded yet.</p>
            ) : (
              <div className="space-y-4">
                {ownerUsage.map((owner) => {
                  const percentage = storageUsedBytes ? Math.round((owner.bytes / storageUsedBytes) * 100) : 0
                  const highlight =
                    !!topContributor &&
                    usagePercent !== null &&
                    usagePercent >= CRITICAL_USAGE_PERCENT &&
                    owner.id === topContributor.id
                  return (
                    <div key={owner.id} className="space-y-1 rounded-lg border p-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 font-medium">
                          <IconUserCircle className="h-4 w-4 text-muted-foreground" />
                          <span>{owner.label}</span>
                        </div>
                        {highlight && <Badge variant="destructive">Alerted</Badge>}
                      </div>
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-muted-foreground">{formatBytes(owner.bytes)}</span>
                        <span className="text-muted-foreground">{percentage}% of tenant usage</span>
                      </div>
                      <Progress value={percentage} />
                    </div>
                  )
                })}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Largest documents</CardTitle>
            <CardDescription>Focus on the top 5 files by size</CardDescription>
          </CardHeader>
          <CardContent className="pt-0">
            {largestDocuments.length === 0 ? (
              <p className="text-sm text-muted-foreground">Upload files to see largest assets.</p>
            ) : (
              <ScrollArea className="h-[280px] pr-4">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Document</TableHead>
                      <TableHead className="hidden sm:table-cell">Uploaded</TableHead>
                      <TableHead className="text-right">Size</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {largestDocuments.map((document) => (
                      <TableRow key={document.id}>
                        <TableCell className="font-medium">
                          {document.title || document.filename}
                        </TableCell>
                        <TableCell className="hidden text-sm text-muted-foreground sm:table-cell">
                          {document.created_at
                            ? formatDistanceToNow(new Date(document.created_at), { addSuffix: true })
                            : "Unknown"}
                        </TableCell>
                        <TableCell className="text-right font-medium">
                          {formatBytes(document.file_size || 0)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </ScrollArea>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Recent uploads</CardTitle>
            <CardDescription>Latest activity impacting storage</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {recentUploads.length === 0 ? (
              <p className="text-sm text-muted-foreground">No uploads detected.</p>
            ) : (
              recentUploads.map((document) => {
                const ownerDetails = extractOwnerDetails(document)
                return (
                  <div key={document.id} className="rounded-lg border p-3">
                    <div className="flex items-center justify-between text-sm font-medium">
                      <span>{document.title || document.filename}</span>
                      <span className="text-muted-foreground">{formatBytes(document.file_size || 0)}</span>
                    </div>
                    <div className="mt-1 flex items-center justify-between text-xs text-muted-foreground">
                      <span>
                        {document.created_at
                          ? formatDistanceToNow(new Date(document.created_at), { addSuffix: true })
                          : "Unknown date"}
                      </span>
                      <span>{ownerDetails.email || ownerDetails.label}</span>
                    </div>
                  </div>
                )
              })
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

function StorageSkeleton() {
  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <Skeleton className="h-80 rounded-xl lg:col-span-2" />
      <Skeleton className="h-80 rounded-xl" />
      <Skeleton className="h-64 rounded-xl lg:col-span-2" />
      <Skeleton className="h-64 rounded-xl" />
    </div>
  )
}
