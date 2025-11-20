"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from "recharts"
import { IconFile, IconChartPie } from "@tabler/icons-react"

interface FacetBucket {
  key: string
  count: number
  selected: boolean
}

interface DocumentTypeChartProps {
  data: FacetBucket[]
  totalDocuments: number
}

const COLORS = [
  '#0088FE', '#00C49F', '#FFBB28', '#FF8042',
  '#8884D8', '#82CA9D', '#FFC658', '#FF7C7C'
]

const FILE_TYPE_LABELS = {
  'pdf': 'PDF Documents',
  'docx': 'Word Documents',
  'doc': 'Word Documents',
  'xlsx': 'Excel Spreadsheets',
  'xls': 'Excel Spreadsheets',
  'pptx': 'PowerPoint Presentations',
  'ppt': 'PowerPoint Presentations',
  'txt': 'Text Files',
  'jpg': 'Images',
  'jpeg': 'Images',
  'png': 'Images',
  'unknown': 'Other Files'
}

export function DocumentTypeChart({ data, totalDocuments }: DocumentTypeChartProps) {
  // Group similar file types
  const groupedData = data.reduce((acc, item) => {
    const key = item.key || 'unknown'
    const groupKey = key.toLowerCase()

    // Group similar types
    let displayKey = FILE_TYPE_LABELS[groupKey as keyof typeof FILE_TYPE_LABELS] || key.toUpperCase()

    const existing = acc.find(item => item.displayKey === displayKey)
    if (existing) {
      existing.count += item.count
    } else {
      acc.push({
        displayKey,
        count: item.count,
        originalKey: key
      })
    }

    return acc
  }, [] as Array<{ displayKey: string; count: number; originalKey: string }>)

  // Sort by count descending and take top 8
  const chartData = groupedData
    .sort((a, b) => b.count - a.count)
    .slice(0, 8)
    .map((item, index) => ({
      name: item.displayKey,
      value: item.count,
      percentage: totalDocuments > 0 ? ((item.count / totalDocuments) * 100).toFixed(1) : '0',
      color: COLORS[index % COLORS.length]
    }))

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload
      return (
        <div className="bg-background border border-border rounded-lg p-3 shadow-lg">
          <p className="font-medium">{data.name}</p>
          <p className="text-sm text-muted-foreground">
            {data.value} documents ({data.percentage}%)
          </p>
        </div>
      )
    }
    return null
  }

  const CustomLegend = ({ payload }: any) => {
    return (
      <div className="flex flex-wrap gap-2 justify-center mt-4">
        {payload?.map((entry: any, index: number) => (
          <div key={index} className="flex items-center gap-2">
            <div
              className="w-3 h-3 rounded-full"
              style={{ backgroundColor: entry.color }}
            />
            <span className="text-sm">{entry.value}</span>
          </div>
        ))}
      </div>
    )
  }

  if (!data || data.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <IconChartPie className="h-5 w-5" />
            Document Types
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center h-64">
            <div className="text-center">
              <IconFile className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
              <p className="text-muted-foreground">No document type data available</p>
            </div>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <IconChartPie className="h-5 w-5" />
          Document Types
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={chartData}
                cx="50%"
                cy="50%"
                innerRadius={40}
                outerRadius={80}
                paddingAngle={2}
                dataKey="value"
              >
                {chartData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip content={<CustomTooltip />} />
              <Legend content={<CustomLegend />} />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div className="mt-4 space-y-2">
          {chartData.slice(0, 5).map((item, index) => (
            <div key={index} className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-2">
                <div
                  className="w-3 h-3 rounded-full"
                  style={{ backgroundColor: item.color }}
                />
                <span>{item.name}</span>
              </div>
              <div className="flex items-center gap-2">
                <Badge variant="secondary" className="text-xs">
                  {item.value}
                </Badge>
                <span className="text-muted-foreground">({item.percentage}%)</span>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}