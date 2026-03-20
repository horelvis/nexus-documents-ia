'use client'

import { memo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { cn } from '@/lib/utils'

interface EmmaMarkdownProps {
  content: string
  className?: string
}

/**
 * Markdown renderer for Emma chat messages.
 * Uses react-markdown + remark-gfm with rich Tailwind component styling
 * for a professional, readable output (no @tailwindcss/typography dependency).
 */
export const EmmaMarkdown = memo(function EmmaMarkdown({ content, className }: EmmaMarkdownProps) {
  if (!content) return null

  return (
    <div className={cn('max-w-none text-sm leading-relaxed text-foreground/90', className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // ── Headings ──
          h1: ({ children }) => (
            <h1 className="text-lg font-bold mt-5 mb-2.5 pb-1.5 border-b border-border/40 text-foreground">
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-base font-bold mt-5 mb-2 pb-1 border-b border-border/30 text-foreground">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-sm font-bold mt-4 mb-1.5 text-foreground">{children}</h3>
          ),
          h4: ({ children }) => (
            <h4 className="text-sm font-semibold mt-3 mb-1 text-foreground/90">{children}</h4>
          ),

          // ── Block elements ──
          p: ({ children }) => (
            <p className="mb-3 last:mb-0 leading-relaxed">{children}</p>
          ),
          blockquote: ({ children }) => (
            <blockquote className="border-l-3 border-primary/40 pl-3.5 py-1 my-3 bg-primary/5 rounded-r-md text-foreground/80 italic [&>p]:mb-1">
              {children}
            </blockquote>
          ),
          hr: () => <hr className="my-5 border-border/40" />,

          // ── Inline elements ──
          strong: ({ children }) => (
            <strong className="font-bold text-foreground">{children}</strong>
          ),
          em: ({ children }) => (
            <em className="text-foreground/80">{children}</em>
          ),
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary font-medium underline underline-offset-2 decoration-primary/40 hover:decoration-primary transition-colors"
            >
              {children}
            </a>
          ),

          // ── Lists ──
          ul: ({ children }) => (
            <ul className="my-2.5 ml-5 space-y-1.5 list-disc marker:text-primary/50">
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol className="my-2.5 ml-5 space-y-1.5 list-decimal marker:text-primary/70 marker:font-semibold">
              {children}
            </ol>
          ),
          li: ({ children }) => (
            <li className="pl-1.5 leading-relaxed">{children}</li>
          ),

          // ── Code ──
          code: ({ className: codeClassName, children, ...props }) => {
            const isBlock = codeClassName?.startsWith('language-')
            if (isBlock) {
              return (
                <code className={cn('text-xs', codeClassName)} {...props}>
                  {children}
                </code>
              )
            }
            return (
              <code
                className="bg-primary/8 text-primary border border-primary/15 px-1.5 py-0.5 rounded text-xs font-mono"
                {...props}
              >
                {children}
              </code>
            )
          },
          pre: ({ children }) => (
            <pre className="bg-muted/80 border border-border/40 rounded-lg p-4 my-3 overflow-x-auto text-xs leading-relaxed">
              {children}
            </pre>
          ),

          // ── Tables ──
          table: ({ children }) => (
            <div className="my-3 overflow-x-auto rounded-lg border border-border/40">
              <table className="min-w-full border-collapse text-xs">{children}</table>
            </div>
          ),
          thead: ({ children }) => (
            <thead className="bg-muted/50 border-b border-border/40">{children}</thead>
          ),
          th: ({ children }) => (
            <th className="px-3 py-2 text-left font-bold text-foreground text-xs uppercase tracking-wider">
              {children}
            </th>
          ),
          tbody: ({ children }) => (
            <tbody className="divide-y divide-border/30">{children}</tbody>
          ),
          tr: ({ children }) => (
            <tr className="hover:bg-muted/30 transition-colors">{children}</tr>
          ),
          td: ({ children }) => (
            <td className="px-3 py-2">{children}</td>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
})
