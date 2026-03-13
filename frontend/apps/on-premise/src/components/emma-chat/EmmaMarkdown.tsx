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
 * Uses react-markdown + remark-gfm with explicit Tailwind component styling
 * (no @tailwindcss/typography dependency required).
 */
export const EmmaMarkdown = memo(function EmmaMarkdown({ content, className }: EmmaMarkdownProps) {
  if (!content) return null

  return (
    <div className={cn('max-w-none text-sm leading-relaxed', className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => (
            <h1 className="text-xl font-bold mt-4 mb-2">{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-lg font-semibold mt-4 mb-2">{children}</h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-base font-semibold mt-3 mb-1.5">{children}</h3>
          ),
          h4: ({ children }) => (
            <h4 className="text-sm font-semibold mt-3 mb-1">{children}</h4>
          ),
          p: ({ children }) => (
            <p className="mb-2 last:mb-0">{children}</p>
          ),
          strong: ({ children }) => (
            <strong className="font-semibold">{children}</strong>
          ),
          em: ({ children }) => (
            <em>{children}</em>
          ),
          ul: ({ children }) => (
            <ul className="my-2 ml-4 list-disc space-y-1">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="my-2 ml-4 list-decimal space-y-1">{children}</ol>
          ),
          li: ({ children }) => (
            <li className="pl-1">{children}</li>
          ),
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary hover:underline"
            >
              {children}
            </a>
          ),
          blockquote: ({ children }) => (
            <blockquote className="border-l-4 border-primary/30 pl-3 my-2 text-muted-foreground italic">
              {children}
            </blockquote>
          ),
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
              <code className="bg-muted px-1.5 py-0.5 rounded text-xs font-mono" {...props}>
                {children}
              </code>
            )
          },
          pre: ({ children }) => (
            <pre className="bg-muted rounded-md p-3 my-2 overflow-x-auto text-xs">
              {children}
            </pre>
          ),
          hr: () => <hr className="my-4 border-border" />,
          table: ({ children }) => (
            <div className="my-2 overflow-x-auto">
              <table className="min-w-full border-collapse text-xs">{children}</table>
            </div>
          ),
          thead: ({ children }) => (
            <thead className="border-b font-semibold">{children}</thead>
          ),
          th: ({ children }) => (
            <th className="px-3 py-1.5 text-left">{children}</th>
          ),
          td: ({ children }) => (
            <td className="px-3 py-1.5 border-b border-border/50">{children}</td>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
})
