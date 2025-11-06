"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { IconTag, IconHash } from "@tabler/icons-react"

interface FacetBucket {
  key: string
  count: number
  selected: boolean
}

interface TopTagsChartProps {
  data: FacetBucket[]
}

export function TopTagsChart({ data }: TopTagsChartProps) {
  // Filter out empty tags and sort by count
  const validData = data
    .filter(item => item.key && item.key.trim() !== '')
    .sort((a, b) => b.count - a.count)
    .slice(0, 15) // Top 15 tags

  if (!data || data.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <IconTag className="h-5 w-5" />
            Popular Tags
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center h-64">
            <div className="text-center">
              <IconHash className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
              <p className="text-muted-foreground">No tag data available</p>
              <p className="text-xs text-muted-foreground mt-2">
                Tags will appear as documents are tagged
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    )
  }

  const maxCount = Math.max(...validData.map(item => item.count))

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <IconTag className="h-5 w-5" />
          Popular Tags
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {validData.map((item, index) => {
            const intensity = maxCount > 0 ? (item.count / maxCount) : 0
            const opacity = 0.3 + (intensity * 0.7) // Range from 0.3 to 1.0

            return (
              <div key={item.key || `tag-${index}`} className="flex items-center justify-between">
                <div className="flex items-center gap-2 flex-1 min-w-0">
                  <IconHash className="h-3 w-3 text-muted-foreground flex-shrink-0" />
                  <span
                    className="text-sm truncate"
                    title={item.key}
                    style={{
                      fontWeight: intensity > 0.7 ? '600' : intensity > 0.4 ? '500' : '400'
                    }}
                  >
                    {item.key}
                  </span>
                </div>
                <Badge
                  variant="secondary"
                  className="text-xs flex-shrink-0 ml-2"
                  style={{
                    backgroundColor: `rgba(59, 130, 246, ${opacity})`,
                    color: intensity > 0.5 ? 'white' : 'inherit'
                  }}
                >
                  {item.count}
                </Badge>
              </div>
            )
          })}
        </div>

        {validData.length === 0 && (
          <div className="text-center py-8">
            <IconHash className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
            <p className="text-muted-foreground">No tags found</p>
            <p className="text-xs text-muted-foreground mt-2">
              Documents need to be tagged for this chart to show data
            </p>
          </div>
        )}

        {validData.length > 0 && (
          <div className="mt-4 pt-3 border-t">
            <p className="text-xs text-muted-foreground text-center">
              {validData.length} unique tags across all documents
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  )
}