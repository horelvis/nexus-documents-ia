"use client"

import { useParams } from "next/navigation"
import { AnalyticsDashboard } from "@/components/analytics/analytics-dashboard"

export default function AnalyticsPage() {
  const params = useParams()
  const tenantId = params.tenantId as string

  return <AnalyticsDashboard tenantId={tenantId} />
}