"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts"
import { IconTrendingUp, IconCalendar } from "@tabler/icons-react"

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

interface TrendsChartProps {
  data: TrendsData | null
  timeRange: "7d" | "30d" | "90d"
}

export function TrendsChart({ data, timeRange }: TrendsChartProps) {
  // Transform data for the chart
  const chartData = data ? Object.keys(data.uploads_by_date)
    .sort()
    .map(date => ({
      date: new Date(date).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric'
      }),
      uploads: data.uploads_by_date[date] || 0,
      views: data.views_by_date[date] || 0,
      storage: data.storage_by_date[date] ? Math.round(data.storage_by_date[date] / (1024 * 1024)) : 0 // Convert to MB
    })) : []

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-background border border-border rounded-lg p-3 shadow-lg">
          <p className="font-medium mb-2">{label}</p>
          {payload.map((entry: any, index: number) => (
            <p key={index} className="text-sm" style={{ color: entry.color }}>
              {entry.name}: {entry.value}{entry.dataKey === 'storage' ? ' MB' : ''}
            </p>
          ))}
        </div>
      )
    }
    return null
  }

  if (!data || chartData.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <IconTrendingUp className="h-5 w-5" />
            Trends Over Time
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center h-64">
            <div className="text-center">
              <IconCalendar className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
              <p className="text-muted-foreground">No trend data available</p>
              <p className="text-xs text-muted-foreground mt-2">
                Data will appear as documents are uploaded and viewed
              </p>
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
          <IconTrendingUp className="h-5 w-5" />
          Trends Over Time
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="h-64 mb-4">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
              <XAxis
                dataKey="date"
                fontSize={12}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                fontSize={12}
                tickLine={false}
                axisLine={false}
              />
              <Tooltip content={<CustomTooltip />} />
              <Line
                type="monotone"
                dataKey="uploads"
                stroke="#0088FE"
                strokeWidth={2}
                dot={{ fill: '#0088FE', strokeWidth: 2, r: 4 }}
                name="Uploads"
              />
              <Line
                type="monotone"
                dataKey="views"
                stroke="#00C49F"
                strokeWidth={2}
                dot={{ fill: '#00C49F', strokeWidth: 2, r: 4 }}
                name="Views"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Summary Stats */}
        <div className="grid grid-cols-3 gap-4 pt-4 border-t">
          <div className="text-center">
            <div className="text-2xl font-bold text-blue-600">{data.total_uploads}</div>
            <p className="text-xs text-muted-foreground">Total Uploads</p>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-green-600">{data.total_views}</div>
            <p className="text-xs text-muted-foreground">Total Views</p>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-purple-600">
              {Math.round(data.total_storage_added / (1024 * 1024))} MB
            </div>
            <p className="text-xs text-muted-foreground">Storage Added</p>
          </div>
        </div>

        {/* Most Accessed Documents */}
        {data.most_accessed_documents && data.most_accessed_documents.length > 0 && (
          <div className="mt-6 pt-4 border-t">
            <h4 className="text-sm font-medium mb-3">Most Accessed Documents</h4>
            <div className="space-y-2">
              {data.most_accessed_documents.slice(0, 3).map((doc, index) => (
                <div key={doc.document_id} className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-2">
                    <span className="text-muted-foreground">#{index + 1}</span>
                    <span className="truncate max-w-48" title={doc.filename}>
                      {doc.filename}
                    </span>
                  </div>
                  <span className="text-muted-foreground">{doc.views} views</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}