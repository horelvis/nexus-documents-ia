"use client"

import { useMemo, Suspense } from "react"
import Link from "next/link"
import { useSearchParams } from "next/navigation"
import { CheckCircle2, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

function ChannelsSuccessContent() {
  const searchParams = useSearchParams()
  const tenantId = useMemo(() => searchParams?.get("tenant_id"), [searchParams])
  const channelId = useMemo(() => searchParams?.get("channel_id"), [searchParams])

  const channelsHref = tenantId ? `/${tenantId}/channels` : "/channels"

  return (
    <div className="min-h-screen flex items-center justify-center bg-muted/30 p-4">
      <Card className="max-w-md w-full text-center">
        <CardHeader>
          <div className="flex justify-center mb-4">
            <CheckCircle2 className="h-12 w-12 text-green-500" />
          </div>
          <CardTitle>Channel Connected</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-muted-foreground">
            Your account has been successfully linked. The channel is now ready to sync data.
          </p>
          {channelId && (
            <p className="text-sm text-muted-foreground">
              Channel ID: <code className="bg-muted px-2 py-0.5 rounded">{channelId.slice(0, 8)}...</code>
            </p>
          )}
          <Button asChild>
            <Link href={channelsHref}>Back to Channels</Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}

export default function ChannelsSuccessPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    }>
      <ChannelsSuccessContent />
    </Suspense>
  )
}
