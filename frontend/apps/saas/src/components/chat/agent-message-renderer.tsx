'use client'

import React from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { 
  IconAlertCircle, 
  IconCalendar, 
  IconCurrencyDollar,
  IconFileInvoice,
  IconChecklist,
  IconTrendingUp,
  IconClock,
  IconAlertTriangle
} from '@tabler/icons-react'
import ReactMarkdown from 'react-markdown'

interface AgentMessageRendererProps {
  content: string
  timestamp: string
  metadata?: any
}

export function AgentMessageRenderer({ content, timestamp, metadata }: AgentMessageRendererProps) {
  // Check if content contains markdown sections
  const hasMarkdown = content.includes('###') || content.includes('##') || content.includes('**')
  
  // Parse payment analysis structure
  const isPaymentAnalysis = content.includes('Payment Due Dates Analysis') || content.includes('OVERDUE')
  
  if (isPaymentAnalysis) {
    return <PaymentAnalysisRenderer content={content} timestamp={timestamp} />
  }
  
  if (hasMarkdown) {
    return <MarkdownMessageRenderer content={content} timestamp={timestamp} />
  }
  
  // Default simple message
  return (
    <div className="space-y-2">
      <div className="prose prose-sm dark:prose-invert max-w-none">
        <p className="whitespace-pre-wrap">{content}</p>
      </div>
      <span className="text-xs opacity-70 block">
        {new Date(timestamp).toLocaleTimeString()}
      </span>
    </div>
  )
}

function PaymentAnalysisRenderer({ content, timestamp }: { content: string, timestamp: string }) {
  // Parse the payment analysis content
  const sections = content.split('###').filter(Boolean)
  
  const overdueMatch = content.match(/OVERDUE \((\d+) items - \$([0-9,]+\.\d{2})\)/)
  const dueMatch = content.match(/DUE WITHIN 7 DAYS \((\d+) items - \$([0-9,]+\.\d{2})\)/)
  const upcomingMatch = content.match(/UPCOMING \((\d+) items - \$([0-9,]+\.\d{2})\)/)
  const totalMatch = content.match(/Total Outstanding[*:]+\s*\$([0-9,]+\.\d{2})/)
  
  return (
    <div className="space-y-4 w-full">
      {/* Header */}
      <div className="flex items-center gap-2 mb-2">
        <IconFileInvoice className="h-5 w-5 text-blue-600" />
        <h3 className="font-semibold text-lg">Payment Due Dates Analysis</h3>
      </div>
      
      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {/* Overdue Card */}
        <Card className="border-red-200 bg-red-50 dark:bg-red-950/20">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <IconAlertCircle className="h-4 w-4 text-red-600" />
              <span className="text-red-700 dark:text-red-400">Overdue</span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold text-red-700 dark:text-red-400">
              ${overdueMatch?.[2] || '0.00'}
            </p>
            <p className="text-sm text-muted-foreground">
              {overdueMatch?.[1] || '0'} items
            </p>
          </CardContent>
        </Card>
        
        {/* Due Soon Card */}
        <Card className="border-yellow-200 bg-yellow-50 dark:bg-yellow-950/20">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <IconClock className="h-4 w-4 text-yellow-600" />
              <span className="text-yellow-700 dark:text-yellow-400">Due This Week</span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold text-yellow-700 dark:text-yellow-400">
              ${dueMatch?.[2] || '0.00'}
            </p>
            <p className="text-sm text-muted-foreground">
              {dueMatch?.[1] || '0'} items
            </p>
          </CardContent>
        </Card>
        
        {/* Upcoming Card */}
        <Card className="border-green-200 bg-green-50 dark:bg-green-950/20">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <IconCalendar className="h-4 w-4 text-green-600" />
              <span className="text-green-700 dark:text-green-400">Upcoming</span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold text-green-700 dark:text-green-400">
              ${upcomingMatch?.[2] || '0.00'}
            </p>
            <p className="text-sm text-muted-foreground">
              {upcomingMatch?.[1] || '0'} items
            </p>
          </CardContent>
        </Card>
      </div>
      
      {/* Total Outstanding */}
      <Alert className="border-blue-200 bg-blue-50 dark:bg-blue-950/20">
        <IconCurrencyDollar className="h-4 w-4" />
        <AlertDescription className="flex items-center justify-between">
          <span className="font-medium">Total Outstanding</span>
          <span className="text-2xl font-bold text-blue-700 dark:text-blue-400">
            ${totalMatch?.[1] || '0.00'}
          </span>
        </AlertDescription>
      </Alert>
      
      {/* Detailed Sections */}
      <div className="space-y-3">
        {sections.map((section, index) => {
          if (section.includes('OVERDUE') || section.includes('DUE WITHIN') || section.includes('UPCOMING')) {
            return <PaymentSection key={index} content={section} />
          }
          if (section.includes('Recommended Actions')) {
            return <RecommendedActions key={index} content={section} />
          }
          return null
        })}
      </div>
      
      <span className="text-xs opacity-70 block text-right">
        {new Date(timestamp).toLocaleTimeString()}
      </span>
    </div>
  )
}

