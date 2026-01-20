"use client"

import { useEffect, useState } from "react"
import { useParams, useRouter } from "next/navigation"
import dynamic from "next/dynamic"

import { useSiteGuest } from "@/contexts/site-guest-context"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Loader2, ArrowLeft } from "lucide-react"

const PDFViewer = dynamic(() => import("@/components/documents/pdf-viewer"), {
  ssr: false,
  loading: () => (
    <div className="flex-1 flex items-center justify-center">
      <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
    </div>
  ),
})

export default function PortalDocumentViewPage() {
  const params = useParams()
  const router = useRouter()
  const slug = params.slug as string
  const documentId = params.documentId as string

  const { sessionToken, portalService } = useSiteGuest()

  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [pdfUrl, setPdfUrl] = useState<string | null>(null)
  const [fileName, setFileName] = useState<string>("document.pdf")
  const [title, setTitle] = useState<string>("")

  useEffect(() => {
    if (!sessionToken) {
      router.replace(`/portal/${slug}`)
      return
    }

    const load = async () => {
      setIsLoading(true)
      setError(null)
      try {
        const [docRes, viewRes] = await Promise.all([
          portalService.getDocument(documentId),
          portalService.getDocumentViewUrl(documentId),
        ])

        if (docRes.data) {
          setFileName(docRes.data.filename || "document.pdf")
          setTitle(docRes.data.title || docRes.data.filename || "")
        }

        if (viewRes.error || !viewRes.data?.view_url) {
          setError(viewRes.error || "Could not load preview")
          return
        }

        setPdfUrl(viewRes.data.view_url)
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not load preview")
      } finally {
        setIsLoading(false)
      }
    }

    load()
  }, [documentId, portalService, router, sessionToken, slug])

  if (!sessionToken) return null

  return (
    <div className="fixed inset-0 bg-background flex flex-col">
      <div className="bg-background border-b">
        <div className="container mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3 min-w-0">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => router.push(`/portal/${slug}`)}
              className="gap-2"
            >
              <ArrowLeft className="h-4 w-4" />
              Volver
            </Button>
            <div className="min-w-0">
              <div className="flex items-center gap-2 min-w-0">
                <h1 className="text-lg font-semibold truncate">{title || fileName}</h1>
                <Badge variant="outline" className="text-xs shrink-0">
                  Preview
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground truncate">{fileName}</p>
            </div>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-hidden">
        {isLoading && (
          <div className="h-full flex items-center justify-center">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        )}

        {!isLoading && error && (
          <div className="h-full flex items-center justify-center p-6">
            <div className="text-center">
              <p className="text-sm text-destructive mb-4">{error}</p>
              <Button variant="outline" onClick={() => router.refresh()}>
                Reintentar
              </Button>
            </div>
          </div>
        )}

        {!isLoading && !error && pdfUrl && (
          <PDFViewer
            url={pdfUrl}
            fileName={fileName}
            className="h-full"
            height="100%"
            showToolbar={true}
            initialScale={1.0}
            httpHeaders={{ Authorization: `Bearer ${sessionToken}` }}
            allowDownload={false}
            allowOpenExternal={false}
          />
        )}
      </div>
    </div>
  )
}

