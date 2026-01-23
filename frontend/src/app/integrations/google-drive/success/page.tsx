'use client'

import { useEffect, useMemo, Suspense } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { CheckCircle2, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

function GoogleDriveSuccessContent() {
  const searchParams = useSearchParams()
  const tenantId = useMemo(() => searchParams?.get('tenantId'), [searchParams])

  useEffect(() => {
    if (window.opener) {
      window.opener.postMessage({ type: 'google-drive-connected' }, '*')
    }
  }, [])

  const templatesHref = tenantId ? `/${tenantId}/templates` : '/templates'

  return (
    <div className="min-h-screen flex items-center justify-center bg-muted/30 p-4">
      <Card className="max-w-md w-full text-center">
        <CardHeader>
          <div className="flex justify-center mb-4">
            <CheckCircle2 className="h-12 w-12 text-green-500" />
          </div>
          <CardTitle>Google Drive Connected</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p>Your Google Drive account is now linked. You can return to NouxCubeIA and start editing templates.</p>
          <Button asChild>
            <Link href={templatesHref}>Back to Templates</Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}

export default function GoogleDriveSuccessPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    }>
      <GoogleDriveSuccessContent />
    </Suspense>
  )
}
