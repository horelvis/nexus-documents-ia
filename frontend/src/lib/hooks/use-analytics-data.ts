"use client"

import { useState, useEffect, useCallback } from "react"

interface DashboardStats {
  total_documents: number
  processed_documents: number
  processing_documents: number
  error_documents: number
  total_storage_bytes: number
  active_users: number
  recent_uploads: number
  trends: {
    documents: number
    storage: number
    active_users: number
    processed: number
    recent_uploads: number
    error_rate: number
  }
}

interface FacetBucket {
  key: string
  count: number
  selected: boolean
}

interface FacetResult {
  field: string
  buckets: FacetBucket[]
  total_count: number
}

interface FacetData {
  facets: FacetResult[]
  total_documents: number
}

interface TrendsData {
  period: string
  uploads_by_date: Record<string, number>
  views_by_date: Record<string, number>
  storage_by_date: Record<string, number>
  most_accessed_documents: Array<{
    document_id: string
    filename: string
    views: number
  }>
  total_uploads: number
  total_views: number
  total_storage_added: number
}

export function useAnalyticsData(tenantId: string, timeRange: "7d" | "30d" | "90d" = "30d") {
  const [dashboardStats, setDashboardStats] = useState<DashboardStats | null>(null)
  const [facetsData, setFacetsData] = useState<FacetData | null>(null)
  const [trendsData, setTrendsData] = useState<TrendsData | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchDashboardStats = useCallback(async () => {
    try {
      const response = await fetch(`/${tenantId}/api/dashboard/stats`)
      if (!response.ok) {
        throw new Error(`Failed to fetch dashboard stats: ${response.statusText}`)
      }
      const data = await response.json()
      setDashboardStats(data)
    } catch (err) {
      console.error('Error fetching dashboard stats:', err)
      setError(err instanceof Error ? err.message : 'Failed to fetch dashboard stats')
    }
  }, [tenantId])

  const fetchFacetsData = useCallback(async () => {
    try {
      const response = await fetch(`/${tenantId}/api/documents/facets`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          facet_fields: ["file_type", "category", "tags"],
          max_facet_values: 20
        }),
      })

      if (!response.ok) {
        throw new Error(`Failed to fetch facets: ${response.statusText}`)
      }

      const data = await response.json()
      setFacetsData(data)
    } catch (err) {
      console.error('Error fetching facets data:', err)
      setError(err instanceof Error ? err.message : 'Failed to fetch facets data')
    }
  }, [tenantId])

  const fetchTrendsData = useCallback(async () => {
    try {
      const response = await fetch(`/${tenantId}/api/dashboard/analytics/trends?period=${timeRange}`)
      if (!response.ok) {
        throw new Error(`Failed to fetch trends: ${response.statusText}`)
      }
      const data = await response.json()
      setTrendsData(data)
    } catch (err) {
      console.error('Error fetching trends data:', err)
      setError(err instanceof Error ? err.message : 'Failed to fetch trends data')
    }
  }, [tenantId, timeRange])

  const refetch = useCallback(async () => {
    setIsLoading(true)
    setError(null)

    await Promise.all([
      fetchDashboardStats(),
      fetchFacetsData(),
      fetchTrendsData()
    ])

    setIsLoading(false)
  }, [fetchDashboardStats, fetchFacetsData, fetchTrendsData])

  useEffect(() => {
    refetch()
  }, [refetch])

  // Refetch when timeRange changes
  useEffect(() => {
    fetchTrendsData()
  }, [timeRange, fetchTrendsData])

  return {
    dashboardStats,
    facetsData,
    trendsData,
    isLoading,
    error,
    refetch
  }
}