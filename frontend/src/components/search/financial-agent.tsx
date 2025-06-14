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
import { useNotifications } from "@/contexts/notifications-context"
import { useSearchService, SearchResult } from "@/lib/services/search.service"

interface FinancialAgentProps {
  searchResults: SearchResult[]
  searchQuery: string
  onFiltersChange: (filters: FinancialFilters) => void
  onInsightClick: (insight: string) => void
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

export default function FinancialAgent({ 
  searchResults, 
  searchQuery, 
  onFiltersChange,
  onInsightClick 
}: FinancialAgentProps) {
  const [isExpanded, setIsExpanded] = useState(false)
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [insights, setInsights] = useState<FinancialInsight[]>([])
  const [filters, setFilters] = useState<FinancialFilters>({})
  const [detectedDocTypes, setDetectedDocTypes] = useState<string[]>([])

  const { addNotification } = useNotifications()
  const searchService = useSearchService()

  // Detect if there are financial documents in search results
  const financialKeywords = ['factura', 'invoice', 'presupuesto', 'budget', 'cotización', 'quote', 'recibo', 'receipt', 'pago', 'payment']
  const hasFinancialDocs = searchResults.some(result => {
    // Handle both new structure (with document object) and current structure (with metadata)
    const document = result.document || result.metadata || {}
    const content = result.content || ''
    const documentText = `${document.title || ''} ${document.description || ''} ${document.filename || ''} ${content}`.toLowerCase()
    return financialKeywords.some(keyword => documentText.includes(keyword))
  }) || financialKeywords.some(keyword => searchQuery.toLowerCase().includes(keyword))

  // Generate financial insights based on search results
  useEffect(() => {
    if (hasFinancialDocs && searchResults.length > 0) {
      generateFinancialInsights()
      detectDocumentTypes()
    }
  }, [searchResults, hasFinancialDocs])

  const detectDocumentTypes = () => {
    const types = new Set<string>()
    searchResults.forEach(result => {
      // Handle both new structure (with document object) and current structure (with metadata)
      const document = result.document || result.metadata || {}
      const content = result.content || ''
      const documentText = `${document.title || ''} ${document.description || ''} ${document.filename || ''} ${content}`.toLowerCase()
      
      if (documentText.includes('factura') || documentText.includes('invoice')) types.add('invoice')
      if (documentText.includes('presupuesto') || documentText.includes('budget')) types.add('budget')
      if (documentText.includes('cotización') || documentText.includes('quote')) types.add('quote')
      if (documentText.includes('recibo') || documentText.includes('receipt')) types.add('receipt')
      if (documentText.includes('informe') && (documentText.includes('financiero') || documentText.includes('financial'))) types.add('report')
    })
    
    setDetectedDocTypes(Array.from(types))
  }

  const generateFinancialInsights = () => {
    const newInsights: FinancialInsight[] = []
    const docCount = searchResults.length

    // Total documents insight
    newInsights.push({
      type: 'total',
      title: 'Documentos Financieros',
      value: docCount.toString(),
      description: `${docCount} documento${docCount !== 1 ? 's' : ''} financiero${docCount !== 1 ? 's' : ''} encontrado${docCount !== 1 ? 's' : ''}`,
      icon: <IconReceiptTax className="h-4 w-4" />,
      color: 'text-blue-600',
      action: 'Analizar todos los documentos financieros'
    })

    // Document type analysis
    if (detectedDocTypes.length > 0) {
      const typeNames = {
        invoice: 'Facturas',
        budget: 'Presupuestos', 
        quote: 'Cotizaciones',
        receipt: 'Recibos',
        report: 'Informes'
      }
      
      const mainType = detectedDocTypes[0]
      newInsights.push({
        type: 'trend',
        title: 'Tipo Principal',
        value: typeNames[mainType as keyof typeof typeNames] || mainType,
        description: `Mayoría de documentos son ${typeNames[mainType as keyof typeof typeNames]?.toLowerCase() || mainType}`,
        icon: <IconChartBar className="h-4 w-4" />,
        color: 'text-green-600',
        action: `Analizar todas las ${typeNames[mainType as keyof typeof typeNames]?.toLowerCase() || mainType}`
      })
    }

    // Search-specific insights
    if (searchQuery.toLowerCase().includes('factura')) {
      newInsights.push({
        type: 'alert',
        title: 'Análisis de Facturas',
        value: 'Disponible',
        description: 'Puedo analizar totales, vencimientos y proveedores',
        icon: <IconCurrencyDollar className="h-4 w-4" />,
        color: 'text-amber-600',
        action: '¿Cuál es el total de estas facturas?'
      })
    }

    if (searchQuery.toLowerCase().includes('presupuesto') || searchQuery.toLowerCase().includes('budget')) {
      newInsights.push({
        type: 'opportunity',
        title: 'Análisis Presupuestario',
        value: 'Recomendado',
        description: 'Puedo comparar presupuestos y gastos',
        icon: <IconTrendingUp className="h-4 w-4" />,
        color: 'text-purple-600',
        action: 'Comparar presupuestos encontrados'
      })
    }

    // Time-based insight
    newInsights.push({
      type: 'alert',
      title: 'Análisis Temporal',
      value: 'Sugerido',
      description: 'Revisar fechas de vencimiento y pagos',
      icon: <IconCalendar className="h-4 w-4" />,
      color: 'text-red-600',
      action: '¿Hay documentos próximos a vencer?'
    })

    setInsights(newInsights)
  }

  const handleFilterChange = (key: keyof FinancialFilters, value: any) => {
    const newFilters = { ...filters, [key]: value }
    setFilters(newFilters)
    onFiltersChange(newFilters)
  }

  const clearFilters = () => {
    setFilters({})
    onFiltersChange({})
  }

  const handleInsightAction = async (insight: FinancialInsight) => {
    if (insight.action) {
      setIsAnalyzing(true)
      onInsightClick(insight.action)
      
      // Simulate analysis delay
      setTimeout(() => {
        setIsAnalyzing(false)
        setIsExpanded(true)
      }, 1000)
    }
  }

  // Don't show if no financial documents detected
  if (!hasFinancialDocs) {
    return null
  }

  return (
    <Card className="border-emerald-200 bg-emerald-50/50 dark:bg-emerald-950/20 dark:border-emerald-800">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-emerald-700 dark:text-emerald-300">
            <IconCurrency className="h-5 w-5" />
            Financial Agent
          </CardTitle>
          <div className="flex items-center gap-2">
            {insights.length > 0 && (
              <Badge variant="outline" className="text-xs border-emerald-200 text-emerald-600 dark:border-emerald-700 dark:text-emerald-400">
                {insights.length} insights
              </Badge>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsExpanded(!isExpanded)}
              className="text-emerald-600 hover:text-emerald-700 dark:text-emerald-400"
            >
              {isExpanded ? (
                <IconChevronUp className="h-4 w-4" />
              ) : (
                <IconChevronDown className="h-4 w-4" />
              )}
            </Button>
          </div>
        </div>
        
        {!isExpanded && (
          <div className="space-y-2">
            <p className="text-sm text-emerald-600 dark:text-emerald-400">
              Detecté {searchResults.length} documento{searchResults.length !== 1 ? 's' : ''} financiero{searchResults.length !== 1 ? 's' : ''}.
              {detectedDocTypes.length > 0 && ` Tipos: ${detectedDocTypes.join(', ')}`}
            </p>
            
            {insights.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {insights.slice(0, 2).map((insight, index) => (
                  <Button
                    key={index}
                    size="sm"
                    variant="outline"
                    onClick={() => handleInsightAction(insight)}
                    disabled={isAnalyzing}
                    className="h-6 text-xs border-emerald-200 text-emerald-600 hover:bg-emerald-100 dark:border-emerald-700 dark:text-emerald-300 dark:hover:bg-emerald-900/30"
                  >
                    {insight.icon}
                    <span className="ml-1">{insight.title}</span>
                  </Button>
                ))}
              </div>
            )}
          </div>
        )}
      </CardHeader>

      {isExpanded && (
        <CardContent className="space-y-4">
          {/* Financial Insights */}
          {insights.length > 0 && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-sm font-medium text-emerald-700 dark:text-emerald-300">
                <IconTrendingUp className="h-4 w-4" />
                Financial Insights:
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {insights.map((insight, index) => (
                  <div
                    key={index}
                    className="p-3 bg-white dark:bg-gray-800 rounded-lg border border-emerald-100 dark:border-emerald-800"
                  >
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className={insight.color}>{insight.icon}</span>
                        <span className="font-medium text-sm">{insight.title}</span>
                      </div>
                      <Badge variant="outline" className="text-xs">
                        {insight.value}
                      </Badge>
                    </div>
                    <p className="text-xs text-muted-foreground mb-2">
                      {insight.description}
                    </p>
                    {insight.action && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleInsightAction(insight)}
                        disabled={isAnalyzing}
                        className="h-6 text-xs w-full border-emerald-200 text-emerald-600 hover:bg-emerald-100 dark:border-emerald-700 dark:text-emerald-300 dark:hover:bg-emerald-900/30"
                      >
                        {isAnalyzing ? (
                          <IconRefresh className="h-3 w-3 animate-spin mr-1" />
                        ) : (
                          <IconCalculator className="h-3 w-3 mr-1" />
                        )}
                        {insight.action}
                      </Button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          <Separator />

          {/* Financial Filters */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm font-medium text-emerald-700 dark:text-emerald-300">
                <IconFilterX className="h-4 w-4" />
                Financial Filters:
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={clearFilters}
                className="h-6 text-xs border-emerald-200 text-emerald-600 hover:bg-emerald-100 dark:border-emerald-700 dark:text-emerald-300 dark:hover:bg-emerald-900/30"
              >
                Clear
              </Button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {/* Amount Range */}
              <div className="space-y-1">
                <label className="text-xs font-medium text-emerald-700 dark:text-emerald-300">
                  Monto Mínimo
                </label>
                <Input
                  type="number"
                  placeholder="0.00"
                  value={filters.minAmount || ''}
                  onChange={(e) => handleFilterChange('minAmount', e.target.value ? parseFloat(e.target.value) : undefined)}
                  className="h-8 text-xs"
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-medium text-emerald-700 dark:text-emerald-300">
                  Monto Máximo
                </label>
                <Input
                  type="number"
                  placeholder="99999.00"
                  value={filters.maxAmount || ''}
                  onChange={(e) => handleFilterChange('maxAmount', e.target.value ? parseFloat(e.target.value) : undefined)}
                  className="h-8 text-xs"
                />
              </div>

              {/* Currency */}
              <div className="space-y-1">
                <label className="text-xs font-medium text-emerald-700 dark:text-emerald-300">
                  Moneda
                </label>
                <Select value={filters.currency || ''} onValueChange={(value) => handleFilterChange('currency', value)}>
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue placeholder="Todas" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todas</SelectItem>
                    <SelectItem value="EUR">EUR</SelectItem>
                    <SelectItem value="USD">USD</SelectItem>
                    <SelectItem value="GBP">GBP</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Document Type */}
              {detectedDocTypes.length > 0 && (
                <div className="space-y-1">
                  <label className="text-xs font-medium text-emerald-700 dark:text-emerald-300">
                    Tipo de Documento
                  </label>
                  <Select value={filters.documentType || ''} onValueChange={(value) => handleFilterChange('documentType', value)}>
                    <SelectTrigger className="h-8 text-xs">
                      <SelectValue placeholder="Todos" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">Todos</SelectItem>
                      <SelectItem value="invoice">Facturas</SelectItem>
                      <SelectItem value="budget">Presupuestos</SelectItem>
                      <SelectItem value="quote">Cotizaciones</SelectItem>
                      <SelectItem value="receipt">Recibos</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              )}

              {/* Date Range */}
              <div className="space-y-1">
                <label className="text-xs font-medium text-emerald-700 dark:text-emerald-300">
                  Período
                </label>
                <Select value={filters.dateRange || ''} onValueChange={(value) => handleFilterChange('dateRange', value)}>
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue placeholder="Cualquiera" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Cualquiera</SelectItem>
                    <SelectItem value="this_month">Este mes</SelectItem>
                    <SelectItem value="last_month">Mes pasado</SelectItem>
                    <SelectItem value="this_quarter">Este trimestre</SelectItem>
                    <SelectItem value="this_year">Este año</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Payment Status */}
              <div className="space-y-1">
                <label className="text-xs font-medium text-emerald-700 dark:text-emerald-300">
                  Estado de Pago
                </label>
                <Select value={filters.paymentStatus || ''} onValueChange={(value) => handleFilterChange('paymentStatus', value)}>
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue placeholder="Cualquiera" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Cualquiera</SelectItem>
                    <SelectItem value="paid">Pagado</SelectItem>
                    <SelectItem value="pending">Pendiente</SelectItem>
                    <SelectItem value="overdue">Vencido</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>

          {/* Quick Actions */}
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-sm font-medium text-emerald-700 dark:text-emerald-300">
              <IconCalculator className="h-4 w-4" />
              Quick Financial Analysis:
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => onInsightClick("¿Cuál es el total de todos los documentos financieros?")}
                className="h-7 text-xs border-emerald-200 text-emerald-600 hover:bg-emerald-100 dark:border-emerald-700 dark:text-emerald-300 dark:hover:bg-emerald-900/30"
              >
                <IconCurrencyDollar className="h-3 w-3 mr-1" />
                Calcular Totales
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => onInsightClick("¿Hay facturas próximas a vencer?")}
                className="h-7 text-xs border-emerald-200 text-emerald-600 hover:bg-emerald-100 dark:border-emerald-700 dark:text-emerald-300 dark:hover:bg-emerald-900/30"
              >
                <IconCalendar className="h-3 w-3 mr-1" />
                Revisar Vencimientos
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => onInsightClick("Analiza los proveedores de estos documentos")}
                className="h-7 text-xs border-emerald-200 text-emerald-600 hover:bg-emerald-100 dark:border-emerald-700 dark:text-emerald-300 dark:hover:bg-emerald-900/30"
              >
                <IconCreditCard className="h-3 w-3 mr-1" />
                Analizar Proveedores
              </Button>
            </div>
          </div>
        </CardContent>
      )}
    </Card>
  )
}