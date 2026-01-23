'use client'

import { useMemo } from 'react'
import { cn } from '@/lib/utils'

interface EmmaMarkdownProps {
  content: string
  className?: string
}

/**
 * Simple Markdown renderer for Emma chat messages.
 * Supports: bold, italic, code, code blocks, lists, links, and headers.
 */
export function EmmaMarkdown({ content, className }: EmmaMarkdownProps) {
  const rendered = useMemo(() => {
    if (!content) return ''

    let html = content

    // Escape HTML entities first
    html = html
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')

    // Code blocks (```language\ncode\n```)
    html = html.replace(
      /```(\w*)\n([\s\S]*?)```/g,
      (_, lang, code) =>
        `<pre class="bg-muted rounded-md p-3 my-2 overflow-x-auto text-xs"><code class="language-${lang || 'text'}">${code.trim()}</code></pre>`
    )

    // Inline code (`code`)
    html = html.replace(
      /`([^`]+)`/g,
      '<code class="bg-muted px-1.5 py-0.5 rounded text-xs font-mono">$1</code>'
    )

    // Bold (**text** or __text__)
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong class="font-semibold">$1</strong>')
    html = html.replace(/__([^_]+)__/g, '<strong class="font-semibold">$1</strong>')

    // Italic (*text* or _text_)
    html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>')
    html = html.replace(/_([^_]+)_/g, '<em>$1</em>')

    // Headers (## Header)
    html = html.replace(/^### (.+)$/gm, '<h3 class="text-base font-semibold mt-4 mb-2">$1</h3>')
    html = html.replace(/^## (.+)$/gm, '<h2 class="text-lg font-semibold mt-4 mb-2">$1</h2>')
    html = html.replace(/^# (.+)$/gm, '<h1 class="text-xl font-bold mt-4 mb-2">$1</h1>')

    // Unordered lists (- item or * item)
    html = html.replace(/^[\-\*] (.+)$/gm, '<li class="ml-4 list-disc">$1</li>')

    // Ordered lists (1. item)
    html = html.replace(/^\d+\. (.+)$/gm, '<li class="ml-4 list-decimal">$1</li>')

    // Wrap consecutive list items in ul/ol tags
    html = html.replace(
      /(<li class="ml-4 list-disc">.+<\/li>\n?)+/g,
      (match) => `<ul class="my-2 space-y-1">${match}</ul>`
    )
    html = html.replace(
      /(<li class="ml-4 list-decimal">.+<\/li>\n?)+/g,
      (match) => `<ol class="my-2 space-y-1">${match}</ol>`
    )

    // Links [text](url)
    html = html.replace(
      /\[([^\]]+)\]\(([^)]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer" class="text-primary hover:underline">$1</a>'
    )

    // Blockquotes (> text)
    html = html.replace(
      /^&gt; (.+)$/gm,
      '<blockquote class="border-l-4 border-primary/30 pl-3 my-2 text-muted-foreground italic">$1</blockquote>'
    )

    // Horizontal rules (---, ***, ___)
    html = html.replace(/^[-*_]{3,}$/gm, '<hr class="my-4 border-border" />')

    // Paragraphs (double newlines)
    html = html.replace(/\n\n/g, '</p><p class="mb-2">')

    // Single newlines to <br>
    html = html.replace(/\n/g, '<br />')

    // Wrap in paragraph
    html = `<p class="mb-2">${html}</p>`

    // Clean up empty paragraphs
    html = html.replace(/<p class="mb-2"><\/p>/g, '')
    html = html.replace(/<p class="mb-2"><br \/>/g, '<p class="mb-2">')

    return html
  }, [content])

  return (
    <div
      className={cn('prose prose-sm dark:prose-invert max-w-none text-sm', className)}
      dangerouslySetInnerHTML={{ __html: rendered }}
    />
  )
}