function PaymentSection({ content }: { content: string }) {
  const lines = content.split('\n').filter(Boolean)
  const header = lines[0]
  const items = lines.slice(2).filter(line => line.startsWith('-'))
  
  const isOverdue = header.includes('OVERDUE')
  const isDueSoon = header.includes('DUE WITHIN')
  
  const colorClass = isOverdue 
    ? 'text-red-600 dark:text-red-400' 
    : isDueSoon 
    ? 'text-yellow-600 dark:text-yellow-400' 
    : 'text-green-600 dark:text-green-400'
  
  return (
    <details className="group">
      <summary className={`cursor-pointer font-medium ${colorClass} hover:underline`}>
        {header.replace(/[🔴🟡🟢]/g, '').trim()}
      </summary>
      <div className="mt-2 pl-4 space-y-1">
        {items.map((item, idx) => (
          <div key={idx} className="text-sm text-muted-foreground">
            {item}
          </div>
        ))}
      </div>
    </details>
  )
}

function RecommendedActions({ content }: { content: string }) {
  const lines = content.split('\n').filter(Boolean)
  const actions = lines.slice(1).filter(line => line.match(/^\d\./))
  
  return (
    <Card className="border-blue-200">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm flex items-center gap-2">
          <IconChecklist className="h-4 w-4 text-blue-600" />
          Recommended Actions
        </CardTitle>
      </CardHeader>
      <CardContent>
        <ol className="space-y-2">
          {actions.map((action, idx) => (
            <li key={idx} className="text-sm flex items-start gap-2">
              <Badge variant="outline" className="mt-0.5 min-w-[24px] h-6 p-0 flex items-center justify-center">
                {idx + 1}
              </Badge>
              <span className="flex-1">
                {action.replace(/^\d\.\s*/, '').replace(/\*\*/g, '')}
              </span>
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  )
}

function MarkdownMessageRenderer({ content, timestamp }: { content: string, timestamp: string }) {
  return (
    <div className="space-y-2">
      <div className="prose prose-sm dark:prose-invert max-w-none">
        <ReactMarkdown
          components={{
            h2: ({ children }) => (
              <h2 className="text-lg font-semibold mt-4 mb-2 flex items-center gap-2">
                <IconTrendingUp className="h-5 w-5 text-blue-600" />
                {children}
              </h2>
            ),
            h3: ({ children }) => (
              <h3 className="text-base font-medium mt-3 mb-1">{children}</h3>
            ),
            ul: ({ children }) => (
              <ul className="space-y-1 list-none">{children}</ul>
            ),
            li: ({ children }) => (
              <li className="flex items-start gap-2">
                <span className="text-blue-600 mt-1">•</span>
                <span className="flex-1">{children}</span>
              </li>
            ),
            strong: ({ children }) => (
              <strong className="font-semibold text-foreground">{children}</strong>
            ),
          }}
        >
          {content}
        </ReactMarkdown>
      </div>
      <span className="text-xs opacity-70 block">
        {new Date(timestamp).toLocaleTimeString()}
      </span>
    </div>
  )
}