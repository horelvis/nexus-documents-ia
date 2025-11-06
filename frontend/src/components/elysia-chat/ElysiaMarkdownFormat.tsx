"use client"

import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { cn } from "@/lib/utils"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ExternalLink, FileText, Quote } from "lucide-react"

interface Citation {
  id: string
  title: string
  url?: string
  page?: number
  excerpt?: string
}

interface ElysiaMarkdownFormatProps {
  content: string
  citations?: Citation[]
  variant?: "primary" | "secondary" | "highlight"
  className?: string
}

export function ElysiaMarkdownFormat({
  content,
  citations = [],
  variant = "primary",
  className
}: ElysiaMarkdownFormatProps) {
  // Process citations in text (replace [ref_id] with citation bubbles)
  const processContentWithCitations = (text: string) => {
    if (!citations.length) return text
    
    // Create citation map for quick lookup
    const citationMap = citations.reduce((map, citation) => {
      map[citation.id] = citation
      return map
    }, {} as Record<string, Citation>)
    
    // Replace citation markers with placeholders
    let processedText = text
    const citationMatches = text.match(/\[ref_(\w+)\]/g) || []
    
    citationMatches.forEach((match) => {
      const refId = match.replace(/\[ref_(\w+)\]/, '$1')
      if (citationMap[refId]) {
        processedText = processedText.replace(match, `{CITATION:${refId}}`)
      }
    })
    
    return processedText
  }

  const processedContent = processContentWithCitations(content)

  // Custom components for markdown rendering
  const components = {
    // Paragraphs with citation support
    p: ({ children }: { children: React.ReactNode }) => {
      if (typeof children === 'string') {
        const parts = children.split(/(\{CITATION:\w+\})/g)
        return (
          <p className="mb-3 last:mb-0 leading-relaxed">
            {parts.map((part, index) => {
              const citationMatch = part.match(/\{CITATION:(\w+)\}/)
              if (citationMatch) {
                const citationId = citationMatch[1]
                const citation = citations.find(c => c.id === citationId)
                if (citation) {
                  return <CitationBubble key={index} citation={citation} />
                }
              }
              return part
            })}
          </p>
        )
      }
      return <p className="mb-3 last:mb-0 leading-relaxed">{children}</p>
    },
    
    // Headings
    h1: ({ children }: { children: React.ReactNode }) => (
      <h1 className="text-2xl font-bold mb-4 text-primary border-b border-border pb-2">
        {children}
      </h1>
    ),
    h2: ({ children }: { children: React.ReactNode }) => (
      <h2 className="text-xl font-semibold mb-3 text-primary border-b border-border pb-1">
        {children}
      </h2>
    ),
    h3: ({ children }: { children: React.ReactNode }) => (
      <h3 className="text-lg font-semibold mb-2 text-foreground">
        {children}
      </h3>
    ),
    h4: ({ children }: { children: React.ReactNode }) => (
      <h4 className="text-base font-semibold mb-2 text-foreground">
        {children}
      </h4>
    ),
    
    // Lists
    ul: ({ children }: { children: React.ReactNode }) => (
      <ul className="list-disc pl-6 mb-4 space-y-2">{children}</ul>
    ),
    ol: ({ children }: { children: React.ReactNode }) => (
      <ol className="list-decimal pl-6 mb-4 space-y-2">{children}</ol>
    ),
    li: ({ children }: { children: React.ReactNode }) => (
      <li className="leading-relaxed">{children}</li>
    ),
    
    // Code blocks
    code: ({ inline, children }: { inline?: boolean; children: React.ReactNode }) => {
      if (inline) {
        return (
          <code className="bg-muted px-2 py-1 rounded text-sm font-mono border">
            {children}
          </code>
        )
      }
      return (
        <pre className="bg-muted p-4 rounded-lg overflow-x-auto mb-4 border">
          <code className="text-sm font-mono">{children}</code>
        </pre>
      )
    },
    
    // Blockquotes
    blockquote: ({ children }: { children: React.ReactNode }) => (
      <blockquote className="border-l-4 border-primary pl-4 my-4 text-muted-foreground italic bg-muted/30 py-2 rounded-r">
        <Quote className="h-4 w-4 inline mr-2 opacity-50" />
        {children}
      </blockquote>
    ),
    
    // Tables
    table: ({ children }: { children: React.ReactNode }) => (
      <div className="overflow-x-auto mb-4">
        <table className="w-full border-collapse border border-border rounded-lg">
          {children}
        </table>
      </div>
    ),
    thead: ({ children }: { children: React.ReactNode }) => (
      <thead className="bg-muted">{children}</thead>
    ),
    th: ({ children }: { children: React.ReactNode }) => (
      <th className="border border-border px-4 py-2 text-left font-semibold">
        {children}
      </th>
    ),
    td: ({ children }: { children: React.ReactNode }) => (
      <td className="border border-border px-4 py-2">{children}</td>
    ),
    
    // Links
    a: ({ href, children }: { href?: string; children: React.ReactNode }) => (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-primary hover:underline font-medium inline-flex items-center gap-1"
      >
        {children}
        <ExternalLink className="h-3 w-3" />
      </a>
    ),
    
    // Strong and emphasis
    strong: ({ children }: { children: React.ReactNode }) => (
      <strong className="font-semibold text-foreground">{children}</strong>
    ),
    em: ({ children }: { children: React.ReactNode }) => (
      <em className="italic">{children}</em>
    ),
  }

  const textColor = {
    primary: "text-foreground",
    secondary: "text-muted-foreground", 
    highlight: "text-primary"
  }[variant]

  return (
    <div className={cn("prose prose-sm max-w-none", textColor, className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={components}
      >
        {processedContent}
      </ReactMarkdown>
      
      {/* Citations at the end */}
      {citations.length > 0 && (
        <div className="mt-6 pt-4 border-t border-border">
          <h4 className="text-sm font-semibold mb-3 text-muted-foreground flex items-center gap-2">
            <FileText className="h-4 w-4" />
            Referencias ({citations.length})
          </h4>
          <div className="space-y-2">
            {citations.map((citation) => (
              <div
                key={citation.id}
                className="text-xs text-muted-foreground p-2 bg-muted rounded border-l-2 border-primary/30"
              >
                <div className="font-medium">{citation.title}</div>
                {citation.page && (
                  <div className="text-muted-foreground">Página {citation.page}</div>
                )}
                {citation.excerpt && (
                  <div className="mt-1 italic">"{citation.excerpt}"</div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// Citation Bubble Component
interface CitationBubbleProps {
  citation: Citation
}

function CitationBubble({ citation }: CitationBubbleProps) {
  return (
    <Button
      variant="outline"
      size="sm"
      className="inline-flex h-6 px-2 mx-1 text-xs font-mono bg-primary/10 hover:bg-primary/20 border-primary/30"
      onClick={() => {
        // Handle citation click - could open a modal, scroll to reference, etc.
        console.log("Citation clicked:", citation)
      }}
      title={`${citation.title}${citation.page ? ` (p. ${citation.page})` : ''}`}
    >
      [{citation.id}]
    </Button>
  )
}