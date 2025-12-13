'use client'

/**
 * DocumentsLayout - Simple wrapper for documents page
 *
 * Simplified layout without folder sidebar navigation.
 * Folder organization happens via move operations, not sidebar navigation.
 */

import * as React from 'react'

interface DocumentsLayoutProps {
  children: React.ReactNode
}

export default function DocumentsLayout({ children }: DocumentsLayoutProps) {
  return (
    <div className="h-full w-full overflow-auto">
      {children}
    </div>
  )
}
