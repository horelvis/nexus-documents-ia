"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import {
  IconFilter,
  IconX,
  IconFile,
  IconTag,
  IconFolder,
  IconLoader2
} from "@tabler/icons-react"

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

interface FacetPanelProps {
  facets: FacetData | null
  onFacetChange: (field: string, value: string, selected: boolean) => void
  onClearAll: () => void
  isLoading?: boolean
  className?: string
}

const FIELD_LABELS = {
  file_type: "File Type",
  category: "Category",
  tags: "Tags"
}

const FIELD_ICONS = {
  file_type: IconFile,
  category: IconFolder,
  tags: IconTag
}

export function FacetPanel({
  facets,
  onFacetChange,
  onClearAll,
  isLoading = false,
  className = ""
}: FacetPanelProps) {
  const [expandedFields, setExpandedFields] = useState<Set<string>>(new Set(["file_type", "category"]))

  const toggleFieldExpansion = (field: string) => {
    const newExpanded = new Set(expandedFields)
    if (newExpanded.has(field)) {
      newExpanded.delete(field)
    } else {
      newExpanded.add(field)
    }
    setExpandedFields(newExpanded)
  }

  const getSelectedCount = () => {
    if (!facets?.facets) return 0
    return facets.facets.reduce((total, facet) => {
      return total + facet.buckets.filter(bucket => bucket.selected).length
    }, 0)
  }

  const selectedCount = getSelectedCount()

  if (isLoading) {
    return (
      <Card className={className}>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-sm">
            <IconFilter className="h-4 w-4" />
            Filters
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-8">
            <IconLoader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        </CardContent>
      </Card>
    )
  }

  if (!facets?.facets || facets.facets.length === 0) {
    return (
      <Card className={className}>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-sm">
            <IconFilter className="h-4 w-4" />
            Filters
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground text-center py-4">
            No filters available
          </p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-sm">
            <IconFilter className="h-4 w-4" />
            Filters
            {selectedCount > 0 && (
              <Badge variant="secondary" className="text-xs">
                {selectedCount}
              </Badge>
            )}
          </CardTitle>
          {selectedCount > 0 && (
            <Button
              variant="ghost"
              size="sm"
              onClick={onClearAll}
              className="h-6 px-2 text-xs"
            >
              <IconX className="h-3 w-3 mr-1" />
              Clear
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        <ScrollArea className="h-96">
          <div className="space-y-4">
            {facets.facets.map((facet) => {
              const IconComponent = FIELD_ICONS[facet.field as keyof typeof FIELD_ICONS] || IconTag
              const isExpanded = expandedFields.has(facet.field)

              return (
                <div key={facet.field} className="space-y-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => toggleFieldExpansion(facet.field)}
                    className="w-full justify-between p-0 h-auto font-medium text-sm"
                  >
                    <div className="flex items-center gap-2">
                      <IconComponent className="h-4 w-4" />
                      {FIELD_LABELS[facet.field as keyof typeof FIELD_LABELS] || facet.field}
                      <Badge variant="outline" className="text-xs">
                        {facet.total_count}
                      </Badge>
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {isExpanded ? "−" : "+"}
                    </div>
                  </Button>

                  {isExpanded && (
                    <div className="ml-6 space-y-1">
                      {facet.buckets.map((bucket) => (
                        <div
                          key={bucket.key}
                          className="flex items-center justify-between py-1 px-2 rounded hover:bg-muted/50"
                        >
                          <div className="flex items-center gap-2 flex-1 min-w-0">
                            <Checkbox
                              id={`${facet.field}-${bucket.key}`}
                              checked={bucket.selected}
                              onCheckedChange={(checked) =>
                                onFacetChange(facet.field, bucket.key, checked as boolean)
                              }
                              className="h-3 w-3"
                            />
                            <label
                              htmlFor={`${facet.field}-${bucket.key}`}
                              className="text-sm cursor-pointer truncate flex-1"
                              title={bucket.key}
                            >
                              {bucket.key || "(empty)"}
                            </label>
                          </div>
                          <Badge variant="secondary" className="text-xs ml-2">
                            {bucket.count}
                          </Badge>
                        </div>
                      ))}
                    </div>
                  )}

                  <Separator className="my-2" />
                </div>
              )
            })}
          </div>
        </ScrollArea>

        {facets.total_documents > 0 && (
          <div className="mt-4 pt-3 border-t">
            <p className="text-xs text-muted-foreground text-center">
              {facets.total_documents.toLocaleString()} total documents
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  )
}