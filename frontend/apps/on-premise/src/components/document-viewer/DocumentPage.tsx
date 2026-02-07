'use client'

import { forwardRef, type ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { cn } from '@/lib/utils'

interface DocumentPageProps {
  /** Markdown content — rendered with ReactMarkdown when provided */
  content?: string
  /** JSX children — rendered directly when provided (takes precedence over content if both set) */
  children?: ReactNode
  /** Zoom level (1 = 100%) */
  zoom?: number
  /** Additional class name for the outer wrapper */
  className?: string
}

/**
 * A4 page renderer that supports two modes:
 * 1. Markdown mode: pass `content` string → rendered with ReactMarkdown + GFM
 * 2. JSX mode: pass `children` → rendered directly inside the A4 wrapper
 *
 * Styled to look like a professional A4 document with proper margins,
 * typography, and print-friendly layout.
 */
const DocumentPage = forwardRef<HTMLDivElement, DocumentPageProps>(
  ({ content, children, zoom = 1, className }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(
          'bg-white dark:bg-card text-gray-900 dark:text-card-foreground',
          'shadow-lg border rounded-sm mx-auto',
          className
        )}
        style={{
          width: '21cm',
          minHeight: '29.7cm',
          padding: '2cm',
          zoom: zoom,
        }}
      >
        {children ? (
          children
        ) : content ? (
          <div className="document-page-markdown prose prose-sm dark:prose-invert max-w-none">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={markdownComponents}
            >
              {content}
            </ReactMarkdown>
          </div>
        ) : null}
      </div>
    )
  }
)

DocumentPage.displayName = 'DocumentPage'

export { DocumentPage }

// ── Custom Markdown components for formal document styling ──────

const markdownComponents = {
  h1: ({ children, ...props }: React.ComponentProps<'h1'>) => (
    <h1
      className="text-xl font-bold mt-6 mb-3 pb-2 border-b border-gray-200 dark:border-gray-700 text-gray-900 dark:text-card-foreground"
      {...props}
    >
      {children}
    </h1>
  ),
  h2: ({ children, ...props }: React.ComponentProps<'h2'>) => (
    <h2
      className="text-lg font-bold mt-5 mb-2 text-gray-800 dark:text-gray-200"
      {...props}
    >
      {children}
    </h2>
  ),
  h3: ({ children, ...props }: React.ComponentProps<'h3'>) => (
    <h3
      className="text-base font-semibold mt-4 mb-2 text-gray-800 dark:text-gray-200"
      {...props}
    >
      {children}
    </h3>
  ),
  p: ({ children, ...props }: React.ComponentProps<'p'>) => (
    <p
      className="text-sm leading-relaxed mb-3 text-gray-700 dark:text-gray-300"
      {...props}
    >
      {children}
    </p>
  ),
  ul: ({ children, ...props }: React.ComponentProps<'ul'>) => (
    <ul className="list-disc list-outside ml-5 mb-3 space-y-1" {...props}>
      {children}
    </ul>
  ),
  ol: ({ children, ...props }: React.ComponentProps<'ol'>) => (
    <ol className="list-decimal list-outside ml-5 mb-3 space-y-1" {...props}>
      {children}
    </ol>
  ),
  li: ({ children, ...props }: React.ComponentProps<'li'>) => (
    <li className="text-sm leading-relaxed text-gray-700 dark:text-gray-300" {...props}>
      {children}
    </li>
  ),
  blockquote: ({ children, ...props }: React.ComponentProps<'blockquote'>) => (
    <blockquote
      className="border-l-4 border-gray-300 dark:border-gray-600 pl-4 my-3 italic text-gray-600 dark:text-gray-400"
      {...props}
    >
      {children}
    </blockquote>
  ),
  table: ({ children, ...props }: React.ComponentProps<'table'>) => (
    <div className="overflow-x-auto mb-4">
      <table className="w-full text-sm border-collapse" {...props}>
        {children}
      </table>
    </div>
  ),
  thead: ({ children, ...props }: React.ComponentProps<'thead'>) => (
    <thead className="bg-gray-50 dark:bg-muted/30" {...props}>
      {children}
    </thead>
  ),
  th: ({ children, ...props }: React.ComponentProps<'th'>) => (
    <th
      className="border border-gray-200 dark:border-gray-700 px-3 py-2 text-left text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider"
      {...props}
    >
      {children}
    </th>
  ),
  td: ({ children, ...props }: React.ComponentProps<'td'>) => (
    <td
      className="border border-gray-200 dark:border-gray-700 px-3 py-2 text-sm text-gray-700 dark:text-gray-300"
      {...props}
    >
      {children}
    </td>
  ),
  hr: (props: React.ComponentProps<'hr'>) => (
    <hr className="my-6 border-gray-200 dark:border-gray-700" {...props} />
  ),
  a: ({ children, ...props }: React.ComponentProps<'a'>) => (
    <a
      className="text-blue-600 dark:text-blue-400 hover:underline"
      target="_blank"
      rel="noopener noreferrer"
      {...props}
    >
      {children}
    </a>
  ),
  code: ({ children, className: codeClassName, ...props }: React.ComponentProps<'code'>) => {
    // Inline code vs code block detection
    const isBlock = codeClassName?.startsWith('language-')
    if (isBlock) {
      return (
        <code
          className={cn(
            'block bg-gray-50 dark:bg-muted/50 rounded-md p-4 my-3 text-xs font-mono overflow-x-auto',
            codeClassName
          )}
          {...props}
        >
          {children}
        </code>
      )
    }
    return (
      <code
        className="bg-gray-100 dark:bg-muted px-1.5 py-0.5 rounded text-xs font-mono text-gray-800 dark:text-gray-200"
        {...props}
      >
        {children}
      </code>
    )
  },
  strong: ({ children, ...props }: React.ComponentProps<'strong'>) => (
    <strong className="font-semibold text-gray-900 dark:text-gray-100" {...props}>
      {children}
    </strong>
  ),
}
