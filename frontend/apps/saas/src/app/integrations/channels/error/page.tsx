"use client"

import { useMemo, Suspense } from "react"
import Link from "next/link"
import { useSearchParams } from "next/navigation"
import { XCircle, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

function ChannelsErrorContent() {
  const searchParams = useSearchParams()
  const tenantId = useMemo(() => searchParams?.get("tenant_id"), [searchParams])
  const error = useMemo(() => searchParams?.get("error"), [searchParams])
  const errorDescription = useMemo(() => searchParams?.get("error_description"), [searchParams])

  const channelsHref = tenantId ? `/${tenantId}/channels` : "/channels"

  return (
    <div className="min-h-screen flex items-center justify-center bg-muted/30 p-4">
      <Card className="max-w-md w-full text-center">
        <CardHeader>
          <div className="flex justify-center mb-4">
            <XCircle className="h-12 w-12 text-destructive" />
          </div>
          <CardTitle>Connection Failed</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-muted-foreground">
            We couldn&apos;t connect your account. Please try again.
          </p>
          {(error || errorDescription) && (
            <div className="bg-destructive/10 text-destructive text-sm p-3 rounded-lg text-left">
              {error && <p className="font-medium">{error}</p>}
              {errorDescription && <p className="mt-1">{errorDescription}</p>}
            </div>
          )}
          <div className="flex gap-2 justify-center">
            <Button variant="outline" asChild>
              <Link href={channelsHref}>Back to Channels</Link>
            </Button>
            <Button asChild>
              <Link href={channelsHref}>Try Again</Link>
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

export default function ChannelsErrorPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    }>
      <ChannelsErrorContent />
    </Suspense>
  )
}
