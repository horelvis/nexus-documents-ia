"use client"

import { useState, useEffect } from "react"
import { 
  IconCurrency,
  IconTrendingUp,
  IconTrendingDown,
  IconCalendar,
  IconAlertTriangle,
  IconChartBar,
  IconCalculator,
  IconFilterX,
  IconRefresh,
  IconChevronUp,
  IconChevronDown,
  IconCurrencyDollar,
  IconReceiptTax,
  IconCreditCard
} from "@tabler/icons-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"

interface FinancialAgentProps {
  searchResults: any[]
  searchQuery: string
  onFiltersChange: (filters: FinancialFilters) => void
  onInsightClick: (insight: string) => void | Promise<void>
}

interface FinancialFilters {
  minAmount?: number
  maxAmount?: number
  currency?: string
  dateRange?: string
  documentType?: string
  paymentStatus?: string
}

interface FinancialInsight {
  type: 'total' | 'average' | 'alert' | 'trend' | 'opportunity'
  title: string
  value: string
  description: string
  icon: React.ReactNode
  color: string
  action?: string
}

export function FinancialAgent({ 
  searchResults, 
  searchQuery, 
  onFiltersChange, 
  onInsightClick 
}: FinancialAgentProps) {
  const [insights, setInsights] = useState<FinancialInsight[]>([])
  const [filters, setFilters] = useState<FinancialFilters>({})
  const [showFilters, setShowFilters] = useState(false)

  useEffect(() => {
    analyzeFinancialData()
  }, [searchResults])

  const analyzeFinancialData = () => {
    if (searchResults.length === 0) return

    // Simulated financial analysis - in production this would analyze actual document content
    const documentCount = searchResults.length
    const invoiceCount = searchResults.filter(r => 
      r.document.title.toLowerCase().includes('invoice') || 
      r.document.title.toLowerCase().includes('factura')
    ).length

    const newInsights: FinancialInsight[] = [
      {
        type: 'total',
        title: 'Total Documents',
        value: documentCount.toString(),
        description: `Found ${documentCount} financial documents`,
        icon: <IconChartBar className="h-5 w-5" />,
        color: 'blue',
        action: 'Show all financial documents'
      },
      {
        type: 'alert',
        title: 'Invoices Found',
        value: invoiceCount.toString(),
        description: 'Review pending payments',
        icon: <IconReceiptTax className="h-5 w-5" />,
        color: 'orange',
        action: 'Check payment due dates'
      },
      {
        type: 'trend',
        title: 'Monthly Trend',
        value: '+12%',
        description: 'Compared to last month',
        icon: <IconTrendingUp className="h-5 w-5" />,
        color: 'green',
        action: 'Analyze monthly expenses'
      },
      {
        type: 'opportunity',
        title: 'Cost Optimization',
        value: '$2,450',
        description: 'Potential savings identified',
        icon: <IconCalculator className="h-5 w-5" />,
        color: 'purple',
        action: 'View optimization opportunities'
      }
    ]

    setInsights(newInsights)
  }

  const handleFilterChange = (key: keyof FinancialFilters, value: any) => {
    const newFilters = { ...filters, [key]: value }
    setFilters(newFilters)
    onFiltersChange(newFilters)
  }

  const getColorClasses = (color: string) => {
    const colors = {
      blue: 'bg-blue-50 text-blue-600 border-blue-200',
      orange: 'bg-orange-50 text-orange-600 border-orange-200',
      green: 'bg-green-50 text-green-600 border-green-200',
      purple: 'bg-purple-50 text-purple-600 border-purple-200',
      red: 'bg-red-50 text-red-600 border-red-200'
    }
    return colors[color as keyof typeof colors] || colors.blue
  }

  return (
    <div className="space-y-4">
      {/* Financial Overview */}
      <Card className="bg-gradient-to-r from-green-50 to-blue-50 border-green-200">
        <CardHeader className="pb-3">
          <CardTitle className="text-lg flex items-center gap-2">
            <IconCurrencyDollar className="h-5 w-5 text-green-600" />
            Financial Analysis
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Analyzing {searchResults.length} documents for financial insights, patterns, and opportunities.
          </p>
        </CardContent>
      </Card>

      {/* Quick Insights */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {insights.map((insight, index) => (
          <Card 
            key={index} 
            className={`cursor-pointer hover:shadow-md transition-shadow ${getColorClasses(insight.color)}`}
            onClick={() => insight.action && onInsightClick(insight.action)}
          >
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                {insight.icon}
                <Badge variant="outline" className="text-xs">
                  {insight.type}
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <h3 className="text-2xl font-bold mb-1">{insight.value}</h3>
              <p className="text-sm font-medium">{insight.title}</p>
              <p className="text-xs opacity-80 mt-1">{insight.description}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Advanced Filters */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-base flex items-center gap-2">
              <IconFilterX className="h-4 w-4" />
              Financial Filters
            </CardTitle>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowFilters(!showFilters)}
            >
              {showFilters ? (
                <IconChevronUp className="h-4 w-4" />
              ) : (
                <IconChevronDown className="h-4 w-4" />
              )}
            </Button>
          </div>
        </CardHeader>
        {showFilters && (
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="text-sm font-medium mb-1 block">Amount Range</label>
                <div className="flex gap-2">
                  <Input
                    type="number"
                    placeholder="Min"
                    value={filters.minAmount || ''}
                    onChange={(e) => handleFilterChange('minAmount', Number(e.target.value))}
                  />
                  <Input
                    type="number"
                    placeholder="Max"
                    value={filters.maxAmount || ''}
                    onChange={(e) => handleFilterChange('maxAmount', Number(e.target.value))}
                  />
                </div>
              </div>
              
              <div>
                <label className="text-sm font-medium mb-1 block">Currency</label>
                <Select 
                  value={filters.currency || ''} 
                  onValueChange={(value) => handleFilterChange('currency', value)}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="All currencies" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="USD">USD</SelectItem>
                    <SelectItem value="EUR">EUR</SelectItem>
                    <SelectItem value="GBP">GBP</SelectItem>
                    <SelectItem value="MXN">MXN</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              
              <div>
                <label className="text-sm font-medium mb-1 block">Date Range</label>
                <Select 
                  value={filters.dateRange || ''} 
                  onValueChange={(value) => handleFilterChange('dateRange', value)}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="All time" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="today">Today</SelectItem>
                    <SelectItem value="week">This Week</SelectItem>
                    <SelectItem value="month">This Month</SelectItem>
                    <SelectItem value="quarter">This Quarter</SelectItem>
                    <SelectItem value="year">This Year</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            
            <Separator />
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="text-sm font-medium mb-1 block">Document Type</label>
                <Select 
                  value={filters.documentType || ''} 
                  onValueChange={(value) => handleFilterChange('documentType', value)}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="All types" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="invoice">Invoices</SelectItem>
                    <SelectItem value="receipt">Receipts</SelectItem>
                    <SelectItem value="statement">Statements</SelectItem>
                    <SelectItem value="report">Reports</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              
              <div>
                <label className="text-sm font-medium mb-1 block">Payment Status</label>
                <Select 
                  value={filters.paymentStatus || ''} 
                  onValueChange={(value) => handleFilterChange('paymentStatus', value)}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="All statuses" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="paid">Paid</SelectItem>
                    <SelectItem value="pending">Pending</SelectItem>
                    <SelectItem value="overdue">Overdue</SelectItem>
                    <SelectItem value="cancelled">Cancelled</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            
            <div className="flex justify-end gap-2">
              <Button 
                variant="outline" 
                size="sm"
                onClick={() => {
                  setFilters({})
                  onFiltersChange({})
                }}
              >
                <IconRefresh className="h-4 w-4 mr-1" />
                Reset Filters
              </Button>
            </div>
          </CardContent>
        )}
      </Card>

      {/* Action Suggestions */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <IconCreditCard className="h-4 w-4" />
            Suggested Actions
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            <Button
              variant="outline"
              className="w-full justify-start"
              onClick={() => onInsightClick("Review invoices due this week")}
            >
              <IconCalendar className="h-4 w-4 mr-2" />
              Review invoices due this week
            </Button>
            <Button
              variant="outline"
              className="w-full justify-start"
              onClick={() => onInsightClick("Analyze expense categories")}
            >
              <IconChartBar className="h-4 w-4 mr-2" />
              Analyze expense categories
            </Button>
            <Button
              variant="outline"
              className="w-full justify-start"
              onClick={() => onInsightClick("Compare monthly spending trends")}
            >
              <IconTrendingUp className="h-4 w-4 mr-2" />
              Compare monthly spending trends
            </Button>
            <Button
              variant="outline"
              className="w-full justify-start text-orange-600 hover:text-orange-700"
              onClick={() => onInsightClick("Find overdue payments")}
            >
              <IconAlertTriangle className="h-4 w-4 mr-2" />
              Find overdue payments
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}