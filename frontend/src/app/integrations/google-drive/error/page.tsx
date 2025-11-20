'use client'

import { useEffect } from 'react'
import Link from 'next/link'
import { AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export default function GoogleDriveErrorPage() {
  useEffect(() => {
    if (window.opener) {
      window.opener.postMessage({ type: 'google-drive-error' }, '*')
    }
  }, [])

  return (
    <div className="min-h-screen flex items-center justify-center bg-muted/30 p-4">
      <Card className="max-w-md w-full text-center">
        <CardHeader>
          <div className="flex justify-center mb-4">
            <AlertTriangle className="h-12 w-12 text-red-500" />
          </div>
          <CardTitle>Connection Failed</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p>We couldn't connect your Google Drive account. Please try again or contact support if the issue persists.</p>
          <Button asChild variant="outline">
            <Link href="/templates">Back to Templates</Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
