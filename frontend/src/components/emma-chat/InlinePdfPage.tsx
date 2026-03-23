'use client'

import { useState, useRef, useEffect, useMemo, useCallback } from 'react'
import { Document, Page as RawPage, pdfjs } from 'react-pdf'

// Cast to any — react-pdf PageProps has a known type conflict with React 18
const Page = RawPage as any
import 'react-pdf/dist/Page/AnnotationLayer.css'
import 'react-pdf/dist/Page/TextLayer.css'
import { IconLoader2 } from '@tabler/icons-react'

pdfjs.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`

interface InlinePdfPageProps {
  url: string
  pageNumber?: number
}

/**
 * Renders a single PDF page that fills the available width.
 * The height adjusts proportionally (A4 aspect ratio).
 */
export default function InlinePdfPage({ url, pageNumber = 1 }: InlinePdfPageProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [containerWidth, setContainerWidth] = useState<number>(0)
  const [error, setError] = useState<string | null>(null)

  // Measure container width and watch for resize
  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const measure = () => setContainerWidth(el.clientWidth)
    measure()

    const observer = new ResizeObserver(measure)
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  const fileSource = useMemo(() => url, [url])

  const documentOptions = useMemo(
    () => ({
      cMapUrl: `https://unpkg.com/pdfjs-dist@${pdfjs.version}/cmaps/`,
      cMapPacked: true,
    }),
    [],
  )

  const onLoadError = useCallback((err: Error) => {
    console.error('InlinePdfPage load error:', err)
    setError('Error al cargar el PDF')
  }, [])

  const pageLoading = (
    <div
      className="flex items-center justify-center bg-white dark:bg-gray-800 border border-border"
      style={{ width: containerWidth, aspectRatio: '1/1.414' }}
    >
      <IconLoader2 className="h-6 w-6 animate-spin text-muted-foreground" />
    </div>
  )

  return (
    <div ref={containerRef} className="w-full flex justify-center">
      {containerWidth > 0 && (
        <Document
          file={fileSource}
          options={documentOptions}
          onLoadError={onLoadError}
          loading={null}
          className="flex justify-center w-full"
        >
          <Page
            pageNumber={pageNumber}
            width={containerWidth}
            className="shadow-lg"
            loading={pageLoading}
          />
        </Document>
      )}
      {error && (
        <p className="text-xs text-muted-foreground py-4">{error}</p>
      )}
    </div>
  )
}
