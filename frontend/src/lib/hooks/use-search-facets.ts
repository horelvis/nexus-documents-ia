"use client"

import { useState, useEffect, useCallback } from "react"
import { useRouter, useSearchParams } from "next/navigation"

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

interface SearchFilters {
  file_type?: string
  category?: string
  tags?: string[]
  date_from?: string
  date_to?: string
}

export function useSearchFacets(tenantId: string) {
  const router = useRouter()
  const searchParams = useSearchParams()

  const [facets, setFacets] = useState<FacetData | null>(null)
  const [isLoadingFacets, setIsLoadingFacets] = useState(false)
  const [currentFilters, setCurrentFilters] = useState<SearchFilters>({})
  const [searchQuery, setSearchQuery] = useState("")

  // Load facets from API
  const loadFacets = useCallback(async (query?: string, filters?: SearchFilters) => {
    setIsLoadingFacets(true)
    try {
      const response = await fetch(`/${tenantId}/api/documents/facets`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          query: query || searchQuery,
          filters: filters || currentFilters,
          facet_fields: ["file_type", "category", "tags"],
          max_facet_values: 10
        }),
      })

      if (response.ok) {
        const data = await response.json()
        setFacets(data)
      } else {
        console.error("Failed to load facets:", response.statusText)
        setFacets(null)
      }
    } catch (error) {
      console.error("Error loading facets:", error)
      setFacets(null)
    } finally {
      setIsLoadingFacets(false)
    }
  }, [tenantId, searchQuery, currentFilters])

  // Update URL with current filters
  const updateUrl = useCallback((filters: SearchFilters, query: string) => {
    const params = new URLSearchParams()

    if (query) params.set("q", query)
    if (filters.file_type) params.set("file_type", filters.file_type)
    if (filters.category) params.set("category", filters.category)
    if (filters.tags?.length) params.set("tags", filters.tags.join(","))
    if (filters.date_from) params.set("date_from", filters.date_from)
    if (filters.date_to) params.set("date_to", filters.date_to)

    const newUrl = `/search?${params.toString()}`
    router.replace(newUrl, { scroll: false })
  }, [router])

  // Handle facet selection change
  const handleFacetChange = useCallback((field: string, value: string, selected: boolean) => {
    const newFilters = { ...currentFilters }

    if (field === "tags") {
      const currentTags = newFilters.tags || []
      if (selected) {
        newFilters.tags = [...currentTags, value]
      } else {
        newFilters.tags = currentTags.filter(tag => tag !== value)
        if (newFilters.tags.length === 0) {
          delete newFilters.tags
        }
      }
    } else {
      if (selected) {
        newFilters[field as keyof SearchFilters] = value
      } else {
        delete newFilters[field as keyof SearchFilters]
      }
    }

    setCurrentFilters(newFilters)
    updateUrl(newFilters, searchQuery)
    loadFacets(searchQuery, newFilters)
  }, [currentFilters, searchQuery, updateUrl, loadFacets])

  // Clear all filters
  const clearAllFilters = useCallback(() => {
    const newFilters = {}
    setCurrentFilters(newFilters)
    updateUrl(newFilters, searchQuery)
    loadFacets(searchQuery, newFilters)
  }, [searchQuery, updateUrl, loadFacets])

  // Update search query
  const updateSearchQuery = useCallback((query: string) => {
    setSearchQuery(query)
    updateUrl(currentFilters, query)
    loadFacets(query, currentFilters)
  }, [currentFilters, updateUrl, loadFacets])

  // Initialize from URL params
  useEffect(() => {
    const query = searchParams.get("q") || ""
    const fileType = searchParams.get("file_type") || undefined
    const category = searchParams.get("category") || undefined
    const tagsParam = searchParams.get("tags")
    const dateFrom = searchParams.get("date_from") || undefined
    const dateTo = searchParams.get("date_to") || undefined

    const filters: SearchFilters = {}
    if (fileType) filters.file_type = fileType
    if (category) filters.category = category
    if (tagsParam) filters.tags = tagsParam.split(",").map(t => t.trim())
    if (dateFrom) filters.date_from = dateFrom
    if (dateTo) filters.date_to = dateTo

    setSearchQuery(query)
    setCurrentFilters(filters)

    // Load facets with current state
    loadFacets(query, filters)
  }, [searchParams, loadFacets])

  // Get active filter count
  const getActiveFilterCount = useCallback(() => {
    let count = 0
    if (currentFilters.file_type) count++
    if (currentFilters.category) count++
    if (currentFilters.tags?.length) count += currentFilters.tags.length
    if (currentFilters.date_from) count++
    if (currentFilters.date_to) count++
    return count
  }, [currentFilters])

  // Get filter summary for display
  const getFilterSummary = useCallback(() => {
    const summary: string[] = []
    if (currentFilters.file_type) summary.push(`Type: ${currentFilters.file_type}`)
    if (currentFilters.category) summary.push(`Category: ${currentFilters.category}`)
    if (currentFilters.tags?.length) summary.push(`Tags: ${currentFilters.tags.join(", ")}`)
    if (currentFilters.date_from) summary.push(`From: ${currentFilters.date_from}`)
    if (currentFilters.date_to) summary.push(`To: ${currentFilters.date_to}`)
    return summary
  }, [currentFilters])

  return {
    facets,
    isLoadingFacets,
    currentFilters,
    searchQuery,
    handleFacetChange,
    clearAllFilters,
    updateSearchQuery,
    getActiveFilterCount,
    getFilterSummary,
    loadFacets
  }
}