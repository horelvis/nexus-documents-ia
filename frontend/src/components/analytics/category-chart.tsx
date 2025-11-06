"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { IconFolder, IconBarChart3 } from "@tabler/icons-react"

interface FacetBucket {
  key: string
  count: number
  selected: boolean
}

interface CategoryChartProps {
  data: FacetBucket[]
  totalDocuments: number
}

export function CategoryChart({ data, totalDocuments }: CategoryChartProps) {
  // Filter out empty categories and sort by count
  const validData = data
    .filter(item => item.key && item.key.trim() !== '')
    .sort((a, b) => b.count - a.count)
    .slice(0, 10) // Top 10 categories

  if (!data || data.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <IconBarChart3 className="h-5 w-5" />
            Document Categories
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center h-64">
            <div className="text-center">
              <IconFolder className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
              <p className="text-muted-foreground">No category data available</p>
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
          <IconBarChart3 className="h-5 w-5" />
          Document Categories
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {validData.map((item, index) => {
            const percentage = totalDocuments > 0 ? (item.count / totalDocuments) * 100 : 0
            const progressPercentage = maxCount > 0 ? (item.count / maxCount) * 100 : 0

            return (
              <div key={item.key || `category-${index}`} className="space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <IconFolder className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm font-medium truncate" title={item.key}>
                      {item.key}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary" className="text-xs">
                      {item.count}
                    </Badge>
                    <span className="text-xs text-muted-foreground">
                      {percentage.toFixed(1)}%
                    </span>
                  </div>
                </div>
                <Progress value={progressPercentage} className="h-2" />
              </div>
            )
          })}
        </div>

        {validData.length === 0 && (
          <div className="text-center py-8">
            <IconFolder className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
            <p className="text-muted-foreground">No categorized documents found</p>
            <p className="text-xs text-muted-foreground mt-2">
              Documents need to be categorized for this chart to show data
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  )
}